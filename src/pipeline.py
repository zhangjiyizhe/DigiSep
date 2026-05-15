# src/pipeline.py
# LangGraph StateGraph — 4-agent pipeline wiring
#
# Pipeline: input_parser → route_discovery → feasibility_screener → report_generator
#
# Nodes:
#   input_parser         — Agent 1 (LLM, Pydantic structured output)
#   route_discovery      — Agent 2 (ReAct, Neo4j tools)
#   feasibility_screener — Agent 3 (Rule Engine, pure Python)
#   report_generator     — Agent 4 (LLM, single call)
#
# Entry points:
#   run_dsp_discovery(query, test_id)          — full pipeline (Agent 1 → 4)
#   run_dsp_discovery_from_cache(query, data)  — resume from Agent 2 cache
#                                                (Agent 3 → 4 only)

from __future__ import annotations
import json

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import InMemorySaver

from src.state import DSPState
from src.input_parser import input_parser
from src.agent_core import agent_route_discovery
from src.feasibility_screener_node import feasibility_screener
# Agent 4 (report_generator) is implemented in src/report_generator.py but is
# intentionally not wired here during the testing phase (T1–T4 experiments).
# Tier counts + flag statistics from Agent 3 are sufficient for all current metrics.
# Reconnect when full NL report generation is required.


# ---------------------------------------------------------------------------
# Conditional edge: after Agent 1
# ---------------------------------------------------------------------------
def after_input_parser(state: DSPState) -> str:
    if state.get("error"):
        return "end"
    if not state.get("feed_type") or not state.get("target_grade"):
        return "end"
    return "route_discovery"


# ---------------------------------------------------------------------------
# Conditional edge: after Agent 2
# ---------------------------------------------------------------------------
def after_route_discovery(state: DSPState) -> str:
    if state.get("error"):
        return "end"
    discovery = state.get("discovery_data")
    if not discovery:
        return "end"
    if discovery.get("total_routes_found", 0) == 0:
        return "zero_route_handler"
    return "feasibility_screener"


# ---------------------------------------------------------------------------
# Node: zero-route handler (Change 3)
# ---------------------------------------------------------------------------
def zero_route_handler(state: DSPState) -> dict:
    feed = state.get("feed_type", "unknown")
    return {
        "zero_route_message": (
            f"No separation routes found for feed type '{feed}'. "
            "The feed type was correctly identified but has no mapped purification "
            "routes in the current knowledge graph. "
            "Consider: (1) checking whether a related feed type has routes, "
            "(2) expanding the KG with additional literature for this substrate."
        )
    }


# ---------------------------------------------------------------------------
# Build full pipeline (Agent 1 → 2 → 3 → 4)
# ---------------------------------------------------------------------------
def build_pipeline() -> object:
    workflow = StateGraph(DSPState)

    workflow.add_node("input_parser",         input_parser)
    workflow.add_node("route_discovery",      agent_route_discovery)
    workflow.add_node("feasibility_screener", feasibility_screener)
    workflow.add_node("zero_route_handler",   zero_route_handler)
    # Agent 4 removed for T1 experiments

    workflow.set_entry_point("input_parser")

    workflow.add_conditional_edges(
        "input_parser",
        after_input_parser,
        {"route_discovery": "route_discovery", "end": END},
    )
    workflow.add_conditional_edges(
        "route_discovery",
        after_route_discovery,
        {
            "feasibility_screener": "feasibility_screener",
            "zero_route_handler":   "zero_route_handler",
            "end":                  END,
        },
    )

    workflow.add_edge("feasibility_screener", END)  # Agent 4 removed
    workflow.add_edge("zero_route_handler",   END)

    app = workflow.compile(checkpointer=InMemorySaver())
    return app


# ---------------------------------------------------------------------------
# Build resume pipeline (Agent 3 → 4 only, skips Agent 1 + 2)
# ---------------------------------------------------------------------------
def build_resume_pipeline() -> object:
    """
    Resume pipeline: Agent 3 only (skip Agent 1 + 2).
    discovery_data injected into initial state by caller.
    """
    workflow = StateGraph(DSPState)

    workflow.add_node("feasibility_screener", feasibility_screener)
    # Agent 4 removed

    workflow.set_entry_point("feasibility_screener")
    workflow.add_edge("feasibility_screener", END)

    app = workflow.compile(checkpointer=InMemorySaver())
    return app


# ---------------------------------------------------------------------------
# Singletons
# ---------------------------------------------------------------------------
pipeline_app        = build_pipeline()
resume_pipeline_app = build_resume_pipeline()


# ---------------------------------------------------------------------------
# Public entry point: full pipeline
# ---------------------------------------------------------------------------
def run_dsp_discovery(user_query: str, test_id: str | None = None) -> dict:
    """
    Full pipeline: Agent 1 → 2 → 3 (Agent 4 not wired during testing phase).

    Args:
        user_query: Natural language query.
        test_id:    Experiment ID (e.g. "T1-01") used for cache file naming.
                    If provided, Agent 2 raw output is saved to
                    outputs/cache/agent2_<test_id>.json automatically.

    Returns:
        Final state dict (contains discovery_data, screened_routes, error).
        state["report"] is None — Agent 4 not active in testing phase.
    """
    # Pass test_id through state so agent_core.py can use it for cache naming
    initial_state = {
        "messages":              [{"role": "user", "content": user_query}],
        "feed_type":             "",
        "target_grade":          "",
        "target_purity_min":     None,
        "verified_only":         False,
        "constraints":           None,
        "discovery_data":        None,
        "screened_routes":       None,
        "report":                None,
        "error":                 None,
        "test_id":               test_id,
        "ambiguous":             None,
        "alternative_feed_type": None,
        "zero_route_message":    None,
    }

    thread_id = test_id or "dsp_session_single"
    config    = {"configurable": {"thread_id": thread_id}}

    try:
        result = pipeline_app.invoke(initial_state, config=config)
        return result
    except Exception as e:
        return {
            "report":  None,
            "error":   f"Pipeline execution failed: {str(e)}",
            "discovery_data":   None,
            "screened_routes":  None,
        }


# ---------------------------------------------------------------------------
# Public entry point: resume from Agent 2 cache
# ---------------------------------------------------------------------------
def run_dsp_discovery_from_cache(
    user_query: str,
    discovery_data: dict,
) -> dict:
    """
    Resume pipeline: Agent 3 → 4 only (skip Agent 1 + 2).

    Injects pre-loaded discovery_data into the initial state and runs
    feasibility_screener → report_generator.

    Args:
        user_query:     Original NL query (used by Agent 4 for context).
        discovery_data: JSON dict previously saved from Agent 2 output.

    Returns:
        Final state dict (contains report, screened_routes, error).
    """
    # Extract basic fields from discovery_data for state context
    feed_type    = discovery_data.get("feed_type", "")
    target_grade = discovery_data.get("target_grade", "")
    purity_min   = discovery_data.get("query_params", {}).get("target_purity_min")

    initial_state = {
        "messages":              [{"role": "user", "content": user_query}],
        "feed_type":             feed_type,
        "target_grade":          target_grade,
        "target_purity_min":     purity_min,
        "verified_only":         False,
        "constraints":           None,
        "discovery_data":        discovery_data,
        "screened_routes":       None,
        "report":                None,
        "error":                 None,
        "test_id":               None,
        "ambiguous":             None,
        "alternative_feed_type": None,
        "zero_route_message":    None,
    }

    config = {"configurable": {"thread_id": "dsp_resume_session"}}

    try:
        result = resume_pipeline_app.invoke(initial_state, config=config)
        return result
    except Exception as e:
        return {
            "report":         None,
            "error":          f"Resume pipeline execution failed: {str(e)}",
            "screened_routes": None,
        }