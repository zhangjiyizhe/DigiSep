# src/input_parser.py
# Agent 1: Input Parser
#
# Single LLM call with Pydantic structured output.
# NOT a ReAct agent — no tools, no loops.
#
# KNOWN_FEED_TYPES is built from actual KG HAS_COMPONENT data. Only species
# present in KG feed streams are listed. Mol fractions are included only for
# fermentation_broth (the only feed stream with non-null values in the KG);
# all other FeedTypes use species-presence matching only.
#
# Matching strategy: (1) name/synonym, (2) distinguishing species,
# (3) origin/process description, (4) return UNKNOWN if no match.
# feed_type = "UNKNOWN" triggers early pipeline termination.
# ParsedDSPInput includes `verified_only: bool = False`.

from __future__ import annotations
from typing import Optional, List

from pydantic import BaseModel, Field
from src.llm_factory import get_llm
from langchain_core.messages import HumanMessage, SystemMessage

from src.state import DSPState


# ---------------------------------------------------------------------------
# Mapping: target_grade string → target_purity_min float
# ---------------------------------------------------------------------------
GRADE_TO_PURITY_MIN: dict[str, float] = {
    "50wt":  0.50,
    "82wt":  0.82,
    "87wt":  0.87,
    "88wt":  0.88,
}


# ---------------------------------------------------------------------------
# KNOWN_FEED_TYPES — built from the KG FeedType → HAS_COMPONENT data
#
# Data source: Cypher query on all FeedType → HAS_FEED_STREAM → HAS_COMPONENT
# Only fermentation_broth (P05 stream) has non-null mol fractions in KG.
# All other FeedTypes: species presence only.
#
# Matching priority for LLM:
#   1. Exact name / common synonym
#   2. Distinguishing species (species that uniquely identify a feed type)
#   3. Origin / process description
#   4. UNKNOWN if none of the above matches
# ---------------------------------------------------------------------------
KNOWN_FEED_TYPES: dict[str, dict] = {

    "fermentation_broth": {
        "display_name": "Lactic Acid Fermentation Broth",
        "kg_species": [
            # P05 stream — only KG stream with real mol fractions
            {"species": "water",         "mol_frac": 0.9058, "role": "solvent"},
            {"species": "lactic_acid",   "mol_frac": 0.0836, "role": "target_product"},
            {"species": "succinic_acid", "mol_frac": 0.0106, "role": "impurity"},
            # P01 stream — no mol fracs, species only
            {"species": "glucose",       "mol_frac": None,   "role": "residual_substrate"},
            # P03 streams — ionic forms (neutralised broth variants)
            {"species": "sodium_ion",    "mol_frac": None,   "role": "counter_ion"},
            {"species": "calcium_ion",   "mol_frac": None,   "role": "counter_ion"},
            {"species": "ammonium_ion",  "mol_frac": None,   "role": "counter_ion"},
        ],
        "distinguishing_species": ["succinic_acid", "lactic_acid"],
        "typical_pH": "3.86–7.0 (free acid) or 6–7 (neutralised with Ca(OH)2/NaOH/NH3)",
        "typical_temp": "35–40 °C",
        "origin": (
            "Standard bacterial LA fermentation broth (Lactobacillus or similar). "
            "May be free acid form or salt form depending on neutralisation agent used."
        ),
        "notes": (
            "MOST COMMON feed type. Key distinguishing features: "
            "(1) LA + water + trace succinic acid "
            "(P05 reference composition: LA 8.36 mol%, water 90.58 mol%, succinic 1.06 mol%). "
            "(2) May contain glucose (residual substrate). "
            "(3) NO lactose, NO xylose, NO furfural, NO maltose. "
            "Ionic variants (Ca-lactate, Na-lactate, NH4-lactate) are all fermentation_broth subtypes."
        ),
    },

    "candy_waste_digestate_broth": {
        "display_name": "LA Fermentation Broth (Candy-Waste + Digestate)",
        "kg_species": [
            {"species": "lactic_acid", "mol_frac": None, "role": "target_product"},
            {"species": "maltose",     "mol_frac": None, "role": "residual_substrate"},
        ],
        "distinguishing_species": ["maltose"],
        "typical_pH": "5.0–6.0",
        "typical_temp": "37–45 °C",
        "origin": (
            "Mixed waste substrate fermentation: candy industry waste (contains maltose/sugars) "
            "combined with anaerobic digestate as nutrient source. Paper P06."
        ),
        "notes": (
            "DISTINGUISHING feature: presence of MALTOSE (candy waste origin). "
            "If user mentions candy, confectionery, sweets, maltose, or digestate → this feed. "
            "No lactose, no xylose, no succinic acid signature."
        ),
    },

    "biomass_derived_reaction_liquor": {
        "display_name": "Corn Stover Hemicellulose-Derived Reaction Liquor",
        "kg_species": [
            {"species": "lactic_acid",   "mol_frac": None, "role": "target_product"},
            {"species": "glucose",       "mol_frac": None, "role": "residual_substrate"},
            {"species": "xylose",        "mol_frac": None, "role": "residual_substrate"},
            {"species": "furfural",      "mol_frac": None, "role": "inhibitory_impurity"},
            {"species": "sodium_ion",    "mol_frac": None, "role": "counter_ion"},
            {"species": "potassium_ion", "mol_frac": None, "role": "counter_ion"},
            {"species": "calcium_ion",   "mol_frac": None, "role": "counter_ion"},
            {"species": "magnesium_ion", "mol_frac": None, "role": "counter_ion"},
        ],
        "distinguishing_species": ["xylose", "furfural"],
        "typical_pH": "3.5–5.0",
        "typical_temp": "50–70 °C (catalytic) or 37–45 °C (fermentative)",
        "origin": (
            "Lignocellulosic biomass (corn stover) hemicellulose fraction. "
            "Converted to LA via catalytic or fermentative route. Paper P07."
        ),
        "notes": (
            "DISTINGUISHING features: "
            "(1) Contains XYLOSE (C5 sugar from hemicellulose) — unique to this feed type. "
            "(2) Contains FURFURAL (lignocellulosic degradation product). "
            "(3) High inorganic ion content (Na+, K+, Ca2+, Mg2+). "
            "If user mentions corn stover, lignocellulose, hemicellulose, xylose, or furfural → this feed."
        ),
    },

    "glucose_fermentation_medium": {
        "display_name": "Glucose-based Medium for B. coagulans CC17",
        "kg_species": [
            {"species": "water",                   "mol_frac": None, "role": "solvent"},
            {"species": "glucose",                 "mol_frac": None, "role": "substrate"},
            {"species": "yeast_extract",           "mol_frac": None, "role": "fermentation_supplement"},
            {"species": "corn_steep_liquor_powder","mol_frac": None, "role": "fermentation_supplement"},
            {"species": "calcium_carbonate",       "mol_frac": None, "role": "pH_buffer"},
        ],
        "distinguishing_species": ["corn_steep_liquor_powder", "calcium_carbonate"],
        "typical_pH": "6.0–6.5 (buffered by CaCO3)",
        "typical_temp": "50–55 °C (thermophilic B. coagulans)",
        "origin": (
            "Defined glucose medium fermented by thermophilic Bacillus coagulans CC17. "
            "Traditional batch AND ISPR (in-situ product removal) variants. Paper P10."
        ),
        "notes": (
            "DISTINGUISHING features: "
            "(1) Pure GLUCOSE substrate (no complex biomass). "
            "(2) CORN STEEP LIQUOR POWDER as nutrient — unusual additive. "
            "(3) CALCIUM CARBONATE for pH buffering (not NaOH or NH3). "
            "(4) Higher fermentation temp (50–55°C, thermophilic). "
            "Both traditional and ISPR fermentation modes map to this feed type."
        ),
    },

    "whey_ultrafiltration_permeate": {
        "display_name": "Sweet Cheese Whey UF Permeate",
        "kg_species": [
            {"species": "water",   "mol_frac": None, "role": "solvent"},
            {"species": "lactose", "mol_frac": None, "role": "substrate_and_impurity"},
        ],
        "distinguishing_species": ["lactose"],
        "typical_pH": "4.0–4.5 (post-fermentation)",
        "typical_temp": "4–10 °C (storage) or 30–37 °C (fermentation)",
        "origin": (
            "Dairy industry by-product. Sweet cheese whey after ultrafiltration "
            "to remove proteins. Lactose fermented to LA. Paper P02."
        ),
        "notes": (
            "DISTINGUISHING feature: presence of LACTOSE — only feed type in KG with lactose. "
            "If user mentions whey, dairy, cheese, lactose → this feed. "
            "No succinic acid, no xylose, no maltose."
        ),
    },

    "synthetic_lactic_acid_solution": {
        "display_name": "Synthetic Aqueous Lactic Acid Solution",
        "kg_species": [
            # No HAS_COMPONENT relationships in KG for this FeedType.
            # Binary LA+water system by definition.
        ],
        "distinguishing_species": [],
        "typical_pH": "2.0–3.5 (unbuffered)",
        "typical_temp": "20–25 °C",
        "origin": (
            "Commercially purchased or lab-prepared LA dissolved in water. "
            "No fermentation, no biological matrix. "
            "Used for equilibrium studies, resin characterisation, model validation."
        ),
        "notes": (
            "DISTINGUISHING feature: binary or near-binary system (LA + water, no impurities). "
            "If user says 'synthetic', 'lab-prepared', 'standard solution', "
            "or 'pure LA in water' with no mention of impurities → this feed. "
            "No fermentation by-products, no salts (unless added for ionic strength)."
        ),
    },

    # ── NEW FEED TYPES (P11–P15 import, 2026-04-20) ──────────────────────

    "food_waste_broth": {
        "display_name": "Mixed Restaurant Food Waste Fermentation Broth",
        "kg_species": [
            {"species": "lactic_acid",  "mol_frac": None, "role": "target_product"},
            {"species": "starch",       "mol_frac": None, "role": "residual_substrate"},
            {"species": "glucose",      "mol_frac": None, "role": "residual_substrate"},
            {"species": "fructose",     "mol_frac": None, "role": "residual_substrate"},
            {"species": "acetic_acid",  "mol_frac": None, "role": "by-product"},
            {"species": "protein",      "mol_frac": None, "role": "macronutrient_impurity"},
            {"species": "fat",          "mol_frac": None, "role": "macronutrient_impurity"},
            {"species": "water",        "mol_frac": None, "role": "solvent"},
        ],
        "distinguishing_species": ["starch", "protein", "fat"],
        "typical_pH": "~6.0 (NaOH-controlled)",
        "typical_temp": "37–45 °C",
        "origin": (
            "Mixed restaurant food waste (noodles, rice, vegetables, meat, sauces) "
            "fermented by simultaneous saccharification and fermentation (SSF). "
            "Complex heterogeneous solid waste substrate. Paper P11."
        ),
        "notes": (
            "DISTINGUISHING features: "
            "(1) Contains STARCH (unhydrolysed carbohydrate from food waste). "
            "(2) Contains PROTEIN and FAT (from meat/sauce components). "
            "(3) SSF process — enzymes and bacteria operate simultaneously. "
            "No maltose, no lactose, no xylose. "
            "If user mentions food waste, restaurant waste, mixed waste, noodles, "
            "or SSF with complex substrate → this feed."
        ),
    },

    "acid_whey_fermentation_broth": {
        "display_name": "Acid Whey Fermentation Broth",
        "kg_species": [
            {"species": "lactic_acid",   "mol_frac": None, "role": "target_product"},
            {"species": "lactose",       "mol_frac": None, "role": "residual_substrate"},
            {"species": "galactose",     "mol_frac": None, "role": "residual_substrate"},
            {"species": "fructose",      "mol_frac": None, "role": "residual_substrate"},
            {"species": "calcium_ion",   "mol_frac": None, "role": "mineral_impurity"},
            {"species": "sodium_ion",    "mol_frac": None, "role": "mineral_impurity"},
            {"species": "potassium_ion", "mol_frac": None, "role": "mineral_impurity"},
            {"species": "magnesium_ion", "mol_frac": None, "role": "mineral_impurity"},
            {"species": "water",         "mol_frac": None, "role": "solvent"},
        ],
        "distinguishing_species": ["galactose", "lactose"],
        "typical_pH": "3.5–4.5 (acid whey is already acidic)",
        "typical_temp": "37–45 °C",
        "origin": (
            "Acid whey by-product from acid-set cheese manufacturing "
            "(ricotta, cottage cheese, quark). "
            "Not protein-depleted. Lactose fermented to LA by B. coagulans. "
            "Paper P12."
        ),
        "notes": (
            "DISTINGUISHING features vs whey_ultrafiltration_permeate: "
            "(1) Acid whey — full protein content, NOT protein-depleted. "
            "(2) whey_ultrafiltration_permeate is SWEET cheese whey after UF (protein-removed). "
            "(3) Acid whey is more acidic (lower pH, already contains lactic acid). "
            "(4) Contains GALACTOSE alongside lactose (lactose hydrolysis product). "
            "Key disambiguation: 'acid whey' / 'acid-set cheese' / 'ricotta whey' → acid_whey_fermentation_broth. "
            "'Sweet whey' / 'UF permeate' / 'protein-free' → whey_ultrafiltration_permeate."
        ),
    },

    "bread_hydrolysate_fermentation_broth": {
        "display_name": "Bread Waste Hydrolysate Fermentation Broth",
        "kg_species": [
            {"species": "lactic_acid",   "mol_frac": None, "role": "target_product"},
            {"species": "glucose",       "mol_frac": None, "role": "primary_substrate"},
            {"species": "disaccharide",  "mol_frac": None, "role": "residual_substrate"},
            {"species": "sodium_ion",    "mol_frac": None, "role": "mineral_impurity"},
            {"species": "potassium_ion", "mol_frac": None, "role": "mineral_impurity"},
            {"species": "calcium_ion",   "mol_frac": None, "role": "mineral_impurity"},
            {"species": "water",         "mol_frac": None, "role": "solvent"},
        ],
        "distinguishing_species": ["disaccharide"],
        "typical_pH": "6.0–6.5 (buffered by CaCO3)",
        "typical_temp": "50–55 °C (thermophilic B. coagulans)",
        "origin": (
            "Stale bread waste (sugar bread or crust bread) enzymatically hydrolysed "
            "and fermented by thermophilic Bacillus coagulans to produce LA. "
            "Covers both sugar bread and crust bread hydrolysates. Paper P12."
        ),
        "notes": (
            "DISTINGUISHING features: "
            "(1) BREAD WASTE origin — stale bread hydrolysate. "
            "(2) Glucose-dominant after hydrolysis, but retains disaccharide residues. "
            "(3) Same B. coagulans organism as glucose_fermentation_medium, "
            "but with complex bread-derived substrate instead of pure glucose. "
            "If user mentions bread, bakery waste, stale bread, bread hydrolysate → this feed. "
            "Note: glucose_fermentation_medium uses PURE glucose with no waste; "
            "bread_hydrolysate has complex origin with disaccharides."
        ),
    },

    "sugarcane_juice_fermentation_broth": {
        "display_name": "Sugarcane Juice Fermentation Broth",
        "kg_species": [
            {"species": "lactic_acid",  "mol_frac": None, "role": "target_product"},
            {"species": "sucrose",      "mol_frac": None, "role": "primary_substrate"},
            {"species": "glucose",      "mol_frac": None, "role": "residual_substrate"},
            {"species": "fructose",     "mol_frac": None, "role": "residual_substrate"},
            {"species": "water",        "mol_frac": None, "role": "solvent"},
        ],
        "distinguishing_species": ["sucrose"],
        "typical_pH": "~6.0 (CaCO3-controlled)",
        "typical_temp": "37–45 °C",
        "origin": (
            "Fresh-squeezed sugarcane juice (high sucrose, low impurity) "
            "fermented by L. pentosus to produce LA. "
            "Calcium carbonate used for pH control. Paper P13."
        ),
        "notes": (
            "DISTINGUISHING features vs sugarcane_molasses_broth: "
            "(1) Fresh-squeezed juice — HIGH sucrose purity, CLEAR/CLEAN liquid. "
            "(2) NO dark color compounds (melanoidins/caramels). "
            "(3) LOW inorganic salt content. "
            "If user mentions sugarcane juice (fresh) or cane juice → sugarcane_juice_fermentation_broth. "
            "If user mentions MOLASSES, dark colour, concentrated by-product, "
            "or high salt content → sugarcane_molasses_broth."
        ),
    },

    "potato_waste_hydrolysate": {
        "display_name": "Potato Processing Waste Hydrolysate Fermentation Broth",
        "kg_species": [
            {"species": "lactic_acid",       "mol_frac": None, "role": "target_product"},
            {"species": "glucose",           "mol_frac": None, "role": "primary_substrate"},
            {"species": "hydrolyzed_starch", "mol_frac": None, "role": "residual_substrate"},
            {"species": "water",             "mol_frac": None, "role": "solvent"},
        ],
        "distinguishing_species": ["hydrolyzed_starch"],
        "typical_pH": "~6.0 (CaCO3-controlled)",
        "typical_temp": "37–45 °C",
        "origin": (
            "Potato processing by-product waste (peels, substandard potatoes, "
            "processing rejects) hydrolysed to release starch/glucose, "
            "then fermented by L. pentosus to produce LA. Paper P14."
        ),
        "notes": (
            "DISTINGUISHING features: "
            "(1) POTATO WASTE origin — starch-rich agricultural waste. "
            "(2) High starch content released during hydrolysis. "
            "(3) Different protein/nitrogen profile from other substrates. "
            "If user mentions potato, potato peel, potato processing waste, "
            "or starch hydrolysate from potato → this feed."
        ),
    },

    "sugarcane_molasses_broth": {
        "display_name": "Sugarcane Molasses Fermentation Broth",
        "kg_species": [
            {"species": "lactic_acid",      "mol_frac": 0.05,  "role": "target_product"},
            {"species": "sucrose",          "mol_frac": None,  "role": "residual_substrate"},
            {"species": "glucose",          "mol_frac": None,  "role": "residual_substrate"},
            {"species": "fructose",         "mol_frac": None,  "role": "residual_substrate"},
            {"species": "melanoidin",       "mol_frac": None,  "role": "colour_impurity"},
            {"species": "potassium_ion",    "mol_frac": None,  "role": "mineral_impurity"},
            {"species": "sodium_ion",       "mol_frac": None,  "role": "mineral_impurity"},
            {"species": "calcium_ion",      "mol_frac": None,  "role": "mineral_impurity"},
            {"species": "water",            "mol_frac": None,  "role": "solvent"},
        ],
        "distinguishing_species": ["melanoidin"],
        "typical_pH": "~6.0 (NaOH-controlled)",
        "typical_temp": "37–45 °C",
        "origin": (
            "Sugarcane molasses — concentrated dark by-product remaining after "
            "sugar crystallisation from sugarcane juice. "
            "Fermented by L. plantarum to produce LA. Paper P15."
        ),
        "notes": (
            "DISTINGUISHING features vs sugarcane_juice_fermentation_broth: "
            "(1) MOLASSES — dark, concentrated, high-impurity by-product. "
            "(2) Contains MELANOIDINS and caramel compounds (dark colour). "
            "(3) HIGH inorganic salt content (K, Na, Ca, Mg) from sugar extraction. "
            "(4) Low LA concentration (~5 wt%). "
            "If user mentions molasses, dark colour, concentrated sugarcane by-product, "
            "or blackstrap → this feed. "
            "If user mentions fresh sugarcane JUICE (clear, high sucrose purity) → "
            "sugarcane_juice_fermentation_broth."
        ),
    },
}


# ---------------------------------------------------------------------------
# Build feed context string injected into LLM system prompt
# ---------------------------------------------------------------------------
def _build_feed_context() -> str:
    lines = [
        "KNOWN FEED TYPES IN THE KNOWLEDGE GRAPH (12 total):",
        "Match the user's feed to one of these by: (1) name/synonym, "
        "(2) distinguishing species, (3) origin.",
        "Return 'UNKNOWN' if target product is NOT lactic acid, or no match possible.",
        "",
    ]
    for key, info in KNOWN_FEED_TYPES.items():
        lines.append(f"=== {key} ===")
        lines.append(f"  Display name : {info['display_name']}")
        lines.append(f"  Origin       : {info['origin']}")
        lines.append(f"  Typical pH   : {info['typical_pH']}")
        lines.append(f"  Typical temp : {info['typical_temp']}")

        if info["kg_species"]:
            parts = []
            for s in info["kg_species"]:
                if s["mol_frac"] is not None:
                    parts.append(
                        f"{s['species']} (mol_frac={s['mol_frac']:.4f}, {s['role']})"
                    )
                else:
                    parts.append(f"{s['species']} ({s['role']})")
            lines.append(f"  KG species   : {'; '.join(parts)}")
        else:
            lines.append("  KG species   : binary LA+water (no composition data in KG)")

        if info["distinguishing_species"]:
            lines.append(
                f"  KEY SPECIES  : {', '.join(info['distinguishing_species'])}"
            )
        lines.append(f"  Notes        : {info['notes']}")
        lines.append("")

    return "\n".join(lines)


# Pre-built once at module load
_FEED_CONTEXT_STR: str = _build_feed_context()


# ---------------------------------------------------------------------------
# Pydantic schema for structured LLM output
# ---------------------------------------------------------------------------
class ParsedDSPInput(BaseModel):
    """Structured representation of the user's DSP query."""

    feed_type: str = Field(
        description=(
            "Exact FeedType.name key from the KG, OR 'UNKNOWN'. "
            "Valid values: 'fermentation_broth', 'whey_ultrafiltration_permeate', "
            "'glucose_fermentation_medium', 'candy_waste_digestate_broth', "
            "'biomass_derived_reaction_liquor', 'synthetic_lactic_acid_solution', "
            "'food_waste_broth', 'acid_whey_fermentation_broth', "
            "'bread_hydrolysate_fermentation_broth', 'sugarcane_juice_fermentation_broth', "
            "'potato_waste_hydrolysate', 'sugarcane_molasses_broth'. "
            "Use 'UNKNOWN' if: (a) target product is NOT lactic acid, "
            "or (b) feed cannot be matched by name, species, or origin. "
            "Match by name first, then by KEY SPECIES, then by origin description."
        )
    )
    target_grade: str = Field(
        description=(
            "TargetSpec.target_grade — numeric purity string. "
            "One of: '50wt', '82wt', '87wt', '88wt'. "
            "Map: 'high purity'/'polymer grade'/'PLA'/'88%' → '88wt'; "
            "'food grade'/'GRAS'/'50%' → '50wt'; "
            "'87%'/'pre-concentrated' → '87wt'; "
            "'82%'/'process crude' → '82wt'."
        )
    )
    target_purity_min: Optional[float] = Field(
        default=None,
        description="Min purity as decimal (0–1). E.g. 88% → 0.88. None if not specified."
    )
    verified_only: bool = Field(
        default=False,
        description=(
            "True only if user explicitly requests literature-verified routes. "
            "Default False."
        )
    )
    excluded_species: Optional[List[str]] = Field(
        default=None,
        description=(
            "Species to avoid in name_canonical format. "
            "E.g. 'no methanol' → ['methanol']. None if not mentioned."
        )
    )
    max_steps: Optional[int] = Field(
        default=None,
        description="Max process steps. None if not specified."
    )
    notes: Optional[str] = Field(
        default=None,
        description="Any other constraint. Record verbatim."
    )
    ambiguous: bool = Field(
        default=False,
        description=(
            "True if the input matches two feed types almost equally and the distinction "
            "is uncertain. When True, also populate alternative_feed_type and "
            "alternative_reasoning."
        )
    )
    alternative_feed_type: Optional[str] = Field(
        default=None,
        description=(
            "Second-best feed type key when ambiguous=True. "
            "Use the same valid key list as feed_type. None otherwise."
        )
    )
    alternative_reasoning: Optional[str] = Field(
        default=None,
        description=(
            "One sentence explaining the key compositional or origin difference "
            "that distinguishes feed_type (recommended) from alternative_feed_type. "
            "None when ambiguous=False."
        )
    )


# ---------------------------------------------------------------------------
# Agent 1 node function
# ---------------------------------------------------------------------------
def input_parser(state: DSPState) -> dict:
    """
    Agent 1 (Input Parser) — LangGraph node.

    Reads the last user message, calls Claude Sonnet with structured output,
    returns parsed fields to merge into DSPState.

    Matching strategy by experiment type:
      T1 (canonical names)  → matched by name/synonym in Field description
      T2 (mol frac numbers) → LLM compares to P05 reference values in FEED_CONTEXT
      T3 (perturbed comps)  → LLM matches by distinguishing species
      T4 (out-of-domain)    → returns UNKNOWN → pipeline terminates at conditional edge
    """
    user_message = state["messages"][-1].content

    llm = get_llm(temperature=0.0, max_tokens=1000)
    structured_llm = llm.with_structured_output(ParsedDSPInput)

    system_content = (
        "You are parsing a user's query about lactic acid (LA) downstream "
        "separation process (DSP) route discovery.\n\n"
        "Tasks:\n"
        "  1. Identify which FeedType the user's feed corresponds to.\n"
        "  2. Identify the target purity grade.\n"
        "  3. Extract any constraints.\n\n"
        "CRITICAL MATCHING RULES (apply in order):\n"
        "  - Target product MUST be lactic acid. If not → feed_type='UNKNOWN'.\n"
        "  - xylose or furfural present → biomass_derived_reaction_liquor\n"
        "  - maltose present → candy_waste_digestate_broth\n"
        "  - starch + protein + fat (mixed food waste / SSF) → food_waste_broth\n"
        "  - bread waste / bakery waste / bread hydrolysate → bread_hydrolysate_fermentation_broth\n"
        "  - potato waste / potato hydrolysate / starch from potato → potato_waste_hydrolysate\n"
        "  - molasses / dark colour / melanoidins / concentrated sugarcane by-product → sugarcane_molasses_broth\n"
        "  - sugarcane juice (fresh, clear, high-sucrose) → sugarcane_juice_fermentation_broth\n"
        "  - acid whey / acid-set cheese / galactose + lactose → acid_whey_fermentation_broth\n"
        "  - sweet whey / UF permeate / protein-depleted whey / lactose only → whey_ultrafiltration_permeate\n"
        "  - corn steep liquor OR CaCO3 pH buffer + pure glucose → glucose_fermentation_medium\n"
        "  - LA + water only, synthetic/lab-prepared → synthetic_lactic_acid_solution\n"
        "  - LA + water + succinic acid OR standard fermentation broth → fermentation_broth\n"
        "  - User gives mol fracs close to: LA ~8.4%, water ~90.6%, succinic ~1.1% → fermentation_broth\n"
        "  - No match possible → UNKNOWN\n\n"
        "AMBIGUITY RULE:\n"
        "  - If the input is compositionally close to two feed types and you are uncertain,\n"
        "    return the best match as feed_type, set ambiguous=True,\n"
        "    set alternative_feed_type to the second-best key, and\n"
        "    set alternative_reasoning to one sentence explaining the key difference.\n"
        "  - Key ambiguous pairs: sugarcane_juice_fermentation_broth vs sugarcane_molasses_broth\n"
        "    (juice=clear/fresh; molasses=dark/concentrated); acid_whey_fermentation_broth vs\n"
        "    whey_ultrafiltration_permeate (acid whey=full protein; UF permeate=protein-depleted);\n"
        "    glucose_fermentation_medium vs bread_hydrolysate_fermentation_broth\n"
        "    (pure glucose vs bread-derived disaccharide mix); fermentation_broth vs\n"
        "    food_waste_broth (standard LA broth vs complex waste matrix with starch/protein/fat).\n\n"
        + _FEED_CONTEXT_STR
    )

    try:
        parsed: ParsedDSPInput = structured_llm.invoke([
            SystemMessage(content=system_content),
            HumanMessage(content=f"User query: {user_message}"),
        ])

        # UNKNOWN → terminate pipeline gracefully
        if parsed.feed_type == "UNKNOWN":
            return {
                "error": (
                    "Agent 1: Feed type could not be matched to any known FeedType "
                    "in the knowledge graph. The feed may be out-of-domain "
                    "(non-LA product or composition irreconcilably different from "
                    f"all 12 known feed types). Original query: {user_message}"
                ),
                "feed_type":         "UNKNOWN",
                "target_grade":      parsed.target_grade,
                "target_purity_min": None,
                "verified_only":     parsed.verified_only,
                "constraints":       None,
            }

        derived_purity_min = GRADE_TO_PURITY_MIN.get(parsed.target_grade)

        constraints: dict = {}
        if parsed.excluded_species:
            constraints["excluded_species"] = parsed.excluded_species
        if parsed.max_steps:
            constraints["max_steps"] = parsed.max_steps
        if parsed.notes:
            constraints["notes"] = parsed.notes

        return {
            "feed_type":              parsed.feed_type,
            "target_grade":           parsed.target_grade,
            "target_purity_min":      derived_purity_min,
            "verified_only":          parsed.verified_only,
            "constraints":            constraints if constraints else None,
            "ambiguous":              parsed.ambiguous,
            "alternative_feed_type":  parsed.alternative_feed_type,
        }

    except Exception as e:
        return {
            "error":             f"Agent 1 failed to parse input: {str(e)}",
            "feed_type":         "",
            "target_grade":      "",
            "target_purity_min": None,
            "verified_only":     False,
            "constraints":       None,
        }