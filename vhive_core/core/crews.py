"""
CrewAI agent and task definitions for Vhive AURA.
Twitter Agent, Dev Agent, Sales Agent - each uses local Ollama via llm_config.
Agents receive memory context (daily notes, tacit knowledge) before each run.
Deploy pipeline: GitHub repo creation → Vercel deployment → Stripe payment link.
"""

import json
import logging
import os
import re
from typing import Any

import requests
from crewai import Agent, Crew, Process, Task

log = logging.getLogger(__name__)

from vhive_core.core.llm_config import CODING_LLM, CREATIVE_LLM
from vhive_core.memory import memory


def _twitter_agent(tools: list = None) -> Agent:
    """Fetches trends via Twitter API. Uses creative LLM."""
    return Agent(
        role="Twitter Research Analyst",
        goal="Identify trending topics and conversations relevant to digital products and cold traffic",
        backstory="Expert at monitoring Twitter for market signals and viral trends.",
        llm=CREATIVE_LLM,
        tools=tools or [],
        verbose=True,
    )


def _dev_agent(tools: list = None) -> Agent:
    """Builds digital product landing pages. Uses coding LLM. Has OpenHands for execution."""
    return Agent(
        role="Full-Stack Developer",
        goal=(
            "Build complete, deployable React+Vite landing pages for digital products. "
            "Each product must include a Stripe payment integration and be ready to push to GitHub and deploy on Vercel."
        ),
        backstory="Senior developer who ships polished landing pages fast and validates them before deploy.",
        llm=CODING_LLM,
        tools=tools or [],
        verbose=True,
    )


def _sales_agent(tools: list = None) -> Agent:
    """Drafts and sends DMs via iMessage and Telegram."""
    return Agent(
        role="Sales Outreach Specialist",
        goal="Draft compelling DMs and execute outreach via iMessage and Telegram to drive cold traffic",
        backstory="Data-driven sales professional who personalizes at scale.",
        llm=CREATIVE_LLM,
        tools=tools or [],
        verbose=True,
    )


def _get_tools():
    """Lazy import tools to avoid circular imports and allow tools to be built in Phase 3."""
    try:
        from vhive_core.tools.github_tool import GitHubRepoTool
        from vhive_core.tools.imessage_tool import iMessageSendTool
        from vhive_core.tools.openhands_tool import OpenHandsExecuteTool
        from vhive_core.tools.telegram_tool import TelegramSendTool
        from vhive_core.tools.twitter_tool import TwitterSearchTool, TwitterSendDMTool
        from vhive_core.tools.vercel_tool import VercelDeployTool

        return {
            "twitter_search": TwitterSearchTool(),
            "twitter_dm": TwitterSendDMTool(),
            "imessage": iMessageSendTool(),
            "telegram": TelegramSendTool(),
            "github": GitHubRepoTool(),
            "vercel": VercelDeployTool(),
            "openhands": OpenHandsExecuteTool(),
        }
    except ImportError:
        return {}


def _broadcast_agent(event: str, agent: str, payload: Any = None) -> None:
    """Emit agent event to Star-Office-UI WebSocket (no-op if broadcaster unavailable)."""
    try:
        from vhive_core.stream_bus import broadcaster

        broadcaster.emit_sync("crewai_agent", {"event": event, "agent": agent, "payload": payload})
    except ImportError:
        pass


def run_research_crew(state: dict[str, Any]) -> str:
    """State 1: Research via CrewAI Twitter Agent. Injects memory context."""
    _broadcast_agent("started", "twitter_research")
    tools = _get_tools()
    agent = _twitter_agent(tools=[tools["twitter_search"]] if "twitter_search" in tools else [])

    # Inject memory: recent daily notes + past trend knowledge
    recent_context = memory.read_recent_context(days=3)
    trend_knowledge = memory.read_knowledge("areas", "twitter-trends")
    memory_block = ""
    if recent_context:
        memory_block += f"\n\n## Recent Activity (last 3 days):\n{recent_context[:1000]}"
    if trend_knowledge:
        memory_block += f"\n\n## Known Trends:\n{trend_knowledge[:500]}"

    task = Task(
        description=(
            "Fetch current Twitter trends and conversations relevant to "
            "viperbyproof.com, complybyproof.com, and itsvoco.com. Summarize key themes."
            f"{memory_block}"
        ),
        agent=agent,
        expected_output="A concise summary of trending topics and relevant conversations.",
    )

    crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=True, stream=True)
    streaming = crew.kickoff()
    for chunk in streaming:
        _broadcast_agent(
            "thought",
            "twitter_research",
            {
                "task": getattr(chunk, "task_name", ""),
                "agent_role": getattr(chunk, "agent_role", agent.role),
                "content": getattr(chunk, "content", "") or "",
                "chunk_type": str(getattr(chunk, "chunk_type", "TEXT")),
                "tool_call": getattr(chunk, "tool_call", None),
            },
        )
    result = streaming.result
    result_str = str(result.raw) if hasattr(result, "raw") else str(result)

    # Update memory: append new trends to knowledge
    memory.update_knowledge("areas", "twitter-trends", result_str[:500])

    _broadcast_agent("finished", "twitter_research", {"result_preview": result_str[:200]})
    return result_str


def run_product_build_crew(state: dict[str, Any]) -> str:
    """State 2: Product build via CrewAI Dev Agent + OpenHands."""
    _broadcast_agent("started", "dev_product_build")
    tools = _get_tools()
    agent = _dev_agent(tools=[tools["openhands"]] if "openhands" in tools else [])

    research = state.get("research_data", "") or "No prior research."

    task = Task(
        description=(
            f"Based on this research: {research}.\n\n"
            "Build a digital product landing page as a Vite+React app. "
            "Return ONLY a valid JSON object — no prose before or after. "
            "The JSON must have exactly these keys:\n"
            "  - product_name: kebab-case slug (e.g. 'ai-seo-audit-tool')\n"
            "  - price_cents: integer price in cents (e.g. 2900 for $29)\n"
            "  - files: object mapping file paths to file content strings\n\n"
            "Required files:\n"
            "  - index.html (Vite entry point)\n"
            "  - package.json (react, react-dom, vite, @vitejs/plugin-react, tailwindcss, autoprefixer, postcss)\n"
            "  - vite.config.ts\n"
            "  - tailwind.config.js\n"
            "  - postcss.config.js\n"
            "  - src/main.tsx\n"
            "  - src/App.tsx (hero, pain points, CTA button using window.location.href = '__STRIPE_URL__')\n"
            "  - src/components/PricingCard.tsx\n\n"
            "The buy button must use: window.location.href = '__STRIPE_URL__' exactly.\n"
            "Return ONLY the JSON — no markdown, no backticks, no explanation."
        ),
        agent=agent,
        expected_output="A valid JSON object with product_name, price_cents, and files keys.",
    )

    crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=True, stream=True)
    streaming = crew.kickoff()
    for chunk in streaming:
        _broadcast_agent(
            "thought",
            "dev_product_build",
            {
                "task": getattr(chunk, "task_name", ""),
                "agent_role": getattr(chunk, "agent_role", agent.role),
                "content": getattr(chunk, "content", "") or "",
                "chunk_type": str(getattr(chunk, "chunk_type", "TEXT")),
                "tool_call": getattr(chunk, "tool_call", None),
            },
        )
    result = streaming.result
    _broadcast_agent("finished", "dev_product_build", {"result_preview": str(result)[:200]})
    return str(result.raw) if hasattr(result, "raw") else str(result)


def _parse_product_bundle(product_code: str) -> dict | None:
    """Try to extract the JSON product bundle from LLM output. Returns None on failure."""
    # Direct parse
    try:
        data = json.loads(product_code.strip())
        if isinstance(data, dict) and "product_name" in data and "files" in data:
            return data
    except json.JSONDecodeError:
        pass

    # Extract JSON block from mixed text (LLM sometimes wraps in prose)
    match = re.search(r"\{[\s\S]*\"product_name\"[\s\S]*\"files\"[\s\S]*\}", product_code)
    if match:
        try:
            data = json.loads(match.group(0))
            if isinstance(data, dict) and "product_name" in data and "files" in data:
                return data
        except json.JSONDecodeError:
            pass

    return None


def _create_stripe_payment_link(product_name: str, price_cents: int) -> str | None:
    """Create a Stripe Product + Price + Payment Link. Returns the payment link URL or None."""
    secret_key = os.getenv("STRIPE_SECRET_KEY", "").strip()
    if not secret_key:
        return None

    headers = {"Authorization": f"Bearer {secret_key}"}
    base = "https://api.stripe.com/v1"

    try:
        # 1. Create Stripe Product
        product_resp = requests.post(
            f"{base}/products",
            data={"name": product_name.replace("-", " ").title()},
            headers=headers,
            timeout=15,
        )
        product_resp.raise_for_status()
        stripe_product_id = product_resp.json()["id"]

        # 2. Create Price
        price_resp = requests.post(
            f"{base}/prices",
            data={
                "product": stripe_product_id,
                "unit_amount": str(price_cents),
                "currency": "usd",
            },
            headers=headers,
            timeout=15,
        )
        price_resp.raise_for_status()
        stripe_price_id = price_resp.json()["id"]

        # 3. Create Payment Link
        link_resp = requests.post(
            f"{base}/payment_links",
            data={
                "line_items[0][price]": stripe_price_id,
                "line_items[0][quantity]": "1",
                f"metadata[product_name]": product_name,
            },
            headers=headers,
            timeout=15,
        )
        link_resp.raise_for_status()
        return link_resp.json()["url"]
    except Exception as e:
        log.warning("Stripe payment link creation failed: %s", e)
        return None


def run_deploy_crew(state: dict[str, Any]) -> str:
    """State 3: Deploy via GitHub + Vercel pipeline with Stripe payment link."""
    tools = _get_tools()
    product_code = state.get("product_code", "")

    # Parse the JSON bundle from the coding LLM output
    bundle = _parse_product_bundle(product_code)
    if not bundle:
        log.warning("product_code is not a valid JSON bundle — deploy skipped")
        return "Deploy skipped: product_code is not a valid JSON bundle"

    product_name = bundle.get("product_name", "aura-product")
    price_cents = bundle.get("price_cents", 0)
    files: dict[str, str] = bundle.get("files", {})

    if not files:
        return "Deploy skipped: product bundle contains no files"

    # Inject Stripe payment link URL (or placeholder if STRIPE_SECRET_KEY not set)
    stripe_url = _create_stripe_payment_link(product_name, price_cents)
    if stripe_url:
        _broadcast_agent("thought", "dev_product_build", {"content": f"Stripe payment link: {stripe_url}"})
    else:
        stripe_url = "https://buy.stripe.com/placeholder"
        log.info("STRIPE_SECRET_KEY not set — using placeholder URL")

    files = {path: content.replace("__STRIPE_URL__", stripe_url) for path, content in files.items()}

    # Push to GitHub
    github_tool = tools.get("github")
    if not github_tool:
        return "Deploy skipped: GitHubRepoTool not available"

    github_result = github_tool.run(
        product_name=product_name,
        files=files,
        description=f"AURA digital product: {product_name}",
    )
    _broadcast_agent("thought", "dev_product_build", {"content": github_result})

    if github_result.startswith("Error"):
        return f"GitHub deploy failed: {github_result}"

    # Deploy to Vercel
    from vhive_core.tools.github_tool import extract_github_repo

    repo_name = extract_github_repo(github_result)
    vercel_tool = tools.get("vercel")
    if not vercel_tool or not repo_name:
        return f"{github_result} | Vercel deploy skipped: tool or repo name unavailable"

    vercel_result = vercel_tool.run(repo_name=repo_name, project_name=product_name)
    _broadcast_agent("thought", "dev_product_build", {"content": vercel_result})

    return f"{github_result} | {vercel_result}"


def run_outreach_crew(state: dict[str, Any]) -> str:
    """State 4: Outreach via CrewAI Sales Agent + iMessage/Telegram/Twitter. Reads tacit rules and patterns."""
    _broadcast_agent("started", "sales_outreach")
    tools = _get_tools()
    agent_tools = []
    if "twitter_dm" in tools:
        agent_tools.append(tools["twitter_dm"])
    if "imessage" in tools:
        agent_tools.append(tools["imessage"])
    if "telegram" in tools:
        agent_tools.append(tools["telegram"])

    agent = _sales_agent(tools=agent_tools)

    research = state.get("research_data", "") or ""
    deployment = state.get("deployment_status", "") or ""

    # Inject tacit knowledge: rules + patterns
    rules = memory.read_tacit("rules")
    patterns = memory.read_tacit("patterns")
    tacit_block = ""
    if rules:
        tacit_block += f"\n\n## Rules (MUST follow):\n{rules[:500]}"
    if patterns:
        tacit_block += f"\n\n## What has worked before:\n{patterns[:500]}"

    task = Task(
        description=(
            f"Research: {research[:300]}. Deployment: {deployment[:200]}. "
            "Your job: send an operator summary via Telegram, then attempt iMessage outreach ONLY if you have a real contact number.\n\n"
            "STEP 1 — REQUIRED: Use TelegramSendTool (no chat_id needed, uses default) to send a run summary: "
            "what was researched, what product was built, deployment status, and your outreach plan.\n\n"
            "STEP 2 — iMessage to operator: Send a brief run summary via iMessage to +12346505567. "
            "This is the operator's verified iPhone number. Include: what was built, deploy status, and next steps. "
            "NEVER use any other phone number. NEVER invent or guess numbers.\n\n"
            "STEP 3 — Twitter DM: Currently unavailable (API credits depleted). Skip it.\n\n"
            "Products to promote: viperbyproof.com (privacy compliance), complybyproof.com (compliance automation), itsvoco.com (voice AI)."
            f"{tacit_block}"
        ),
        agent=agent,
        expected_output="Confirmation of Telegram message sent, and summary of all outreach actions taken.",
    )

    crew = Crew(agents=[agent], tasks=[task], process=Process.sequential, verbose=True, stream=True)
    streaming = crew.kickoff()
    for chunk in streaming:
        _broadcast_agent(
            "thought",
            "sales_outreach",
            {
                "task": getattr(chunk, "task_name", ""),
                "agent_role": getattr(chunk, "agent_role", agent.role),
                "content": getattr(chunk, "content", "") or "",
                "chunk_type": str(getattr(chunk, "chunk_type", "TEXT")),
                "tool_call": getattr(chunk, "tool_call", None),
            },
        )
    result = streaming.result
    result_str = str(result.raw) if hasattr(result, "raw") else str(result)
    _broadcast_agent("finished", "sales_outreach", {"result_preview": result_str[:200]})
    return result_str
