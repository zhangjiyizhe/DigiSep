# src/feasibility_screener_node.py
# Agent 3: Feasibility Screener — LangGraph node wrapper
#
# Passes feed_type from state to screen_all_routes() so R-01 and R-02
# correctly skip recovery checks for pre-clarified feeds.
#
# Wraps the deterministic Rule Engine (src/rule_engine.py) as a LangGraph node.
# No LLM calls. No Neo4j queries. Pure Python.
#
# Input:  state["discovery_data"] + state["feed_type"]
# Output: state["screened_routes"]

from __future__ import annotations
from typing import Any

from src.state import DSPState
from src.rule_engine import screen_all_routes


def _build_decision_rules_by_step(routes: list[dict]) -> dict[str, list[dict]]:
    """
    Build step_key → DecisionRule list mapping from route step data.
    R-03 is disabled so this is unused, but kept for API compatibility.
    """
    rules_by_step: dict[str, list[dict]] = {}
    for route in routes:
        for step in route.get("steps", []):
            step_key = step.get("step_key", "")
            if step_key and step_key not in rules_by_step:
                rules_by_step[step_key] = step.get("decision_rules", [])
    return rules_by_step


def _extract_verification(route: dict) -> dict[str, Any]:
    v = route.get("verification", {})
    return {
        "verified":   v.get("verified", False),
        "pathway_id": v.get("pathway_id"),
        "paper_id":   v.get("paper_id"),
    }


def feasibility_screener(state: DSPState) -> dict:
    """
    Agent 3 (Feasibility Screener) — LangGraph node.

    Reads discovery_data["routes"] from state, runs R-01/R-02/R-05/R-06
    (R-03 disabled, R-04 deprecated), and stores results in screened_routes.
    """
    discovery_data = state.get("discovery_data")

    if not discovery_data:
        return {
            "screened_routes": [],
            "error": "Agent 3: discovery_data is missing from state.",
        }

    routes: list[dict] = discovery_data.get("routes", [])

    if not routes:
        return {
            "screened_routes": [],
            "error": "Agent 3: No routes in discovery_data to screen.",
        }

    # Pass feed_type so R-01/R-02 can skip checks for pre-clarified feeds
    feed_type = state.get("feed_type", "")

    decision_rules_by_step = _build_decision_rules_by_step(routes)

    raw_results: list[dict] = screen_all_routes(
        routes,
        decision_rules_by_step,
        feed_type=feed_type,
    )

    route_lookup = {r.get("route_id", ""): r for r in routes}

    screened_routes = []
    for result in raw_results:
        route_id       = result.get("route_id", "")
        original_route = route_lookup.get(route_id, {})
        verification   = _extract_verification(original_route)

        screened_routes.append({
            "route_id":    route_id,
            "tier":        result.get("tier", "Unknown"),
            "flags":       result.get("flags", []),
            "num_flags":   result.get("num_flags", 0),
            "flag_summary": result.get("flag_summary", {}),
            "verified":    verification["verified"],
            "pathway_id":  verification["pathway_id"],
            "paper_id":    verification["paper_id"],
        })

    tier1 = sum(1 for r in screened_routes if r["tier"].startswith("Tier 1"))
    tier2 = sum(1 for r in screened_routes if r["tier"].startswith("Tier 2"))
    tier3 = sum(1 for r in screened_routes if r["tier"].startswith("Tier 3"))
    print(
        f"[Agent 3] Screened {len(screened_routes)} routes: "
        f"Tier 1={tier1}, Tier 2={tier2}, Tier 3={tier3}"
    )

    return {"screened_routes": screened_routes}