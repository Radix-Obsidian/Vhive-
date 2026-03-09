"""
GitHub tool — creates a repo and pushes all product files via the GitHub REST API.
Used by AURA's deploy step to host generated digital product code.
"""

from __future__ import annotations

import base64
import logging
import os
import re
import time

import requests
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

_GITHUB_API = "https://api.github.com"


class GitHubRepoToolInput(BaseModel):
    """Input schema for GitHub repo creation + file push."""

    product_name: str = Field(..., description="Repo name slug (kebab-case, no spaces)")
    files: dict[str, str] = Field(..., description="Mapping of file path to file content")
    description: str = Field(default="", description="Repository description")


class GitHubRepoTool(BaseTool):
    """Create a GitHub repo and push code files via the Git Data API."""

    name: str = "GitHubRepoTool"
    description: str = (
        "Create a public GitHub repo and push all product files. "
        "Requires GITHUB_TOKEN env var. Optional: GITHUB_ORG for org repos."
    )
    args_schema: type = GitHubRepoToolInput

    def _run(self, product_name: str, files: dict[str, str], description: str = "") -> str:
        token = os.getenv("GITHUB_TOKEN", "").strip()
        if not token:
            return "Error: GITHUB_TOKEN must be set in .env"

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        # Unique name to avoid collisions on re-runs
        repo_name = f"{product_name}-{int(time.time())}"

        # Determine owner: org or personal account
        org = os.getenv("GITHUB_ORG", "").strip()
        if org:
            create_url = f"{_GITHUB_API}/orgs/{org}/repos"
            owner = org
        else:
            me_resp = requests.get(f"{_GITHUB_API}/user", headers=headers, timeout=10)
            if not me_resp.ok:
                return f"Error: could not authenticate with GitHub — {me_resp.json().get('message', me_resp.status_code)}"
            owner = me_resp.json()["login"]
            create_url = f"{_GITHUB_API}/user/repos"

        # 1. Create repository (empty, no auto-init)
        resp = requests.post(
            create_url,
            json={"name": repo_name, "description": description, "private": False, "auto_init": False},
            headers=headers,
            timeout=30,
        )
        if resp.status_code == 422:
            return f"Error: repo name '{repo_name}' is invalid or already exists"
        if not resp.ok:
            return f"Error creating repo: {resp.json().get('message', resp.status_code)}"

        html_url = resp.json()["html_url"]
        base_url = f"{_GITHUB_API}/repos/{owner}/{repo_name}"

        # 2. Create blobs for each file
        tree_items = []
        for file_path, content in files.items():
            blob = requests.post(
                f"{base_url}/git/blobs",
                json={"content": base64.b64encode(content.encode()).decode(), "encoding": "base64"},
                headers=headers,
                timeout=30,
            )
            if not blob.ok:
                return f"Error uploading {file_path}: {blob.json().get('message', blob.status_code)}"
            tree_items.append({"path": file_path, "mode": "100644", "type": "blob", "sha": blob.json()["sha"]})

        # 3. Create tree
        tree_resp = requests.post(
            f"{base_url}/git/trees",
            json={"tree": tree_items},
            headers=headers,
            timeout=30,
        )
        if not tree_resp.ok:
            return f"Error creating git tree: {tree_resp.json().get('message', tree_resp.status_code)}"
        tree_sha = tree_resp.json()["sha"]

        # 4. Create root commit (no parents)
        commit_resp = requests.post(
            f"{base_url}/git/commits",
            json={"message": "Initial AURA product deploy", "tree": tree_sha, "parents": []},
            headers=headers,
            timeout=30,
        )
        if not commit_resp.ok:
            return f"Error creating commit: {commit_resp.json().get('message', commit_resp.status_code)}"
        commit_sha = commit_resp.json()["sha"]

        # 5. Create main branch ref
        ref_resp = requests.post(
            f"{base_url}/git/refs",
            json={"ref": "refs/heads/main", "sha": commit_sha},
            headers=headers,
            timeout=30,
        )
        if not ref_resp.ok:
            return f"Error creating branch ref: {ref_resp.json().get('message', ref_resp.status_code)}"

        log.info("GitHub: pushed %d files to %s", len(files), html_url)
        return f"Deployed to GitHub: {html_url} (repo: {owner}/{repo_name})"


# ── Module-level helpers ─────────────────────────────────────────

_GH_URL_PATTERN = re.compile(r"https://github\.com/[^\s)]+")
_GH_REPO_PATTERN = re.compile(r"repo:\s*([^/\s]+/[^\s)]+)")


def extract_github_url(deploy_result: str) -> str | None:
    """Pull the GitHub HTML URL from a deploy result string."""
    m = _GH_URL_PATTERN.search(deploy_result)
    return m.group(0) if m else None


def extract_github_repo(deploy_result: str) -> str | None:
    """Pull 'owner/repo-name' from a deploy result string."""
    m = _GH_REPO_PATTERN.search(deploy_result)
    return m.group(1) if m else None
