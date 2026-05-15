# src/rule_engine_baseline.py
# Rule Engine — BASELINE condition for ablation experiments
#
# Active rules:  R-01, R-02, R-05, R-06
# Disabled rules: R-03 (design error — DesignConstraint ≠ infeasible),
#                 R-04 (deprecated)
#
# Verbatim copy of src/rule_engine.py — exists as a separate module so
# scripts/run_experiments.py can monkey-patch src.rule_engine to point at
# the chosen condition without modifying any source file.

from __future__ import annotations
from typing import Any


PRE_CLARIFIED_FEEDS = {
    "whey_ultrafiltration_permeate",
    "synthetic_lactic_acid_solution",
    "biomass_derived_reaction_liquor",
}

CELL_CONTAINING_FEEDS = {
    "fermentation_broth",
    "candy_waste_digestate_broth",
    "glucose_fermentation_medium",
    "biomass_derived_reaction_liquor",
}

Flag          = dict[str, str]
StepInfo      = dict[str, Any]
RouteData     = dict[str, Any]
DecisionRules = list[dict]


def _r01_stage_sequence(steps: list[StepInfo], feed_type: str = "") -> list[Flag]:
    flags: list[Flag] = []
    is_pre_clarified         = feed_type in PRE_CLARIFIED_FEEDS
    requires_recovery_checks = not is_pre_clarified
    EXEMPT = {"auxiliary", "conversion", "reactive_separation", "formulation"}
    ordered_stages = [
        s["dsp_stage"] for s in steps
        if s.get("dsp_stage") and s["dsp_stage"] not in EXEMPT
    ]
    has_recovery      = "recovery"      in ordered_stages
    has_concentration = "concentration" in ordered_stages
    has_purification  = "purification"  in ordered_stages
    first_technique        = steps[0].get("technique_family", "") if steps else ""
    skip_no_recovery_check = (first_technique == "extraction")
    if requires_recovery_checks:
        if (not skip_no_recovery_check
                and not has_recovery
                and (has_concentration or has_purification)):
            flags.append({
                "rule_id": "R-01",
                "level":   "WARNING",
                "message": (
                    "Route has no recovery stage (cell removal). "
                    "Starting directly from concentration or purification assumes "
                    "the feed is already clarified — verify feed pre-treatment."
                ),
            })
        if has_purification and has_recovery:
            first_pur_idx = next(i for i, s in enumerate(ordered_stages) if s == "purification")
            first_rec_idx = next(i for i, s in enumerate(ordered_stages) if s == "recovery")
            if first_pur_idx < first_rec_idx:
                flags.append({
                    "rule_id": "R-01",
                    "level":   "CRITICAL",
                    "message": (
                        "Purification step appears before recovery step in route sequence. "
                        "Dissolved-impurity removal before cell removal is scientifically "
                        "invalid for cell-containing feeds."
                    ),
                })
        if has_concentration and has_recovery:
            first_con_idx = next(i for i, s in enumerate(ordered_stages) if s == "concentration")
            first_rec_idx = next(i for i, s in enumerate(ordered_stages) if s == "recovery")
            if first_con_idx < first_rec_idx:
                flags.append({
                    "rule_id": "R-01",
                    "level":   "WARNING",
                    "message": (
                        "Concentration step appears before recovery step. "
                        "Concentrating a cell-containing broth may cause fouling — "
                        "cell removal should precede concentration."
                    ),
                })
    return flags


def _r02_feed_compatibility(steps: list[StepInfo], feed_type: str = "") -> list[Flag]:
    flags: list[Flag] = []
    if feed_type in PRE_CLARIFIED_FEEDS:
        return flags
    if not steps:
        return flags
    first_tf = steps[0].get("technique_family", "")
    recovery_techniques = {
        "microfiltration", "ultrafiltration", "centrifugation",
        "vacuum_filtration", "decanter",
    }
    route_techniques = [s.get("technique_family", "") for s in steps]
    has_cell_removal = any(tf in recovery_techniques for tf in route_techniques)
    if first_tf in ("electrodialysis", "bipolar_electrodialysis") and not has_cell_removal:
        flags.append({
            "rule_id": "R-02",
            "level":   "CRITICAL",
            "message": (
                f"First step is '{first_tf}' but route has no cell removal step. "
                "Electrodialysis membranes foul rapidly with cell-containing broth. "
                "Microfiltration or centrifugation must precede electrodialysis."
            ),
        })
    if first_tf in ("adsorption", "ion_exchange") and not has_cell_removal:
        flags.append({
            "rule_id": "R-02",
            "level":   "CRITICAL",
            "message": (
                f"First step is '{first_tf}' but route has no cell removal step. "
                "Resin fouling by cell mass will severely reduce adsorption performance. "
                "Cell removal must precede adsorption."
            ),
        })
    if first_tf in ("nanofiltration", "reverse_osmosis") and not has_cell_removal:
        flags.append({
            "rule_id": "R-02",
            "level":   "WARNING",
            "message": (
                f"First step is '{first_tf}' but route has no microfiltration step. "
                "NF/RO membranes are susceptible to biofouling from cell debris. "
                "Consider adding microfiltration upstream."
            ),
        })
    return flags


def _r03_decision_rule_constraints(steps, decision_rules_by_step):
    return []


def _r04_reactive_separation_position(steps):
    return []


def _r05_route_completeness(steps: list[StepInfo]) -> list[Flag]:
    flags: list[Flag] = []
    techniques = [s.get("technique_family", "") for s in steps]
    step_keys  = [s.get("step_key", "")         for s in steps]

    def has_key_containing(substring):
        return any(substring in sk for sk in step_keys)

    if has_key_containing("esterification") and not has_key_containing("hydrolysis"):
        flags.append({
            "rule_id": "R-05",
            "level":   "CRITICAL",
            "message": (
                "Route contains esterification but no hydrolysis step. "
                "The lactic acid ester must be hydrolysed back to free lactic acid "
                "to recover the product — this step is missing."
            ),
        })
    has_extraction = (
        "extraction" in techniques or has_key_containing("extraction")
    )
    has_back_extraction = (
        "back_extraction" in techniques
        or has_key_containing("back_extraction")
        or has_key_containing("stripping")
    )
    if has_extraction and not has_back_extraction:
        non_salting = any(
            "extraction" in s.get("technique_family", "")
            and s.get("technique_family", "") != "salting_out_extraction"
            for s in steps
        )
        if non_salting:
            flags.append({
                "rule_id": "R-05",
                "level":   "WARNING",
                "message": (
                    "Route contains extraction but no back-extraction step. "
                    "Lactic acid must be stripped back from the organic phase "
                    "to recover the aqueous product stream."
                ),
            })
    has_precipitation = "precipitation" in techniques or "crystallization" in techniques
    has_acidification = "acidification" in techniques or has_key_containing("acidification")
    if has_precipitation and not has_acidification:
        flags.append({
            "rule_id": "R-05",
            "level":   "WARNING",
            "message": (
                "Route contains precipitation (likely Ca-lactate) but no acidification step. "
                "Calcium lactate must be acidified (e.g. with H2SO4) to release free "
                "lactic acid — this step appears to be missing."
            ),
        })
    return flags


def _r06_verification_status(steps: list[StepInfo], verification: dict) -> list[Flag]:
    flags: list[Flag] = []
    verified  = verification.get("verified", False)
    num_steps = len(steps)
    if not verified:
        if num_steps > 8:
            flags.append({
                "rule_id": "R-06",
                "level":   "WARNING",
                "message": (
                    f"Route has {num_steps} steps and is NOT verified by any single "
                    "literature source. Long cross-paper combinations carry significant "
                    "uncertainty — intermediate stream compatibility is unconfirmed."
                ),
            })
        else:
            flags.append({
                "rule_id": "R-06",
                "level":   "NOTE",
                "message": (
                    "Route is a cross-paper combination not verified by any single "
                    "literature source. Individual steps are literature-supported but "
                    "the complete sequence has not been demonstrated as a whole."
                ),
            })
    return flags


def classify_route(flags: list[Flag], verified: bool = False) -> str:
    levels = {f["level"] for f in flags}
    if "CRITICAL" in levels:
        return "Tier 3 — Problematic"
    if "WARNING" in levels:
        return "Tier 2 — Plausible"
    if not verified:
        return "Tier 2 — Plausible"
    return "Tier 1 — Verified"


def screen_route(
    route: RouteData,
    decision_rules_by_step: dict[str, DecisionRules] | None = None,
    feed_type: str = "",
) -> dict[str, Any]:
    steps        = route.get("steps", [])
    verification = route.get("verification", {})
    route_id     = route.get("route_id", "unknown")
    verified     = verification.get("verified", False)
    all_flags: list[Flag] = []
    all_flags.extend(_r01_stage_sequence(steps, feed_type=feed_type))
    all_flags.extend(_r02_feed_compatibility(steps, feed_type=feed_type))
    all_flags.extend(_r03_decision_rule_constraints(steps, decision_rules_by_step or {}))
    all_flags.extend(_r04_reactive_separation_position(steps))
    all_flags.extend(_r05_route_completeness(steps))
    all_flags.extend(_r06_verification_status(steps, verification))
    tier = classify_route(all_flags, verified=verified)
    flag_summary = {
        "CRITICAL": sum(1 for f in all_flags if f["level"] == "CRITICAL"),
        "WARNING":  sum(1 for f in all_flags if f["level"] == "WARNING"),
        "NOTE":     sum(1 for f in all_flags if f["level"] == "NOTE"),
    }
    return {
        "route_id":     route_id,
        "tier":         tier,
        "flags":        all_flags,
        "num_flags":    len(all_flags),
        "flag_summary": flag_summary,
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
