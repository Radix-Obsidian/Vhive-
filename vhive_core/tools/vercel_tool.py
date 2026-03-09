"""
Vercel deployment tool — links a GitHub repo to a new Vercel project and triggers a build.
Polls until the deployment is READY, then returns the live URL.
"""

from __future__ import annotations

import logging
import os
import re
import time

import requests
from crewai.tools import BaseTool
from pydantic import BaseModel, Field

log = logging.getLogger(__name__)

_VERCEL_API = "https://api.vercel.com"


class VercelDeployToolInput(BaseModel):
    """Input schema for Vercel deployment."""

    repo_name: str = Field(..., description="GitHub repo in 'owner/repo' format")
    project_name: str = Field(..., description="Vercel project slug (kebab-case)")
    framework: str = Field(default="vite", description="Framework preset (vite, nextjs, etc.)")


class VercelDeployTool(BaseTool):
    """Create a Vercel project linked to a GitHub repo and deploy it."""

    name: str = "VercelDeployTool"
    description: str = (
        "Deploy a GitHub repo to Vercel. Requires VERCEL_TOKEN. "
        "The Vercel GitHub App must be installed on the target repo/org. "
        "Optional: VERCEL_TEAM_ID for team deployments."
    )
    args_schema: type = VercelDeployToolInput

    def _run(self, repo_name: str, project_name: str, framework: str = "vite") -> str:
        token = os.getenv("VERCEL_TOKEN", "").strip()
        if not token:
            return "Error: VERCEL_TOKEN must be set in .env"

        headers = {"Authorization": f"Bearer {token}"}
        team_id = os.getenv("VERCEL_TEAM_ID", "").strip()
        params: dict = {"teamId": team_id} if team_id else {}

        # 1. Create Vercel project linked to the GitHub repo
        project_resp = requests.post(
            f"{_VERCEL_API}/v9/projects",
            json={
                "name": project_name,
                "gitRepository": {"type": "github", "repo": repo_name},
                "framework": framework,
                "buildCommand": "npm run build",
                "outputDirectory": "dist",
            },
            headers=headers,
            params=params,
            timeout=30,
        )
        if project_resp.status_code in (400, 403):
            err_msg = project_resp.json().get("error", {}).get("message", str(project_resp.json()))
            return f"Error creating Vercel project: {err_msg}"
        if not project_resp.ok:
            return f"Error creating Vercel project: HTTP {project_resp.status_code}"

        project_data = project_resp.json()
        project_id = project_data["id"]
        log.info("Vercel: created project %s (id=%s)", project_name, project_id)

        # 2. Trigger deployment from GitHub main branch
        deploy_resp = requests.post(
            f"{_VERCEL_API}/v13/deployments",
            json={
                "name": project_name,
                "gitSource": {"type": "github", "repo": repo_name, "ref": "main"},
                "projectId": project_id,
            },
            headers=headers,
            params=params,
            timeout=30,
        )
        if not deploy_resp.ok:
            err = deploy_resp.json().get("error", {}).get("message", str(deploy_resp.status_code))
            return f"Error triggering deployment: {err}"

        deploy_data = deploy_resp.json()
        deploy_id = deploy_data["id"]
        deploy_url = deploy_data.get("url", "")
        log.info("Vercel: deployment %s queued", deploy_id)

        # 3. Poll until READY (up to 90 seconds)
        for _ in range(18):
            time.sleep(5)
            status_resp = requests.get(
                f"{_VERCEL_API}/v13/deployments/{deploy_id}",
                headers=headers,
                params=params,
                timeout=15,
            )
            if status_resp.ok:
                data = status_resp.json()
                state = data.get("readyState", "")
                if state == "READY":
                    deploy_url = data.get("url", deploy_url)
                    log.info("Vercel: deployment READY at %s", deploy_url)
                    break
                if state == "ERROR":
                    return f"Error: Vercel build failed — check dashboard for project '{project_name}'"

        live_url = f"https://{deploy_url}" if deploy_url and not deploy_url.startswith("http") else deploy_url
        return f"Deployed to Vercel: {live_url} (project: {project_id})"


# ── Module-level helpers ─────────────────────────────────────────

_VERCEL_URL_PATTERN = re.compile(r"https://[^\s)]+\.vercel\.app")


def extract_vercel_url(deploy_result: str) -> str | None:
    """Pull the live Vercel URL from a deploy result string."""
    m = _VERCEL_URL_PATTERN.search(deploy_result)
    return m.group(0) if m else None
