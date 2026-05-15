# src/rule_engine.py
# Rule Engine — Deterministic feasibility screener for DSP routes
#
# Active rules:  R-01, R-02, R-05, R-06
# Disabled rules: R-03 (design error), R-04 (deprecated)
#
# Flag levels: CRITICAL > WARNING > NOTE
# Tier classification:
#   Tier 1 — Verified    : no CRITICAL, no WARNING, AND exact Pathway match
#   Tier 2 — Plausible   : WARNING present (no CRITICAL), OR no CRITICAL but unverified
#   Tier 3 — Problematic : CRITICAL present

from __future__ import annotations
from typing import Any


# ---------------------------------------------------------------------------
# Feed type metadata — used by R-01 and R-02
# ---------------------------------------------------------------------------

# Feeds that already have cells/particles removed BEFORE entering the DSP pipeline.
# R-01 "no recovery" check is skipped for these feeds.
# R-02 feed compatibility checks are also skipped (broth is already clarified).
PRE_CLARIFIED_FEEDS = {
    "whey_ultrafiltration_permeate",     # UF permeate — cells removed by UF
    "synthetic_lactic_acid_solution",    # Pure aqueous solution — no cells
    "biomass_derived_reaction_liquor",   # Chemical catalytic conversion product,
                                         # NOT a fermentation broth — no cells.
                                         # Already pre-treated with activated carbon
                                         # and filtration before DSP entry.
}

# Feeds that contain cells/particles and REQUIRE recovery as first DSP stage.
# (All other feeds default to requiring recovery checks.)
CELL_CONTAINING_FEEDS = {
    "fermentation_broth",
    "candy_waste_digestate_broth",
    "glucose_fermentation_medium",
    "biomass_derived_reaction_liquor",
}


# ---------------------------------------------------------------------------
# Type aliases for clarity
# ---------------------------------------------------------------------------
Flag        = dict[str, str]      # {rule_id, level, message}
StepInfo    = dict[str, Any]      # one step from route["steps"]
RouteData   = dict[str, Any]      # full route dict from get_all_routes
DecisionRules = list[dict]        # list of DecisionRule dicts (unused — R-03 disabled)


# ---------------------------------------------------------------------------
# R-01: DSP stage sequence sanity check
# ---------------------------------------------------------------------------
def _r01_stage_sequence(steps: list[StepInfo], feed_type: str = "") -> list[Flag]:
    """
    R-01: Check that dsp_stage sequence follows DSP logic.
    Valid general order: recovery → concentration → purification.
    auxiliary, conversion, reactive_separation, formulation are exempt.

    "no recovery" WARNING is only raised for cell-containing feeds.
    Pre-clarified feeds (whey UF permeate, synthetic solution) skip this check
    because they enter the DSP pipeline already free of cells and particles.

    Spec triggers:
      CRITICAL — purification before recovery (cell-containing feeds only)
      WARNING  — concentration before recovery (cell-containing feeds only)
      WARNING  — no recovery stage at all (cell-containing feeds only,
                 and not exempt by reactive extraction first step)
    """
    flags: list[Flag] = []

    # Pre-clarified feeds: skip all "no recovery" checks entirely
    is_pre_clarified = feed_type in PRE_CLARIFIED_FEEDS
    # Unknown feed type: apply checks conservatively (assume cell-containing)
    requires_recovery_checks = not is_pre_clarified

    EXEMPT = {"auxiliary", "conversion", "reactive_separation", "formulation"}
    ordered_stages = [
        s["dsp_stage"] for s in steps
        if s.get("dsp_stage") and s["dsp_stage"] not in EXEMPT
    ]

    has_recovery      = "recovery"      in ordered_stages
    has_concentration = "concentration" in ordered_stages
    has_purification  = "purification"  in ordered_stages

    # Reactive extraction exemption:
    # First step = extraction → acts as combined recovery+concentration,
    # so "no recovery" warning does not apply.
    first_technique = steps[0].get("technique_family", "") if steps else ""
    skip_no_recovery_check = (first_technique == "extraction")

    if requires_recovery_checks:
        # WARNING: no recovery stage at all
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

        # CRITICAL: purification before recovery
        if has_purification and has_recovery:
            first_pur_idx = next(
                i for i, s in enumerate(ordered_stages) if s == "purification"
            )
            first_rec_idx = next(
                i for i, s in enumerate(ordered_stages) if s == "recovery"
            )
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

        # WARNING: concentration before recovery
        if has_concentration and has_recovery:
            first_con_idx = next(
                i for i, s in enumerate(ordered_stages) if s == "concentration"
            )
            first_rec_idx = next(
                i for i, s in enumerate(ordered_stages) if s == "recovery"
            )
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


# ---------------------------------------------------------------------------
# R-02: Feed compatibility check
# ---------------------------------------------------------------------------
def _r02_feed_compatibility(steps: list[StepInfo], feed_type: str = "") -> list[Flag]:
    """
    R-02: Check if the first step is compatible with the feed type.

    Pre-clarified feeds skip all R-02 checks — there are no cells
    to cause fouling, so electrodialysis/adsorption/NF as first step is fine.

    Spec triggers (cell-containing feeds only):
      CRITICAL — first step is electrodialysis AND no prior cell removal
      CRITICAL — first step is adsorption/ion_exchange AND no prior cell removal
      WARNING  — first step is nanofiltration/reverse_osmosis AND no prior MF
    """
    flags: list[Flag] = []

    # Skip all checks for pre-clarified feeds
    if feed_type in PRE_CLARIFIED_FEEDS:
        return flags

    if not steps:
        return flags

    first_tf = steps[0].get("technique_family", "")

    recovery_techniques = {
        "microfiltration", "ultrafiltration", "centrifugation",
        "vacuum_filtration", "decanter",
    }
    route_techniques  = [s.get("technique_family", "") for s in steps]
    has_cell_removal  = any(tf in recovery_techniques for tf in route_techniques)

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


# ---------------------------------------------------------------------------
# R-03: DISABLED
# ---------------------------------------------------------------------------
def _r03_decision_rule_constraints(
    steps: list[StepInfo],
    decision_rules_by_step: dict[str, DecisionRules],
) -> list[Flag]:
    """
    R-03: DISABLED.

    Original intent: flag steps with :DesignConstraint DecisionRules as CRITICAL.
    Reason for disabling:
      1. DesignConstraint means "this step has operating constraints to respect"
         (e.g. T < 80°C to prevent oligomerization). It does NOT mean the route
         is infeasible — the constraint just needs to be followed in design.
      2. Labelling every constrained step as CRITICAL caused nearly all routes
         across all feed types to land in Tier 3, regardless of actual feasibility.
      3. ProcessStep nodes are global (shared across all FeedTypes), so constraints
         extracted from one paper (e.g. P05, fermentation_broth) incorrectly
         penalised routes from other feed types.

    Decision rules remain in the KG and will be surfaced in the NL report
    as informational annotations, not as Tier classification criteria.
    """
    return []   # Always returns empty — rule is disabled


# ---------------------------------------------------------------------------
# R-04: DEPRECATED
# ---------------------------------------------------------------------------
def _r04_reactive_separation_position(steps: list[StepInfo]) -> list[Flag]:
    """
    R-04: DEPRECATED. Retained as a no-op for rule-numbering continuity.
    """
    return []


# ---------------------------------------------------------------------------
# R-05: Route completeness check
# ---------------------------------------------------------------------------
def _r05_route_completeness(steps: list[StepInfo]) -> list[Flag]:
    """
    R-05: Check for missing paired steps that are scientifically required.

    Spec triggers:
      CRITICAL — esterification present but no hydrolysis
      WARNING  — extraction present but no back_extraction
      WARNING  — precipitation present but no acidification
    """
    flags: list[Flag] = []

    techniques = [s.get("technique_family", "") for s in steps]
    step_keys  = [s.get("step_key", "")         for s in steps]

    def has_key_containing(substring: str) -> bool:
        return any(substring in sk for sk in step_keys)

    # CRITICAL: esterification without hydrolysis
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

    # WARNING: extraction without back_extraction
    has_extraction = (
        "extraction" in techniques
        or has_key_containing("extraction")
    )
    has_back_extraction = (
        "back_extraction" in techniques
        or has_key_containing("back_extraction")
        or has_key_containing("stripping")
    )
    if has_extraction and not has_back_extraction:
        # Exclude salting_out_extraction — does not require back-extraction
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

    # WARNING: precipitation without acidification
    has_precipitation  = "precipitation" in techniques or "crystallization" in techniques
    has_acidification  = "acidification" in techniques or has_key_containing("acidification")
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


# ---------------------------------------------------------------------------
# R-06: Literature verification status
# ---------------------------------------------------------------------------
def _r06_verification_status(
    steps: list[StepInfo],
    verification: dict[str, Any],
) -> list[Flag]:
    """
    R-06: Flag routes based on their literature verification status.

    Spec triggers:
      WARNING — num_steps > 8 AND unverified
      NOTE    — unverified (short route)
    """
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


# ---------------------------------------------------------------------------
# 3-Tier classification
# ---------------------------------------------------------------------------
def classify_route(flags: list[Flag], verified: bool = False) -> str:
    """
    Tier 1 — Verified   : no CRITICAL, no WARNING, AND exact Pathway match
    Tier 2 — Plausible  : WARNING present (no CRITICAL), OR no CRITICAL but unverified
    Tier 3 — Problematic: CRITICAL present
    """
    levels = {f["level"] for f in flags}
    if "CRITICAL" in levels:
        return "Tier 3 — Problematic"
    if "WARNING" in levels:
        return "Tier 2 — Plausible"
    if not verified:
        return "Tier 2 — Plausible"
    return "Tier 1 — Verified"


# ---------------------------------------------------------------------------
# Main entry point: screen_route
# ---------------------------------------------------------------------------
def screen_route(
    route: RouteData,
    decision_rules_by_step: dict[str, DecisionRules] | None = None,
    feed_type: str = "",
) -> dict[str, Any]:
    """
    Run all active rules (R-01, R-02, R-05, R-06) against a single route.

    Args:
        route:                  One route dict from get_all_routes output.
                                Must contain: steps (list), verification (dict).
                                Each step must contain: step_key, dsp_stage,
                                technique_family.
        decision_rules_by_step: Unused (R-03 disabled). Kept for API compatibility.
        feed_type:              FeedType.name — used by R-01 and R-02 to determine
                                whether recovery checks apply.

    Returns:
        {route_id, tier, flags, num_flags, flag_summary}
    """
    steps:        list[StepInfo] = route.get("steps", [])
    verification: dict           = route.get("verification", {})
    route_id:     str            = route.get("route_id", "unknown")
    verified:     bool           = verification.get("verified", False)

    all_flags: list[Flag] = []
    all_flags.extend(_r01_stage_sequence(steps, feed_type=feed_type))
    all_flags.extend(_r02_feed_compatibility(steps, feed_type=feed_type))
    # R-03 disabled — call kept for traceability, always returns []
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
        "route_id":    route_id,
        "tier":        tier,
        "flags":       all_flags,
        "num_flags":   len(all_flags),
        "flag_summary": flag_summary,
    }


# ---------------------------------------------------------------------------
# Batch entry point: screen_all_routes
# ---------------------------------------------------------------------------
def screen_all_routes(
    routes: list[RouteData],
    decision_rules_by_step: dict[str, DecisionRules] | None = None,
    feed_type: str = "",
) -> list[dict[str, Any]]:
    """
    Screen a list of routes. Returns results in same order as input.

    Args:
        routes:                 List of route dicts from get_all_routes.
        decision_rules_by_step: Unused (R-03 disabled). Kept for API compatibility.
        feed_type:              Passed to each screen_route call for R-01/R-02.
    """
    return [
        screen_route(route, decision_rules_by_step, feed_type=feed_type)
        for route in routes
    ]