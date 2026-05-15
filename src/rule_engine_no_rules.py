# src/rule_engine_no_rules.py
# Rule Engine — ABLATION: pass-through (no rules applied)
#
# All routes are returned as Tier 2 — Plausible with zero flags.
# Used by scripts/run_experiments.py for the no_rules ablation condition.
#
# Tier 1 = 0 by design: Tier 1 requires both verification AND no flags.
# Without rules, condition (b) cannot be evaluated → all routes are Tier 2.

from __future__ import annotations
from typing import Any

Flag          = dict[str, str]
StepInfo      = dict[str, Any]
RouteData     = dict[str, Any]
DecisionRules = list[dict]


def classify_route(flags: list, verified: bool = False) -> str:
    return "Tier 2 — Plausible"


def screen_route(
    route: RouteData,
    decision_rules_by_step: dict[str, DecisionRules] | None = None,
    feed_type: str = "",
) -> dict[str, Any]:
    return {
        "route_id":   route.get("route_id", "unknown"),
        "tier":       "Tier 2 — Plausible",
        "flags":      [],
        "num_flags":  0,
        "flag_summary": {"CRITICAL": 0, "WARNING": 0, "NOTE": 0},
    }


def screen_all_routes(
    routes: list[RouteData],
    decision_rules_by_step: dict[str, DecisionRules] | None = None,
    feed_type: str = "",
) -> list[dict[str, Any]]:
    return [
        screen_route(route, decision_rules_by_step, feed_type=feed_type)
        for route in routes
    ]
