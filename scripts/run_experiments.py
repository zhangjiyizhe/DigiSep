# scripts/run_experiments.py
# Experiment batch runner for T1–T4 ablation and feed-type experiments.
#
# Usage:
#   python scripts/run_experiments.py --run-t1 [--rule-engine baseline|enhanced|no_rules]
#   python scripts/run_experiments.py --run-t2 [--rule-engine ...]
#   python scripts/run_experiments.py --run-t3 [--rule-engine ...]
#   python scripts/run_experiments.py --run-t4 [--rule-engine ...]
#   python scripts/run_experiments.py --rerun T1-03 T1-07 [--rule-engine ...]
#   python scripts/run_experiments.py --progress [--rule-engine ...]
#
# --rule-engine defaults to "baseline" if omitted.
# Results are saved to experiments/<series>_results_<rule_engine>.json
# Agent 2 cache is shared across rule engine conditions — only Agent 3 changes.

import sys
import os
import json
import time
import importlib
import types
from datetime import datetime

# Ensure the project root is on sys.path so that `src.*` and `config`
# imports work regardless of the current working directory.
_SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
_PROJECT_DIR = os.path.dirname(_SCRIPT_DIR)   # project root (holds src/ and config.py)
if _PROJECT_DIR not in sys.path:
    sys.path.insert(0, _PROJECT_DIR)

# ---------------------------------------------------------------------------
# Rule engine selection — must happen BEFORE any pipeline import
# ---------------------------------------------------------------------------
_VALID_ENGINES = {"no_rules", "baseline", "enhanced"}
_ENGINE_MODULE_MAP = {
    "no_rules": "src.rule_engine_no_rules",
    "baseline": "src.rule_engine_baseline",
    "enhanced": "src.rule_engine_enhanced",
}


def _parse_rule_engine_arg(argv: list[str]) -> str:
    if "--rule-engine" in argv:
        idx = argv.index("--rule-engine")
        if idx + 1 < len(argv):
            engine = argv[idx + 1].lower()
            if engine not in _VALID_ENGINES:
                print(f"Error: --rule-engine must be one of {sorted(_VALID_ENGINES)}")
                sys.exit(1)
            return engine
        print("Error: --rule-engine requires a value (no_rules / baseline / enhanced)")
        sys.exit(1)
    return "baseline"


RULE_ENGINE = _parse_rule_engine_arg(sys.argv[1:])

_engine_mod = importlib.import_module(_ENGINE_MODULE_MAP[RULE_ENGINE])
_shim = types.ModuleType("src.rule_engine")
_shim.screen_all_routes = _engine_mod.screen_all_routes
_shim.screen_route       = _engine_mod.screen_route
_shim.classify_route     = _engine_mod.classify_route
sys.modules["src.rule_engine"] = _shim

print(f"[Rule Engine] Active: {RULE_ENGINE} ({_ENGINE_MODULE_MAP[RULE_ENGINE]})")

from src.pipeline import run_dsp_discovery, run_dsp_discovery_from_cache


# ---------------------------------------------------------------------------
# Experiment matrices
# ---------------------------------------------------------------------------

T1_EXPERIMENTS = [
    {
        "test_id":   "T1-01",
        "feed_type": "fermentation_broth",
        "grade":     "50wt",
        "query":     "Find all lactic acid purification routes from fermentation broth with at least 50 wt% purity.",
    },
    {
        "test_id":   "T1-02",
        "feed_type": "fermentation_broth",
        "grade":     "82wt",
        "query":     "Find all lactic acid purification routes from fermentation broth with at least 82 wt% purity.",
    },
    {
        "test_id":   "T1-03",
        "feed_type": "fermentation_broth",
        "grade":     "88wt",
        "query":     "Find all lactic acid purification routes from fermentation broth with at least 88 wt% purity.",
    },
    {
        "test_id":   "T1-04",
        "feed_type": "biomass_derived_reaction_liquor",
        "grade":     "50wt",
        "query":     "Find all lactic acid purification routes from biomass-derived reaction liquor with at least 50 wt% purity.",
    },
    {
        "test_id":   "T1-05",
        "feed_type": "biomass_derived_reaction_liquor",
        "grade":     "82wt",
        "query":     "Find all lactic acid purification routes from biomass-derived reaction liquor with at least 82 wt% purity.",
    },
    {
        "test_id":   "T1-06",
        "feed_type": "biomass_derived_reaction_liquor",
        "grade":     "88wt",
        "query":     "Find all lactic acid purification routes from biomass-derived reaction liquor with at least 88 wt% purity.",
    },
    {
        "test_id":   "T1-07",
        "feed_type": "whey_ultrafiltration_permeate",
        "grade":     "50wt",
        "query":     "Find all lactic acid purification routes from whey ultrafiltration permeate with at least 50 wt% purity.",
    },
    {
        "test_id":   "T1-08",
        "feed_type": "whey_ultrafiltration_permeate",
        "grade":     "82wt",
        "query":     "Find all lactic acid purification routes from whey ultrafiltration permeate with at least 82 wt% purity.",
    },
    {
        "test_id":   "T1-09",
        "feed_type": "whey_ultrafiltration_permeate",
        "grade":     "88wt",
        "query":     "Find all lactic acid purification routes from whey ultrafiltration permeate with at least 88 wt% purity.",
    },
]

T2_EXPERIMENTS = [
    {
        "test_id":            "T2-01",
        "expected_feed_type": "fermentation_broth",
        "grade":              "88wt",
        "query": (
            "My feed stream contains lactic acid at 8.36 mol%, water at 90.58 mol%, "
            "and succinic acid at 1.06 mol%. Temperature 35°C. "
            "I want polymer-grade LA (88 wt%)."
        ),
    },
    {
        "test_id":            "T2-02",
        "expected_feed_type": "fermentation_broth",
        "grade":              "88wt",
        "query": (
            "Aqueous stream: LA approximately 8 mol%, water around 91 mol%, "
            "trace organic acids about 1 mol% total. From bacterial fermentation at 37°C. "
            "Target 88wt% purity."
        ),
    },
    {
        "test_id":            "T2-03",
        "expected_feed_type": "fermentation_broth",
        "grade":              "88wt",
        "query": (
            "Feed composition: roughly 8% lactic acid, 90% water, "
            "and about 1% each of succinic acid and glucose. "
            "Comes from a standard Lactobacillus fermentation. Want 88wt% product."
        ),
    },
    {
        "test_id":            "T2-04",
        "expected_feed_type": "biomass_derived_reaction_liquor",
        "grade":              "88wt",
        "query": (
            "Liquid stream containing lactic acid and water, approximately 10:90 ratio by moles, "
            "plus trace amounts of xylose (~2%) and furfural (~0.5%) "
            "from lignocellulosic biomass processing. Target 88wt%."
        ),
    },
    {
        "test_id":            "T2-05",
        "expected_feed_type": "synthetic_lactic_acid_solution",
        "grade":              "88wt",
        "query": (
            "Aqueous LA solution: roughly 90 mol% water, 10 mol% lactic acid. "
            "Synthetically prepared — no fermentation, no impurities. Want 88wt%."
        ),
    },
    {
        "test_id":            "T2-06",
        "expected_feed_type": "whey_ultrafiltration_permeate",
        "grade":              "50wt",
        "query": (
            "Feed: water 85 mol%, lactic acid 6 mol%, lactose 4 mol%, minerals ~5 mol%. "
            "From dairy processing — cheese whey after protein removal. "
            "Food-grade target 50wt%."
        ),
    },
]

T3_EXPERIMENTS = [
    {
        "test_id":            "T3-01",
        "expected_feed_type": "fermentation_broth",
        "grade":              "88wt",
        "query": (
            "Feed: lactic acid 8 mol%, water 89 mol%, succinic acid 1 mol%, "
            "formic acid 2 mol% (unusual side product from fermentation). "
            "pH 4.2, 35°C. Target 88wt%."
        ),
    },
    {
        "test_id":            "T3-02",
        "expected_feed_type": "fermentation_broth",
        "grade":              "88wt",
        "query": (
            "Fermentation broth: LA 8 mol%, water 90 mol%, "
            "ethanol 2 mol% from mixed-culture contamination. "
            "35°C. 88wt% target."
        ),
    },
    {
        "test_id":            "T3-03",
        "expected_feed_type": "fermentation_broth",
        "grade":              "88wt",
        "query": (
            "Feed: water 83 mol%, lactic acid 15 mol%, succinic acid 1 mol%, acetic acid 1 mol%. "
            "Pre-concentrated fermentation broth after partial evaporation. 88wt% target."
        ),
    },
    {
        "test_id":            "T3-04",
        "expected_feed_type": "whey_ultrafiltration_permeate",
        "grade":              "50wt",
        "query": (
            "Cheese whey permeate: water 88 mol%, LA 6 mol%, lactose 4 mol%, "
            "citric acid 2 mol% (atypical for standard whey). Food grade 50wt%."
        ),
    },
    {
        "test_id":            "T3-05",
        "expected_feed_type": "biomass_derived_reaction_liquor",
        "grade":              "88wt",
        "query": (
            "Feed stream: water 78 mol%, lactic acid 12 mol%, xylose 5 mol%, "
            "furfural 3 mol%, acetic acid 2 mol%. Biomass origin. 88wt% target."
        ),
    },
    {
        "test_id":            "T3-06",
        "expected_feed_type": "UNKNOWN",
        "grade":              "88wt",
        "query": (
            "Aqueous mixture: water 60 mol%, lactic acid 25 mol%, glycerol 15 mol%. "
            "From biodiesel co-product stream mixed with LA fermentation output. 88wt%."
        ),
    },
]

T4_EXPERIMENTS = [
    {
        "test_id":            "T4-01",
        "expected_feed_type": "UNKNOWN",
        "grade":              "88wt",
        "query": (
            "My fermentation broth contains succinic acid as the main product (~8 mol%), "
            "water 90 mol%, trace glucose. "
            "I want 99% pure succinic acid for polymer applications."
        ),
    },
    {
        "test_id":            "T4-02",
        "expected_feed_type": "UNKNOWN",
        "grade":              "88wt",
        "query": (
            "Ethanol fermentation broth: ethanol 8 mol%, water 90 mol%, CO2 traces. "
            "Yeast fermentation at 30°C. Target: fuel-grade ethanol 99.5 mol%."
        ),
    },
    {
        "test_id":            "T4-03",
        "expected_feed_type": "UNKNOWN",
        "grade":              "50wt",
        "query": (
            "Citric acid production broth: citric acid 10 mol%, water 88 mol%, "
            "oxalic acid 2 mol%. Aspergillus niger fermentation. "
            "Target: food-grade citric acid."
        ),
    },
    {
        "test_id":            "T4-04",
        "expected_feed_type": "UNKNOWN",
        "grade":              "88wt",
        "query": (
            "Crude glycerol from biodiesel transesterification: glycerol 60 mol%, "
            "methanol 20 mol%, water 15 mol%, fatty acid salts 5 mol%. "
            "Target: USP-grade glycerol 99.5%."
        ),
    },
]

T2E_EXPERIMENTS = [
    # ── Sub-group A: Numerical (wt% / g/L values given) ──────────────────
    {
        "test_id":            "T2E-N-01",
        "expected_feed_type": "fermentation_broth",
        "grade":              "88wt",
        "numerical_mode":     True,
        "query": (
            "Feed stream composition: lactic acid 8.36 wt%, water 90.58 wt%, "
            "succinic acid 1.06 wt%. Temperature 35°C, pH 3.9. "
            "Produced by standard Lactobacillus fermentation. Target: polymer-grade LA 88 wt%."
        ),
    },
    {
        "test_id":            "T2E-N-02",
        "expected_feed_type": "fermentation_broth",
        "grade":              "50wt",
        "numerical_mode":     True,
        "query": (
            "My fermentation output: approximately 8.4 wt% lactic acid, "
            "90.5 wt% water, 1.1 wt% succinic acid, trace glucose. "
            "Target: food-grade LA 50 wt%."
        ),
    },
    {
        "test_id":            "T2E-N-03",
        "expected_feed_type": "fermentation_broth",
        "grade":              "88wt",
        "numerical_mode":     True,
        "query": (
            "Aqueous broth: LA ~8%, water ~91%, organic acid impurities ~1% "
            "(succinic acid dominant). From bacterial LA fermentation at 37°C with NaOH neutralisation. "
            "Want 88 wt% pure lactic acid."
        ),
    },
    {
        "test_id":            "T2E-N-04",
        "expected_feed_type": "glucose_fermentation_medium",
        "grade":              "50wt",
        "numerical_mode":     True,
        "query": (
            "Feed from Bacillus coagulans fermentation at 55°C: lactic acid ~9 wt%, "
            "glucose <0.2 wt% (residual), inorganic ions (Ca, K, Na) ~2.7 wt%, water balance. "
            "CaCO3 used for pH control. Target: 50 wt% food-grade LA."
        ),
    },
    {
        "test_id":            "T2E-N-05",
        "expected_feed_type": "glucose_fermentation_medium",
        "grade":              "88wt",
        "numerical_mode":     True,
        "query": (
            "Thermophilic B. coagulans fermentation on pure glucose medium. "
            "LA concentration approximately 90 g/L (roughly 9 wt%), "
            "residual glucose <2 g/L, corn steep liquor powder as nutrient. "
            "Target 88 wt% polymer-grade LA."
        ),
    },
    {
        "test_id":            "T2E-N-06",
        "expected_feed_type": "acid_whey_fermentation_broth",
        "grade":              "50wt",
        "numerical_mode":     True,
        "query": (
            "Acid whey fermentation broth: lactic acid ~33 g/L (~3.3 wt%), "
            "disaccharide (lactose) ~8.9 g/L, galactose/fructose ~4.2 g/L, "
            "inorganic minerals ~36.7 g/L, water balance. From acid-set cheese by-product. "
            "Target: food-grade 50 wt% LA."
        ),
    },
    {
        "test_id":            "T2E-N-07",
        "expected_feed_type": "acid_whey_fermentation_broth",
        "grade":              "50wt",
        "numerical_mode":     True,
        "query": (
            "Cheese whey fermentation broth. LA concentration ~3.3 wt%, "
            "lactose and galactose present at ~0.9 wt% and ~0.4 wt% respectively, "
            "high mineral content (~3.7 wt% ions). Acid whey substrate. "
            "Target 50 wt% food-grade LA."
        ),
    },
    {
        "test_id":            "T2E-N-08",
        "expected_feed_type": "bread_hydrolysate_fermentation_broth",
        "grade":              "50wt",
        "numerical_mode":     True,
        "query": (
            "Bread waste hydrolysate fermented by B. coagulans at 50°C. "
            "Lactic acid ~77 g/L (~7.7 wt%), residual glucose ~10 g/L (~1 wt%), "
            "disaccharides ~13 g/L (~1.3 wt%), inorganic ions ~21 g/L. "
            "Target: food-grade 50 wt% LA."
        ),
    },
    {
        "test_id":            "T2E-N-09",
        "expected_feed_type": "bread_hydrolysate_fermentation_broth",
        "grade":              "50wt",
        "numerical_mode":     True,
        "query": (
            "Stale bread hydrolysate fermentation output: approximately 7.7 wt% lactic acid, "
            "1 wt% residual glucose, 1.3 wt% disaccharides (from partial hydrolysis), "
            "water and minerals balance. Target: 50 wt% LA."
        ),
    },
    # ── Sub-group B: Species-presence (qualitative descriptions) ─────────
    {
        "test_id":            "T2E-S-01",
        "expected_feed_type": "food_waste_broth",
        "grade":              "50wt",
        "numerical_mode":     False,
        "query": (
            "Mixed restaurant food waste fermentation broth: contains lactic acid, "
            "residual starch, glucose, fructose, protein from meat/sauce components, "
            "fat, and acetic acid as a by-product. "
            "Produced by SSF (simultaneous saccharification and fermentation). "
            "Target: food-grade 50 wt% LA."
        ),
    },
    {
        "test_id":            "T2E-S-02",
        "expected_feed_type": "food_waste_broth",
        "grade":              "50wt",
        "numerical_mode":     False,
        "query": (
            "Fermentation broth from mixed food waste (noodles, rice, vegetables, "
            "meat, sauce) using Streptococcus bovis. SSF process. "
            "Complex substrate with starch and protein. Target 50 wt% LA."
        ),
    },
    {
        "test_id":            "T2E-S-03",
        "expected_feed_type": "sugarcane_juice_fermentation_broth",
        "grade":              "50wt",
        "numerical_mode":     False,
        "query": (
            "Fresh sugarcane juice fermentation broth. Substrate is freshly squeezed "
            "cane juice: sucrose-dominant with glucose and fructose present. "
            "Fermented by L. pentosus with CaCO3 pH control. "
            "Target: food-grade 50 wt% LA."
        ),
    },
    {
        "test_id":            "T2E-S-04",
        "expected_feed_type": "sugarcane_juice_fermentation_broth",
        "grade":              "50wt",
        "numerical_mode":     False,
        "query": (
            "LA fermentation broth from sugarcane juice as substrate. "
            "Clear juice with high sucrose purity, low inorganic salt content. "
            "No dark colour compounds. Calcium carbonate used for pH buffering. "
            "50 wt% food-grade lactic acid target."
        ),
    },
    {
        "test_id":            "T2E-S-05",
        "expected_feed_type": "potato_waste_hydrolysate",
        "grade":              "50wt",
        "numerical_mode":     False,
        "query": (
            "Potato processing waste hydrolysate fermented by L. pentosus. "
            "Substrate: hydrolysed potato peels and rejects (starch released as glucose). "
            "Broth contains lactic acid, residual glucose, hydrolysed starch, water. "
            "Target: 50 wt% LA."
        ),
    },
    {
        "test_id":            "T2E-S-06",
        "expected_feed_type": "potato_waste_hydrolysate",
        "grade":              "50wt",
        "numerical_mode":     False,
        "query": (
            "Fermentation broth from enzymatic hydrolysis of potato industry waste. "
            "High starch hydrolysate content, glucose as primary carbon source. "
            "Target food-grade lactic acid at 50 wt%."
        ),
    },
    {
        "test_id":            "T2E-S-07",
        "expected_feed_type": "sugarcane_molasses_broth",
        "grade":              "50wt",
        "numerical_mode":     False,
        "query": (
            "Sugarcane molasses fermentation broth for lactic acid production. "
            "Substrate: blackstrap molasses — dark concentrated by-product after sugar crystallisation. "
            "Contains melanoidins, high inorganic salt content (K, Na, Ca, Mg), "
            "sucrose/glucose/fructose mixture. Fermented by L. plantarum. "
            "Target: 50 wt% food-grade LA."
        ),
    },
    {
        "test_id":            "T2E-S-08",
        "expected_feed_type": "sugarcane_molasses_broth",
        "grade":              "50wt",
        "numerical_mode":     False,
        "query": (
            "Lactic acid fermentation using molasses as carbon source. "
            "Dark-coloured concentrated sugarcane by-product. "
            "High colour compound content, high mineral salt impurities. "
            "Target: 50 wt% LA."
        ),
    },
]

T5_EXPERIMENTS = [
    # ── Pair 1: fermentation_broth vs food_waste_broth ───────────────────
    {
        "test_id":            "T5-01",
        "expected_feed_type": "food_waste_broth",
        "boundary_pair":      "fermentation_broth vs food_waste_broth",
        "grade":              "50wt",
        "query": (
            "Lactic acid fermentation broth from a complex mixed substrate. "
            "Contains lactic acid, water, trace succinic acid (like standard fermentation broth), "
            "but also residual starch, protein, and fat from the waste food-derived substrate. "
            "Target: 50 wt% food-grade LA."
        ),
    },
    {
        "test_id":            "T5-02",
        "expected_feed_type": "food_waste_broth",
        "boundary_pair":      "fermentation_broth vs food_waste_broth",
        "grade":              "50wt",
        "query": (
            "Standard LA fermentation output. LA ~8%, water ~90%, some organic acids. "
            "However substrate was mixed food waste (rice, noodles, vegetables) — "
            "complex carbohydrate and protein source for SSF. "
            "Target food-grade 50 wt%."
        ),
    },
    # ── Pair 2: glucose_fermentation_medium vs bread_hydrolysate ─────────
    {
        "test_id":            "T5-03",
        "expected_feed_type": "bread_hydrolysate_fermentation_broth",
        "boundary_pair":      "glucose_fermentation_medium vs bread_hydrolysate_fermentation_broth",
        "grade":              "50wt",
        "query": (
            "Bacillus coagulans fermentation at 50°C with CaCO3 for pH control. "
            "Glucose-based feed, but the glucose was obtained by enzymatic hydrolysis "
            "of stale bread — some disaccharide residues remain from incomplete hydrolysis. "
            "Target: 50 wt% LA."
        ),
    },
    {
        "test_id":            "T5-04",
        "expected_feed_type": "glucose_fermentation_medium",
        "boundary_pair":      "glucose_fermentation_medium vs bread_hydrolysate_fermentation_broth",
        "grade":              "50wt",
        "query": (
            "Pure glucose medium fermented by thermophilic B. coagulans (55°C). "
            "CaCO3 pH buffering, corn steep liquor powder as nutrient supplement. "
            "Glucose source is commercial glucose — no bread or waste substrate. "
            "Target 50 wt% LA."
        ),
    },
    # ── Pair 3: sugarcane_juice vs sugarcane_molasses ─────────────────────
    {
        "test_id":            "T5-05",
        "expected_feed_type": "sugarcane_molasses_broth",
        "boundary_pair":      "sugarcane_juice_fermentation_broth vs sugarcane_molasses_broth",
        "grade":              "50wt",
        "query": (
            "Sugarcane-derived fermentation broth. Contains sucrose, glucose, fructose, "
            "lactic acid, and inorganic salts. The substrate has some dark colour "
            "from concentration — it is a cane-based concentrated by-product, "
            "not fresh juice. Target: 50 wt% LA."
        ),
    },
    {
        "test_id":            "T5-06",
        "expected_feed_type": "sugarcane_juice_fermentation_broth",
        "boundary_pair":      "sugarcane_juice_fermentation_broth vs sugarcane_molasses_broth",
        "grade":              "50wt",
        "query": (
            "Sugarcane fermentation broth. Sucrose, glucose, fructose present. "
            "Clear liquid — freshly squeezed cane juice with no dark colour or "
            "concentrated colour compounds. L. pentosus fermentation. "
            "Target: 50 wt% food-grade LA."
        ),
    },
    # ── Pair 4: acid_whey vs whey_ultrafiltration_permeate ───────────────
    {
        "test_id":            "T5-07",
        "expected_feed_type": "acid_whey_fermentation_broth",
        "boundary_pair":      "acid_whey_fermentation_broth vs whey_ultrafiltration_permeate",
        "grade":              "50wt",
        "query": (
            "Whey-based fermentation broth for lactic acid production. "
            "Lactose and galactose present. From cheese manufacturing by-product. "
            "Not protein-depleted — this is the raw acid whey from acid-set cheese, "
            "not the UF permeate fraction. Target: 50 wt% LA."
        ),
    },
    {
        "test_id":            "T5-08",
        "expected_feed_type": "whey_ultrafiltration_permeate",
        "boundary_pair":      "acid_whey_fermentation_broth vs whey_ultrafiltration_permeate",
        "grade":              "50wt",
        "query": (
            "Sweet cheese whey ultrafiltration permeate fermented to lactic acid. "
            "Lactose present as carbon source. Protein-depleted (removed by UF membrane). "
            "Dairy industry by-product. Target: food-grade 50 wt% LA."
        ),
    },
    # ── Pair 5: fermentation_broth vs potato_waste_hydrolysate ───────────
    {
        "test_id":            "T5-09",
        "expected_feed_type": "potato_waste_hydrolysate",
        "boundary_pair":      "fermentation_broth vs potato_waste_hydrolysate",
        "grade":              "50wt",
        "query": (
            "LA fermentation broth from starch-containing substrate. "
            "Contains lactic acid, glucose, water, and residual starch. "
            "The carbon source is potato processing waste — peels and substandard potatoes "
            "hydrolysed enzymatically. Target: 50 wt% LA."
        ),
    },
    {
        "test_id":            "T5-10",
        "expected_feed_type": "fermentation_broth",
        "boundary_pair":      "fermentation_broth vs potato_waste_hydrolysate",
        "grade":              "50wt",
        "query": (
            "Standard lactic acid fermentation broth from Lactobacillus. "
            "Contains lactic acid ~8%, water ~90%, succinic acid ~1%, trace glucose. "
            "No starch, no potato-derived substrate. Pure glucose as carbon source. "
            "Target: 50 wt% food-grade LA."
        ),
    },
]

_EXPERIMENT_REGISTRY = {
    "T1": T1_EXPERIMENTS,
    "T2": T2_EXPERIMENTS,
    "T3": T3_EXPERIMENTS,
    "T4": T4_EXPERIMENTS,
    "T2E": T2E_EXPERIMENTS,
    "T5":  T5_EXPERIMENTS,
}


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def _results_path(series: str) -> str:
    if series in ("T2E", "T5"):
        name = "T2_extended_results" if series == "T2E" else "T5_boundary_results"
        return f"experiments/Group 1/{name}.json"
    return f"experiments/{series}_results_{RULE_ENGINE}.json"


def _report_path(test_id: str) -> str:
    os.makedirs("outputs", exist_ok=True)
    return f"outputs/{test_id}_{RULE_ENGINE}_report.txt"


def _cache_path(test_id: str) -> str:
    return f"outputs/cache/agent2_{test_id}.json"


# ---------------------------------------------------------------------------
# Results persistence
# ---------------------------------------------------------------------------

def _load_results(path: str) -> list:
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []


def _save_result(entry: dict, path: str):
    os.makedirs("experiments", exist_ok=True)
    results = _load_results(path)
    updated = False
    for i, r in enumerate(results):
        if r.get("test_id") == entry["test_id"]:
            results[i] = entry
            updated = True
            break
    if not updated:
        results.append(entry)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)


def _get_completed_test_ids(path: str) -> set:
    return {r["test_id"] for r in _load_results(path) if r.get("status") == "complete"}


# ---------------------------------------------------------------------------
# Metric helpers
# ---------------------------------------------------------------------------

def _parse_tier_counts(result: dict) -> tuple[int, int, int]:
    screened = result.get("screened_routes") or []
    tier1 = sum(1 for r in screened if str(r.get("tier", "")).startswith("Tier 1"))
    tier2 = sum(1 for r in screened if str(r.get("tier", "")).startswith("Tier 2"))
    tier3 = sum(1 for r in screened if str(r.get("tier", "")).startswith("Tier 3"))
    return tier1, tier2, tier3


def _parse_flag_counts(result: dict) -> tuple[int, int, int]:
    screened = result.get("screened_routes") or []
    critical = sum(r.get("flag_summary", {}).get("CRITICAL", 0) for r in screened)
    warning  = sum(r.get("flag_summary", {}).get("WARNING",  0) for r in screened)
    note     = sum(r.get("flag_summary", {}).get("NOTE",     0) for r in screened)
    return critical, warning, note


def _save_txt_report(result: dict, query: str, elapsed: float, test_id: str) -> str:
    path     = _report_path(test_id)
    screened = result.get("screened_routes") or []
    discovery = result.get("discovery_data") or {}
    tier1, tier2, tier3 = _parse_tier_counts(result)
    total    = discovery.get("total_routes_found", 0)
    feed     = result.get("feed_type", "")
    grade    = result.get("target_grade", "")
    critical = sum(r.get("flag_summary", {}).get("CRITICAL", 0) for r in screened)
    warning  = sum(r.get("flag_summary", {}).get("WARNING",  0) for r in screened)
    note     = sum(r.get("flag_summary", {}).get("NOTE",     0) for r in screened)

    with open(path, "w", encoding="utf-8") as f:
        f.write(f"Query: {query}\n")
        f.write(f"Generated: {datetime.now().isoformat()}\n")
        f.write(f"Time: {elapsed:.1f}s\n")
        f.write(f"Rule Engine: {RULE_ENGINE}\n")
        f.write("=" * 70 + "\n\n")
        f.write(f"Feed Type:    {feed}\n")
        f.write(f"Grade:        {grade}\n")
        f.write(f"Routes Found: {total}\n")
        f.write(f"Tier 1:       {tier1}\n")
        f.write(f"Tier 2:       {tier2}\n")
        f.write(f"Tier 3:       {tier3}\n")
        f.write("\nFlags Fired:\n")
        f.write(f"  CRITICAL: {critical}\n")
        f.write(f"  WARNING:  {warning}\n")
        f.write(f"  NOTE:     {note}\n")
        if result.get("error"):
            f.write(f"\nError: {result['error']}\n")

    print(f"[Output] Summary saved: {path}")
    return path


# ---------------------------------------------------------------------------
# Progress display
# ---------------------------------------------------------------------------

def _print_progress(series: str):
    experiments = _EXPERIMENT_REGISTRY[series]
    rpath       = _results_path(series)
    results     = _load_results(rpath)
    completed   = {r["test_id"] for r in results if r.get("status") == "complete"}
    failed      = {r["test_id"] for r in results if r.get("status") == "failed"}

    print(f"\n{'='*60}")
    print(f"{series} PROGRESS  [rule_engine={RULE_ENGINE}]")
    print(f"{'='*60}")
    for exp in experiments:
        tid = exp["test_id"]
        if tid in completed:
            r = next(x for x in results if x["test_id"] == tid)
            print(
                f"  ✅ {tid}  Tier1={r.get('tier1','?')}  "
                f"Tier2={r.get('tier2','?')}  Tier3={r.get('tier3','?')}  "
                f"({r.get('runtime_seconds','?')}s)"
            )
        elif tid in failed:
            r = next(x for x in results if x["test_id"] == tid)
            print(f"  ❌ {tid}  FAILED: {r.get('error','unknown')}")
        else:
            print(f"  ⬜ {tid}  (pending)")
    done = len(completed)
    total = len(experiments)
    print(f"\n  {done}/{total} complete")
    print(f"  Results: {rpath}")
    print(f"{'='*60}\n")


# ---------------------------------------------------------------------------
# Single experiment runner
# ---------------------------------------------------------------------------

MAX_AGENT3_RETRIES = 4


def run_single_experiment(exp: dict, resume_cache: str | None, series: str) -> bool:
    test_id = exp["test_id"]
    query   = exp["query"]
    feed    = exp.get("feed_type", exp.get("expected_feed_type", ""))
    grade   = exp["grade"]
    rpath   = _results_path(series)

    print(f"\n{'='*60}")
    print(f"RUNNING {test_id}  |  {feed}  |  {grade}  |  engine={RULE_ENGINE}")
    print(f"Query: {query}")
    print(f"{'='*60}\n")

    total_start = time.time()
    discovery_data = None

    if resume_cache:
        print(f"[{test_id}] Resume: loading Agent 2 cache from {resume_cache}")
        try:
            with open(resume_cache, "r", encoding="utf-8") as f:
                discovery_data = json.load(f)
        except Exception as e:
            print(f"[{test_id}] Failed to load cache: {e}. Aborting.")
            _save_result({
                "test_id": test_id, "feed_type": feed, "grade": grade,
                "rule_engine": RULE_ENGINE, "status": "failed",
                "error": f"Cache load failed: {e}",
                "runtime_seconds": round(time.time() - total_start, 1),
                "timestamp": datetime.now().isoformat(),
            }, rpath)
            return False
    else:
        print(f"[{test_id}] Full run: Agent 1 + 2...")
        try:
            t0     = time.time()
            result = run_dsp_discovery(query, test_id=test_id)
            print(f"[{test_id}] Agent 1+2 done in {time.time()-t0:.1f}s")

            if isinstance(result, dict):
                discovery_data = result.get("discovery_data")
            if not discovery_data:
                err = (result or {}).get("error") or "Agent 2 returned no discovery_data."
                print(f"[{test_id}] Agent 2 failed: {err}")
                _save_result({
                    "test_id": test_id, "feed_type": feed, "grade": grade,
                    "rule_engine": RULE_ENGINE, "status": "failed",
                    "error": f"Agent 2 failed: {err}",
                    "runtime_seconds": round(time.time() - total_start, 1),
                    "timestamp": datetime.now().isoformat(),
                }, rpath)
                return False

            screened = result.get("screened_routes")
            if screened is not None and not result.get("error"):
                elapsed = time.time() - total_start
                tier1, tier2, tier3 = _parse_tier_counts(result)
                critical, warning, note = _parse_flag_counts(result)
                _save_txt_report(result, query, elapsed, test_id)
                _save_result({
                    "test_id": test_id, "feed_type": feed, "grade": grade,
                    "rule_engine": RULE_ENGINE,
                    "routes_found_agent2": discovery_data.get("total_routes_found", 0),
                    "routes_screened_agent3": tier1 + tier2 + tier3,
                    "tier1": tier1, "tier2": tier2, "tier3": tier3,
                    "flags_critical": critical, "flags_warning": warning, "flags_note": note,
                    "runtime_seconds": round(elapsed, 1),
                    "ftma": "correct", "status": "complete",
                    "timestamp": datetime.now().isoformat(),
                }, rpath)
                print(f"\n✅ {test_id} DONE in {elapsed:.1f}s")
                print(f"   Routes: {discovery_data.get('total_routes_found',0)}  Tier1={tier1}  Tier2={tier2}  Tier3={tier3}")
                print(f"   Flags:  CRITICAL={critical}  WARNING={warning}  NOTE={note}")
                return True

            print(f"[{test_id}] Agent 3 failed in initial run — retrying from cache.")

        except Exception as e:
            print(f"[{test_id}] Exception during Agent 1/2: {e}")
            _save_result({
                "test_id": test_id, "feed_type": feed, "grade": grade,
                "rule_engine": RULE_ENGINE, "status": "failed",
                "error": f"Agent 1/2 exception: {e}",
                "runtime_seconds": round(time.time() - total_start, 1),
                "timestamp": datetime.now().isoformat(),
            }, rpath)
            return False

    # Retry Agent 3 from cache
    for attempt in range(1, MAX_AGENT3_RETRIES + 1):
        print(f"\n[{test_id}] Agent 3 attempt {attempt}/{MAX_AGENT3_RETRIES}...")
        try:
            result  = run_dsp_discovery_from_cache(query, discovery_data)
            screened = result.get("screened_routes") if isinstance(result, dict) else None
            if screened is not None and not (result or {}).get("error"):
                elapsed = time.time() - total_start
                tier1, tier2, tier3 = _parse_tier_counts(result)
                critical, warning, note = _parse_flag_counts(result)
                _save_txt_report(result, query, elapsed, test_id)
                _save_result({
                    "test_id": test_id, "feed_type": feed, "grade": grade,
                    "rule_engine": RULE_ENGINE,
                    "routes_found_agent2": discovery_data.get("total_routes_found", 0),
                    "routes_screened_agent3": tier1 + tier2 + tier3,
                    "tier1": tier1, "tier2": tier2, "tier3": tier3,
                    "flags_critical": critical, "flags_warning": warning, "flags_note": note,
                    "runtime_seconds": round(elapsed, 1),
                    "ftma": "correct", "status": "complete",
                    "agent3_attempts": attempt,
                    "timestamp": datetime.now().isoformat(),
                }, rpath)
                print(f"\n✅ {test_id} DONE (attempt {attempt}) in {elapsed:.1f}s total")
                return True

            print(f"[{test_id}] Attempt {attempt} failed: {(result or {}).get('error','no screened_routes')}")
        except Exception as e:
            print(f"[{test_id}] Attempt {attempt} raised: {e}")

        if attempt < MAX_AGENT3_RETRIES:
            wait = 10 * attempt
            print(f"[{test_id}] Waiting {wait}s before retry {attempt + 1}...")
            time.sleep(wait)

    elapsed = time.time() - total_start
    cache   = _cache_path(test_id)
    print(f"\n❌ {test_id} FAILED after {MAX_AGENT3_RETRIES} attempts ({elapsed:.1f}s)")
    print(f"   Resume later: python scripts/run_experiments.py --rule-engine {RULE_ENGINE} --resume {cache} \"{query}\"")
    _save_result({
        "test_id": test_id, "feed_type": feed, "grade": grade,
        "rule_engine": RULE_ENGINE, "status": "failed",
        "error": f"Agent 3 failed after {MAX_AGENT3_RETRIES} retries.",
        "agent2_cache": cache,
        "runtime_seconds": round(elapsed, 1),
        "timestamp": datetime.now().isoformat(),
    }, rpath)
    return False


# ---------------------------------------------------------------------------
# Batch runners
# ---------------------------------------------------------------------------

def run_t1_batch(skip_completed: bool = True):
    rpath = _results_path("T1")
    print(f"\n{'='*60}")
    print(f"T1 BATCH  [rule_engine={RULE_ENGINE}]")
    print(f"Results: {rpath}")
    print(f"{'='*60}")
    completed = _get_completed_test_ids(rpath) if skip_completed else set()
    successes = skipped = failures = 0
    for exp in T1_EXPERIMENTS:
        tid = exp["test_id"]
        if tid in completed:
            print(f"\n⏭  {tid} already complete — skipping.")
            skipped += 1
            continue
        cache_file   = _cache_path(tid)
        resume_cache = cache_file if os.path.exists(cache_file) else None
        if resume_cache:
            print(f"\n[Auto-resume] Agent 2 cache found for {tid}: {resume_cache}")
        ok = run_single_experiment(exp, resume_cache=resume_cache, series="T1")
        if ok:
            successes += 1
        else:
            failures += 1
        _print_progress("T1")
    print(f"\nT1 DONE — Completed: {successes}  Skipped: {skipped}  Failed: {failures}\n")


def run_experiment_batch(series: str, skip_completed: bool = True):
    experiments = _EXPERIMENT_REGISTRY[series]
    rpath       = _results_path(series)
    print(f"\n{'='*60}")
    print(f"{series} BATCH  [rule_engine={RULE_ENGINE}]")
    print(f"Results: {rpath}")
    print(f"{'='*60}")
    completed = _get_completed_test_ids(rpath) if skip_completed else set()
    successes = skipped = failures = 0
    for exp in experiments:
        tid               = exp["test_id"]
        query             = exp["query"]
        expected_feed     = exp.get("expected_feed_type", exp.get("feed_type", ""))
        grade             = exp["grade"]
        if tid in completed:
            print(f"\n⏭  {tid} already complete — skipping.")
            skipped += 1
            continue
        print(f"\n{'='*60}")
        print(f"RUNNING {tid}  |  expected={expected_feed}  |  grade={grade}")
        print(f"Query: {query}")
        print(f"{'='*60}\n")
        start = time.time()
        try:
            result  = run_dsp_discovery(query, test_id=tid)
            elapsed = time.time() - start
            if not isinstance(result, dict):
                result = {}
            parsed_feed  = result.get("feed_type", "")
            error        = result.get("error", "")
            discovery    = result.get("discovery_data") or {}
            routes_found = discovery.get("total_routes_found", 0)
            tier1, tier2, tier3 = _parse_tier_counts(result)
            critical, warning, note = _parse_flag_counts(result)
            screened = result.get("screened_routes") or []
            if expected_feed == "UNKNOWN":
                gdr_pass = (parsed_feed == "UNKNOWN" or "UNKNOWN" in str(error))
                ftma     = "correct" if gdr_pass else "incorrect"
                status   = "complete"
            else:
                ftma     = "correct" if parsed_feed == expected_feed else "incorrect"
                gdr_pass = None
                status   = "complete" if screened or ftma == "incorrect" else "failed"
            _save_txt_report(result, query, elapsed, tid)
            _save_result({
                "test_id":             tid,
                "series":              series,
                "rule_engine":         RULE_ENGINE,
                "expected_feed_type":  expected_feed,
                "agent1_parsed_feed":  parsed_feed,
                "ftma":                ftma,
                "grade":               grade,
                "routes_found_agent2": routes_found,
                "routes_screened":     len(screened),
                "tier1":               tier1,
                "tier2":               tier2,
                "tier3":               tier3,
                "flags_critical":      critical,
                "flags_warning":       warning,
                "flags_note":          note,
                "gdr_pass":            gdr_pass,
                "error":               error or None,
                "runtime_seconds":     round(elapsed, 1),
                "status":              status,
                "timestamp":           datetime.now().isoformat(),
            }, rpath)
            if expected_feed == "UNKNOWN":
                icon = "✅" if gdr_pass else "❌"
                print(f"\n{icon} {tid}  GDR={'PASS' if gdr_pass else 'FAIL'}  parsed='{parsed_feed}'  ({elapsed:.1f}s)")
            else:
                icon = "✅" if ftma == "correct" else "❌"
                print(f"\n{icon} {tid}  FTMA={ftma}  parsed='{parsed_feed}'  Tier1={tier1} Tier2={tier2} Tier3={tier3}  ({elapsed:.1f}s)")
            successes += 1
        except Exception as e:
            elapsed = time.time() - start
            print(f"\n❌ {tid} EXCEPTION: {e}")
            _save_result({
                "test_id":            tid,
                "series":             series,
                "rule_engine":        RULE_ENGINE,
                "expected_feed_type": expected_feed,
                "grade":              grade,
                "status":             "failed",
                "error":              str(e),
                "runtime_seconds":    round(elapsed, 1),
                "timestamp":          datetime.now().isoformat(),
            }, rpath)
            failures += 1
    print(f"\n{series} DONE — Completed: {successes}  Skipped: {skipped}  Failed: {failures}\n")


# ---------------------------------------------------------------------------
# T2E / T5 specialised batch runners (capture ambiguous flag + extra fields)
# ---------------------------------------------------------------------------

def run_t2e_t5_batch(series: str, skip_completed: bool = True):
    experiments = _EXPERIMENT_REGISTRY[series]
    rpath       = _results_path(series)
    label       = "T2-Extended" if series == "T2E" else "T5-Boundary"
    print(f"\n{'='*60}")
    print(f"{label} BATCH  [rule_engine={RULE_ENGINE}]")
    print(f"Results: {rpath}")
    print(f"{'='*60}")
    completed = _get_completed_test_ids(rpath) if skip_completed else set()
    successes = skipped = failures = 0

    for exp in experiments:
        tid           = exp["test_id"]
        query         = exp["query"]
        expected_feed = exp.get("expected_feed_type", "")
        grade         = exp["grade"]
        extra_fields  = {}
        if "numerical_mode" in exp:
            extra_fields["numerical_mode"] = exp["numerical_mode"]
        if "boundary_pair" in exp:
            extra_fields["boundary_pair"] = exp["boundary_pair"]

        if tid in completed:
            print(f"\n⏭  {tid} already complete — skipping.")
            skipped += 1
            continue

        print(f"\n{'='*60}")
        print(f"RUNNING {tid}  |  expected={expected_feed}  |  grade={grade}")
        if "boundary_pair" in exp:
            print(f"Pair: {exp['boundary_pair']}")
        if "numerical_mode" in exp:
            mode = "numerical" if exp["numerical_mode"] else "species"
            print(f"Mode: {mode}")
        print(f"Query: {query}")
        print(f"{'='*60}\n")

        start = time.time()
        try:
            result  = run_dsp_discovery(query, test_id=tid)
            elapsed = time.time() - start
            if not isinstance(result, dict):
                result = {}

            parsed_feed           = result.get("feed_type", "")
            ambiguous_flag        = result.get("ambiguous", False) or False
            alt_feed              = result.get("alternative_feed_type") or ""
            zero_msg              = result.get("zero_route_message") or ""
            error                 = result.get("error", "")
            discovery             = result.get("discovery_data") or {}
            routes_found          = discovery.get("total_routes_found", 0)
            tier1, tier2, tier3   = _parse_tier_counts(result)
            critical, warning, note = _parse_flag_counts(result)
            screened              = result.get("screened_routes") or []

            ftma   = "correct" if parsed_feed == expected_feed else "incorrect"
            status = "complete"

            _save_txt_report(result, query, elapsed, tid)
            entry = {
                "test_id":              tid,
                "series":               series,
                "rule_engine":          RULE_ENGINE,
                "expected_feed_type":   expected_feed,
                "agent1_parsed_feed":   parsed_feed,
                "ftma":                 ftma,
                "ambiguous_flag":       ambiguous_flag,
                "alternative_feed_type": alt_feed or None,
                "zero_route_message":   zero_msg or None,
                "grade":                grade,
                "routes_found":         routes_found,
                "tier1":                tier1,
                "tier2":                tier2,
                "tier3":                tier3,
                "flags_critical":       critical,
                "flags_warning":        warning,
                "flags_note":           note,
                "runtime_seconds":      round(elapsed, 1),
                "status":               status,
                "timestamp":            datetime.now().isoformat(),
                **extra_fields,
            }
            if error:
                entry["error"] = error
            os.makedirs("experiments/Group 1", exist_ok=True)
            _save_result(entry, rpath)

            icon = "[OK]" if ftma == "correct" else "[FAIL]"
            amb  = " [AMBIGUOUS]" if ambiguous_flag else ""
            zr   = " [ZERO-ROUTES]" if zero_msg else ""
            print(
                f"\n{icon}{amb}{zr} {tid}  FTMA={ftma}  parsed='{parsed_feed}'"
                f"  Tier1={tier1} Tier2={tier2} Tier3={tier3}  ({elapsed:.1f}s)"
            )
            if ambiguous_flag and alt_feed:
                print(f"   Alternative candidate: {alt_feed}")
            if zero_msg:
                print(f"   Zero-route message: {zero_msg}")
            successes += 1

        except Exception as e:
            elapsed = time.time() - start
            print(f"\n[FAIL] {tid} EXCEPTION: {e}")
            os.makedirs("experiments/Group 1", exist_ok=True)
            _save_result({
                "test_id":            tid,
                "series":             series,
                "rule_engine":        RULE_ENGINE,
                "expected_feed_type": expected_feed,
                "grade":              grade,
                "status":             "failed",
                "error":              str(e),
                "runtime_seconds":    round(elapsed, 1),
                "timestamp":          datetime.now().isoformat(),
                **extra_fields,
            }, rpath)
            failures += 1

    print(f"\n{label} DONE — Completed: {successes}  Skipped: {skipped}  Failed: {failures}\n")
    print(f"Results: {rpath}\n")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    args = sys.argv[1:]
    # Strip --rule-engine and its value from further parsing
    if "--rule-engine" in args:
        idx  = args.index("--rule-engine")
        args = args[:idx] + args[idx + 2:]

    if "--help" in args or not args:
        print("Usage:")
        print("  python scripts/run_experiments.py --run-t1 [--rule-engine baseline|enhanced|no_rules]")
        print("  python scripts/run_experiments.py --run-t2 [--rule-engine ...]")
        print("  python scripts/run_experiments.py --run-t3 [--rule-engine ...]")
        print("  python scripts/run_experiments.py --run-t4 [--rule-engine ...]")
        print("  python scripts/run_experiments.py --run-t2e  (T2-Extended: new feed types)")
        print("  python scripts/run_experiments.py --run-t5   (T5-Boundary: ambiguous pairs)")
        print("  python scripts/run_experiments.py --progress [--rule-engine ...]")
        print("  python scripts/run_experiments.py --rerun T1-03 T1-07 [--rule-engine ...]")
        return

    if "--run-t1" in args:
        run_t1_batch()
        return

    if "--run-t2e" in args:
        run_t2e_t5_batch("T2E")
        return

    if "--run-t5" in args:
        run_t2e_t5_batch("T5")
        return

    for s in ("t2", "t3", "t4"):
        if f"--run-{s}" in args:
            run_experiment_batch(s.upper())
            return

    if "--progress" in args:
        for s in ("T1", "T2", "T3", "T4", "T2E", "T5"):
            rpath = _results_path(s)
            if os.path.exists(rpath):
                _print_progress(s)
        return

    if "--rerun" in args:
        idx      = args.index("--rerun")
        test_ids = args[idx + 1:]
        if not test_ids:
            print("Usage: --rerun T1-03 T1-07")
            sys.exit(1)
        all_valid = {e["test_id"]: s for s, exps in _EXPERIMENT_REGISTRY.items() for e in exps}
        invalid   = [t for t in test_ids if t not in all_valid]
        if invalid:
            print(f"Unknown test IDs: {invalid}")
            sys.exit(1)
        for tid in test_ids:
            s     = all_valid[tid]
            rpath = _results_path(s)
            kept  = [r for r in _load_results(rpath) if r["test_id"] != tid]
            os.makedirs("experiments", exist_ok=True)
            with open(rpath, "w", encoding="utf-8") as f:
                json.dump(kept, f, indent=2, ensure_ascii=False)
            print(f"[Rerun] Reset {tid} in {rpath}")
        for s in sorted({all_valid[tid] for tid in test_ids}):
            print(f"\n[Rerun] Starting {s} batch...\n")
            if s == "T1":
                run_t1_batch()
            else:
                run_experiment_batch(s)
        return

    print("Unknown command. Use --help.")


if __name__ == "__main__":
    main()
