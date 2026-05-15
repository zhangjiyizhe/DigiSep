# src/rule_engine_enhanced.py
# Rule Engine — ENHANCED condition for ablation experiments
#
# Active rules:  R-01, R-02, R-05 to R-10
# Disabled rules: R-03 (design error), R-04 (deprecated)
#
# Additions over baseline:
#   R-01 revised: conversion/reactive_separation fully exempt from ordering check
#   R-02 revised: expanded fouling-sensitive technique list (CRITICAL vs WARNING)
#   R-05 revised: neutralization→acidification pairing (CRITICAL); amine extraction
#                 back-extraction split by reagent type; precipitation→acidification CRITICAL
#   R-07 NEW: thermal degradation risk (distillation/evaporation after concentration)
#   R-08 NEW: reactive distillation requires prior concentration on dilute feeds
#   R-09 NEW: physical solvent extraction without pH control
#   R-10 NEW: adsorption/IX without desorption is operationally incomplete
#
# Citations per rule are documented in the message strings below.

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

AMINE_REAGENTS = {
    "trioctylamine", "alamine_336", "aliquat_336",
    "tri-n-octylamine", "tri_octyl_amine",
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
                    "the feed is already clarified — verify feed pre-treatment. "
                    "[Harrison et al. 2015; Belter et al. 1988]"
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
                        "invalid for cell-containing feeds (irreversible fouling). "
                        "[Belter et al. 1988]"
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
                        "cell removal should precede concentration. "
                        "[Belter et al. 1988]"
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
    CRITICAL_FOULING = {
        "electrodialysis", "bipolar_electrodialysis",
        "adsorption", "ion_exchange",
        "nanofiltration", "reverse_osmosis",
        "pervaporation",
    }
    WARNING_FOULING = {
        "activated_carbon_treatment",
        "crystallization",
        "molecular_distillation",
    }
    if first_tf in CRITICAL_FOULING and not has_cell_removal:
        flags.append({
            "rule_id": "R-02",
            "level":   "CRITICAL",
            "message": (
                f"First step is '{first_tf}' but route has no cell removal step. "
                f"'{first_tf}' is highly susceptible to fouling by cells, proteins, "
                "and debris in fermentation broth. Cell removal must precede this step. "
                "[Madzingaidzo et al. 2002; Novalic et al. 1996; Prochaska et al. 2018]"
            ),
        })
    if first_tf in WARNING_FOULING and not has_cell_removal:
        flags.append({
            "rule_id": "R-02",
            "level":   "WARNING",
            "message": (
                f"First step is '{first_tf}' applied directly to unclarified broth. "
                "Performance degradation from cell debris and macromolecules is expected. "
                "Consider adding microfiltration upstream. "
                "[Prochaska et al. 2018]"
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

    def has_technique(tf):
        return tf in techniques

    if has_key_containing("esterification") and not has_key_containing("hydrolysis"):
        flags.append({
            "rule_id": "R-05a",
            "level":   "CRITICAL",
            "message": (
                "Route contains esterification but no hydrolysis step. "
                "The lactic acid ester must be hydrolysed back to free lactic acid — "
                "product recovery is impossible without this step. "
                "[Asthana et al. 2006; Kolah et al. 2008]"
            ),
        })

    has_non_salting_extraction = any(
        "extraction" in s.get("technique_family", "")
        and s.get("technique_family", "") != "salting_out_extraction"
        for s in steps
    )
    has_back_extraction = (
        has_technique("back_extraction")
        or has_key_containing("back_extraction")
        or has_key_containing("stripping")
    )
    if has_non_salting_extraction and not has_back_extraction:
        uses_amine = any(
            any(amine in s.get("step_key", "").lower() for amine in AMINE_REAGENTS)
            for s in steps
            if "extraction" in s.get("technique_family", "")
        )
        if uses_amine:
            flags.append({
                "rule_id": "R-05b",
                "level":   "CRITICAL",
                "message": (
                    "Route uses amine-based reactive extraction but has no back-extraction step. "
                    "The LA–amine complex is thermally stable and cannot be recovered by "
                    "evaporation alone — back-extraction is chemically mandatory. "
                    "[Wasewar et al. 2004]"
                ),
            })
        else:
            flags.append({
                "rule_id": "R-05b",
                "level":   "WARNING",
                "message": (
                    "Route contains physical solvent extraction but no back-extraction step. "
                    "A dedicated back-extraction step is recommended for complete product recovery. "
                    "[Wasewar et al. 2004]"
                ),
            })

    has_precipitation = has_technique("precipitation") or has_technique("crystallization")
    has_acidification = (
        has_technique("acidification")
        or has_key_containing("acidification")
        or has_technique("thermal_decomposition")
    )
    if has_precipitation and not has_acidification:
        flags.append({
            "rule_id": "R-05c",
            "level":   "CRITICAL",
            "message": (
                "Route contains precipitation (likely Ca-lactate) but no acidification or "
                "thermal decomposition step. Without this step the product is an inorganic salt, not free LA. "
                "[Tejayadi & Cheryan 1995]"
            ),
        })

    has_neutralization = has_technique("neutralization") or has_key_containing("neutralization")
    if has_neutralization and not has_acidification:
        flags.append({
            "rule_id": "R-05d",
            "level":   "CRITICAL",
            "message": (
                "Route contains a neutralization step (producing lactate salt) but has no "
                "downstream acidification or thermal decomposition step. "
                "Acidification is mandatory to recover free LA. "
                "[Datta & Henry 2006; Tejayadi & Cheryan 1995]"
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


def _r07_thermal_degradation(
    steps: list[StepInfo],
    decision_rules_by_step: dict[str, DecisionRules] | None = None,
) -> list[Flag]:
    flags: list[Flag] = []
    if decision_rules_by_step is None:
        decision_rules_by_step = {}
    THERMAL_SENSITIVE = {
        "distillation", "vacuum_distillation",
        "evaporation", "multi_effect_evaporation", "vacuum_evaporation",
    }
    OLIGOMER_KEYWORDS = {"oligomer", "oligomeris", "dimerisation", "degradation"}
    concentration_seen = False
    for step in steps:
        tf        = step.get("technique_family", "")
        dsp_stage = step.get("dsp_stage", "")
        step_key  = step.get("step_key", "")
        if dsp_stage == "concentration":
            concentration_seen = True
        if tf in THERMAL_SENSITIVE and concentration_seen:
            step_rules = decision_rules_by_step.get(step_key, [])
            has_oligo_rule = any(
                any(kw in rule.get("phenomenon_name", "").lower()
                    or kw in rule.get("condition", "").lower()
                    for kw in OLIGOMER_KEYWORDS)
                for rule in step_rules
            )
            if not has_oligo_rule:
                flags.append({
                    "rule_id": "R-07",
                    "level":   "WARNING",
                    "message": (
                        f"Step '{step_key}' ({tf}) operates after concentration and is "
                        "thermally sensitive: LA oligomerises above 70–80°C at >50 wt% "
                        "concentration. Temperature control should be verified. "
                        "[Groot et al. 2010; Asthana et al. 2006]"
                    ),
                })
    return flags


def _r08_rd_requires_preconcentration(
    steps: list[StepInfo],
    feed_type: str = "",
) -> list[Flag]:
    flags: list[Flag] = []
    if feed_type not in ("fermentation_broth", "candy_waste_digestate_broth",
                         "glucose_fermentation_medium"):
        return flags
    has_rd = any(
        s.get("technique_family", "") == "reactive_distillation"
        or "reactive_distillation" in s.get("step_key", "")
        for s in steps
    )
    if not has_rd:
        return flags
    CONCENTRATION_STAGES = {
        "evaporation", "multi_effect_evaporation", "vacuum_evaporation",
        "reverse_osmosis", "distillation", "vacuum_distillation", "extraction",
    }
    rd_index = next(
        (i for i, s in enumerate(steps)
         if s.get("technique_family", "") == "reactive_distillation"
         or "reactive_distillation" in s.get("step_key", "")),
        None,
    )
    has_prior_concentration = any(
        s.get("technique_family", "") in CONCENTRATION_STAGES
        for s in steps[:rd_index]
    ) if rd_index is not None else False
    if not has_prior_concentration:
        flags.append({
            "rule_id": "R-08",
            "level":   "CRITICAL",
            "message": (
                "Reactive distillation (esterification) step present but no preceding "
                "concentration step found. Fermentation broth (~8–10 wt% LA) has excess "
                "water that suppresses esterification equilibrium. Preconcentration to "
                ">50 wt% LA is required for viable RD conversion. "
                "[Kolah et al. 2008; Joglekar et al. 2006]"
            ),
        })
    return flags


def _r09_extraction_ph_control(steps: list[StepInfo]) -> list[Flag]:
    flags: list[Flag] = []
    step_keys  = [s.get("step_key", "") for s in steps]
    techniques = [s.get("technique_family", "") for s in steps]

    def has_key_containing(substring):
        return any(substring in sk for sk in step_keys)

    has_physical_extraction = any(
        "extraction" in s.get("technique_family", "")
        and s.get("technique_family", "") not in ("back_extraction", "salting_out_extraction")
        and not any(amine in s.get("step_key", "").lower() for amine in AMINE_REAGENTS)
        for s in steps
    )
    has_ph_control = (
        "acidification" in techniques
        or has_key_containing("acidification")
        or has_key_containing("ph_adjust")
        or "neutralization" in techniques
    )
    if has_physical_extraction and not has_ph_control:
        flags.append({
            "rule_id": "R-09",
            "level":   "WARNING",
            "message": (
                "Route uses physical solvent extraction without a pH adjustment step. "
                "Distribution coefficient K_D < 0.1 at pH > pKa (3.86). "
                "Acidification before extraction is strongly recommended. "
                "[Wasewar et al. 2004; Datta & Henry 2006]"
            ),
        })
    return flags


def _r10_adsorption_requires_desorption(steps: list[StepInfo]) -> list[Flag]:
    flags: list[Flag] = []
    techniques = [s.get("technique_family", "") for s in steps]
    step_keys  = [s.get("step_key", "") for s in steps]

    def has_key_containing(substring):
        return any(substring in sk for sk in step_keys)

    ADSORPTION_TECHNIQUES = {"ion_exchange", "activated_carbon_treatment", "adsorption"}
    has_adsorption = any(tf in ADSORPTION_TECHNIQUES for tf in techniques)
    has_desorption = (
        "desorption" in techniques
        or has_key_containing("desorption")
        or has_key_containing("regenerat")
        or has_key_containing("elution")
    )
    if has_adsorption and not has_desorption:
        adsorption_steps = [
            s.get("step_key", s.get("technique_family", ""))
            for s in steps
            if s.get("technique_family", "") in ADSORPTION_TECHNIQUES
        ]
        flags.append({
            "rule_id": "R-10",
            "level":   "WARNING",
            "message": (
                f"Route contains adsorption/IX step(s) ({', '.join(adsorption_steps)}) "
                "but no desorption or regeneration step. Resin/carbon capacity is finite — "
                "continuous production requires a regeneration cycle. "
                "[Moldes et al. 2003]"
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
    decision_rules_by_step = decision_rules_by_step or {}
    all_flags: list[Flag] = []
    all_flags.extend(_r01_stage_sequence(steps, feed_type=feed_type))
    all_flags.extend(_r02_feed_compatibility(steps, feed_type=feed_type))
    all_flags.extend(_r03_decision_rule_constraints(steps, decision_rules_by_step))
    all_flags.extend(_r04_reactive_separation_position(steps))
    all_flags.extend(_r05_route_completeness(steps))
    all_flags.extend(_r06_verification_status(steps, verification))
    all_flags.extend(_r07_thermal_degradation(steps, decision_rules_by_step))
    all_flags.extend(_r08_rd_requires_preconcentration(steps, feed_type=feed_type))
    all_flags.extend(_r09_extraction_ph_control(steps))
    all_flags.extend(_r10_adsorption_requires_desorption(steps))
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
