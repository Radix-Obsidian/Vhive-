"""
LangGraph state definitions and routing for Vhive AURA workflow.
Every node that makes external API calls has a conditional edge to handle_error.
Each node logs its execution to SQLite via VhiveDB and writes daily notes to memory.
"""

from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from vhive_core.db import db
from vhive_core.memory import memory


class VhiveState(TypedDict, total=False):
    """State schema for the AURA workflow."""

    run_id: str
    research_data: str
    product_code: str
    deployment_status: str
    outreach_drafts: str
    errors: list[str]
    should_retry: bool
    retry_count: int


def _get_retry_count(state: VhiveState) -> int:
    """Get current retry count, default 0."""
    return state.get("retry_count", 0)


def _route_after_node(state: VhiveState) -> Literal["handle_error", "continue"]:
    """
    Route to handle_error if errors occurred, else continue to next node.
    __continue__ is a special value for conditional edges - we use path_map.
    """
    if state.get("errors"):
        return "handle_error"
    return "continue"


def _route_after_error(state: VhiveState) -> Literal["research", "end"]:
    """After handle_error: retry research (up to limit) or end."""
    MAX_RETRIES = 3
    retries = _get_retry_count(state)
    if retries < MAX_RETRIES and state.get("should_retry", True):
        return "retry"
    return "end"


def _create_graph():
    """Build and return the compiled StateGraph."""
    from vhive_core.core.crews import (
        run_deploy_crew,
        run_outreach_crew,
        run_product_build_crew,
        run_research_crew,
    )

    graph = StateGraph(VhiveState)

    # --- Logged node wrapper ---

    def _logged_node(node_name: str, crew_fn, result_key: str):
        """Wrap a crew function with DB step logging."""

        def node(state: VhiveState) -> dict:
            run_id = state.get("run_id", "")
            step_id = db.log_step_start(run_id, node_name) if run_id else ""
            try:
                result = crew_fn(state)
                if step_id:
                    db.log_step_end(step_id, "completed", str(result)[:500])
                return {result_key: result, "errors": []}
            except Exception as e:
                if step_id:
                    db.log_step_end(step_id, "failed", str(e)[:500])
                return {"errors": [str(e)], "should_retry": True}

        return node

    # --- Nodes ---

    from vhive_core.tools.shopify_tool import extract_product_title, extract_shopify_gid

    research_node = _logged_node("research", run_research_crew, "research_data")
    product_build_node = _logged_node("product_build", run_product_build_crew, "product_code")
    _raw_deploy_node = _logged_node("deploy", run_deploy_crew, "deployment_status")

    def deploy_node(state: VhiveState) -> dict:
        """Deploy + record product in DB for revenue tracking."""
        result = _raw_deploy_node(state)
        deploy_status = result.get("deployment_status", "")
        if deploy_status and not result.get("errors"):
            gid = extract_shopify_gid(str(deploy_status))
            title = extract_product_title(str(deploy_status)) or "Untitled"
            if gid:
                db.add_product(
                    title=title,
                    shopify_gid=gid,
                    run_id=state.get("run_id", ""),
                )
        return result

    outreach_node = _logged_node("outreach", run_outreach_crew, "outreach_drafts")

    def handle_error_node(state: VhiveState) -> dict:
        """Pause and retry logic. Increment retry count."""
        retries = _get_retry_count(state)
        return {"retry_count": retries + 1}

    # --- Add nodes ---
    graph.add_node("research", research_node)
    graph.add_node("product_build", product_build_node)
    graph.add_node("deploy", deploy_node)
    graph.add_node("outreach", outreach_node)
    graph.add_node("handle_error", handle_error_node)

    # --- Edges ---
    graph.add_edge(START, "research")

    graph.add_conditional_edges(
        "research",
        _route_after_node,
        path_map={"handle_error": "handle_error", "continue": "product_build"},
    )

    graph.add_conditional_edges(
        "product_build",
        _route_after_node,
        path_map={"handle_error": "handle_error", "continue": "deploy"},
    )

    graph.add_conditional_edges(
        "deploy",
        _route_after_node,
        path_map={"handle_error": "handle_error", "continue": "outreach"},
    )

    graph.add_conditional_edges(
        "outreach",
        _route_after_node,
        path_map={"handle_error": "handle_error", "continue": END},
    )

    graph.add_conditional_edges(
        "handle_error",
        _route_after_error,
        path_map={"retry": "research", "end": END},
    )

    return graph.compile()


# Compile graph on module load
workflow = _create_graph()
