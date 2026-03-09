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
    """Writes code for digital products. Uses coding LLM. Has OpenHands for execution."""
    return Agent(
        role="Python Developer",
        goal="Write clean, working code for digital products (e.g., templates, scripts) and validate via sandbox",
        backstory="Senior developer who ships fast and tests in isolated environments.",
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
            f"Based on this research: {research}. "
            "Write a practical digital product that DOES NOT require Twitter/social media API credentials. "
            "Good examples: a Python productivity script, a data analysis template, a compliance checklist generator, "
            "a markdown report template, or a simple automation tool. "
            "The product should be self-contained and actually runnable. Execute it in the sandbox to validate. "
            "Return the working code and execution output."
        ),
        agent=agent,
        expected_output="Working code and sandbox execution output.",
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


def run_deploy_crew(state: dict[str, Any]) -> str:
    """State 3: Deploy via Shopify tool."""
    tools = _get_tools()
    if "shopify" not in tools:
        return "Shopify tool not available - deploy skipped."

    shopify_tool = tools["shopify"]
    product_code = state.get("product_code", "")

    try:
        result = shopify_tool.run(
            title="AURA Digital Product",
            description=product_code[:500] if product_code else "Digital product from AURA",
            product_type="digital",
        )
        return str(result)
    except Exception as e:
        # Deploy failure (e.g. auth error) is non-fatal — log and continue to outreach
        return f"Deploy skipped: {e}"


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
            "STEP 2 — OPTIONAL iMessage: ONLY send iMessage if you have been given a real verified phone number. "
            "NEVER invent, guess, or use placeholder phone numbers like +12025551234 or any 555-xxxx number. "
            "If no real phone numbers are provided, skip iMessage entirely.\n\n"
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
