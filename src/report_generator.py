# src/report_generator.py
# Agent 4: Report Generator
#
# Single LLM call — NOT a ReAct agent, no tools, no loops.
# Input:  state["discovery_data"] + state["screened_routes"]
# Output: state["report"] — tiered NL report (Tier 1/2/3)
#
# Design principles:
#   - Agent 4 EXPLAINS Rule Engine output; it does NOT override it.
#   - If Agent 3 says Tier 3, Agent 4 reports it as Tier 3 — no re-evaluation.
#   - All numerical claims must be traceable to discovery_data.
#   - No hallucination, no ranking, no scoring.
#
# LLM provider:
#   - Controlled by LLM_PROVIDER in config.py ("anthropic" | "groq")
#   - Switch model by changing GROQ_MODEL or ANTHROPIC_MODEL in config.py
#   - No code changes needed here to switch providers.

from __future__ import annotations
import json

from langchain_core.messages import SystemMessage, HumanMessage

from src.llm_factory import get_llm          # ← NEW: replaces direct ChatAnthropic import
from src.state import DSPState


# ---------------------------------------------------------------------------
# Agent 4 system prompt
# ---------------------------------------------------------------------------
_AGENT4_SYSTEM_PROMPT = """
You are Agent 4 (Report Generator) in a lactic acid DSP multi-agent pipeline.
You receive structured route discovery data from Agent 2 and feasibility screening
results from Agent 3 (a deterministic rule engine).
Your task is to produce a clear, tiered natural language report for a process engineer.

## Core rules

- Report Tier 1 routes in FULL detail. Tier 2 routes with flags noted. Tier 3 routes briefly.
- NEVER re-evaluate feasibility. Tier and flags from the rule engine are facts, not opinions.
- NEVER rank or score routes. Present them neutrally within each tier.
- NEVER invent data. All claims must come from the structured input you receive.
- Use plain language. The reader is a process engineer, not a knowledge graph expert.
- Include units for all numerical values.
- When citing a flag, quote the rule_id (R-01, R-02, etc.) and the flag message verbatim.

## Citation rules — CRITICAL

The knowledge graph stores step-level performance data independently of route verification.
A route verified by P01 may include steps independently studied in P05.
You MUST distinguish these two levels in every Tier 1 route:

- **Route verification**: The paper that validated the COMPLETE route sequence as a whole.
  State once per route: "Verified against [PXX] as a complete purification sequence."

- **Step-level data**: Metrics (conversion, yield, purity) may come from a DIFFERENT paper.
  ALWAYS attribute explicitly: "P05 (independent simulation of this step)"
  NEVER present cross-paper step data as if it validates the overall route.

CORRECT example:
  Route verified against P01 as a complete sequence.
  Step 4 — RD Esterification: conversion = 0.99 [P05, independent simulation of this step]

INCORRECT (do not do this):
  Step 4 — RD Esterification: conversion = 0.99 [P01, P05]

## Performance metrics — grouping and explanation rules

When multiple values exist for the SAME metric type on the SAME step (e.g., three Yield values
for Step 2 Adsorption), DO NOT create one row per value. Instead:

1. **Group by metric type**: Merge multiple values into one row.
2. **State the range or list**: e.g., "86.2–93.0%" or "86.2%, 92.1%, 93.0%"
3. **Explain the variation**: Use the `basis` field from the KG if available. If not available,
   use the most likely scientific reason based on the metric type:
   - Multiple Capacity values → different adsorbent loadings, feed concentrations, or temperature
   - Multiple Yield values → different operating conditions (pH, flow rate, temperature)
   - Multiple Conversion values → different residence times or catalyst loadings
   - Multiple Purity values → different feed compositions or column configurations
4. **Never leave multiple rows unexplained**. A process engineer seeing three different Yield
   values with no explanation will assume data inconsistency.

CORRECT performance metrics table format:
| Step | Metric | Value | Unit | Source | Note |
|------|--------|-------|------|--------|------|
| Step 2 — Adsorption | Capacity | 106–222 | mg/g wet resin | P01 | Range across different feed concentrations and pH conditions |
| Step 2 — Adsorption | Yield | 86–93 | % | P01 | Range across different operating conditions |

INCORRECT (do not do this):
| Step 2 | Capacity | 222.46 | mg/g wet resin | P01 |
| Step 2 | Capacity | 197.09 | mg/g wet resin | P01 |
| Step 2 | Capacity | 106.0  | mg/g wet resin | P01 |

## Purity grouping — routes spanning multiple grades

When discovery data contains routes across multiple target grades (e.g. 50wt, 82wt, 88wt),
the user requested a minimum purity threshold and the system returned ALL routes meeting
or exceeding it. In this case:

1. Add this note at the top of QUERY PARAMETERS section:
   > "Showing all routes meeting or exceeding the requested minimum purity of X wt%.
   >  Routes are grouped by achieved target grade below."

2. Within each Tier section, group routes by target_grade in ascending purity order:
   ### Routes achieving 50 wt% (la_50wt)
   ### Routes achieving 82 wt% (la_82wt)
   ### Routes achieving 88 wt% (la_88wt)

3. In the NOTES AND CAVEATS section, state the total count per grade:
   e.g. "50wt: N routes | 82wt: N routes | 88wt: N routes"

4. If all routes share the same target_grade, no grouping headers are needed.

### 1. FEED SUMMARY
   Feed type, conditions (T, P, flow rate), major components with concentrations.
   State concentration units exactly as in the data (mole fraction, mass fraction, or wt%).

### 2. NOTES AND CAVEATS
   Include: total routes discovered, how many shown in detail, tier breakdown (Tier 1/2/3: N each),
   any literature-verified routes downgraded by rule engine (brief reason),
   any data gaps. Keep to 4–6 sentences.

### 3. QUERY PARAMETERS
   Target grade, minimum purity, verified_only flag, any user constraints.

### 4. TIER 1 — VERIFIED ROUTES  [N routes]
   For each route:
   a) Route name + verification statement: "Verified against [PXX] as a complete sequence."
   b) Step sequence in plain English (numbered list)
   c) Step-by-step detail table:
      | Step | Technique | DSP Stage | Key Chemicals | Key Constraints | Data Source |
   d) Performance metrics table with EXPLICIT cross-paper attribution:
      | Step | Metric | Value | Unit | Source |
      (If source differs from route verifier, add note: "independent study of this step")
   e) Key design guidelines from KG decision rules (bullet list)
   f) Shared steps with other routes (if any)

### 5. TIER 2 — PLAUSIBLE ROUTES  [N total, showing top 10 by fewest steps]
   For each of the 10:
   - One-line step sequence
   - Flags: [R-XX] LEVEL: message
   Keep to 3–4 lines per route.
   After the 10, add:
   > Showing 10 of [N] Tier 2 routes. Ask for more by technology, step count, or paper.

### 6. TIER 3 — PROBLEMATIC ROUTES  [N routes]
   For each:
   - One-line step sequence
   - Flags: [R-XX] CRITICAL: message
   - One sentence: why problematic and what must be resolved before use.
   If a route is both literature-verified AND Tier 3, add:
   "Published in [PXX] but flagged CRITICAL by rule engine due to [reason].
    The literature result is valid in its original context; the flag reflects
    general DSP design constraints, not an error in the publication."

Use markdown formatting (## for sections, ### for route names, | tables |, **bold** for emphasis).
""".strip()


# ---------------------------------------------------------------------------
# Agent 4 node function
# ---------------------------------------------------------------------------
def report_generator(state: DSPState) -> dict:
    """
    Agent 4 (Report Generator) — LangGraph node.

    Reads discovery_data and screened_routes from state,
    makes a single LLM call, and stores the NL report in state["report"].
    """
    discovery_data  = state.get("discovery_data")
    screened_routes = state.get("screened_routes")

    # Guard: should not happen if conditional edges are correct, but be safe
    if not discovery_data:
        return {
            "report": (
                "**Report generation failed**: No discovery data found in state. "
                "Agent 2 may have encountered an error."
            )
        }
    if screened_routes is None:
        return {
            "report": (
                "**Report generation failed**: No screening results found in state. "
                "Agent 3 may have encountered an error."
            )
        }

    # LLM is now sourced from llm_factory — provider controlled by config.py
    llm = get_llm(temperature=0.0)

    # Build tier summary for the user content prompt
    tier_counts = _count_tiers(screened_routes)

    # Attach per-route screening results into the routes in discovery_data
    # so Agent 4 can see tier + flags alongside each route's step details.
    # This avoids Agent 4 having to cross-reference two separate lists.
    enriched_data = _merge_screening_into_discovery(discovery_data, screened_routes)

    user_content = f"""
Please generate a tiered DSP route discovery report from the data below.

TIER SUMMARY (for your reference):
  Tier 1 — Verified   : {tier_counts['tier1']} routes
  Tier 2 — Plausible  : {tier_counts['tier2']} routes
  Tier 3 — Problematic: {tier_counts['tier3']} routes
  Total               : {tier_counts['total']} routes

ENRICHED DISCOVERY DATA (routes include tier + flags from Agent 3):
{json.dumps(enriched_data, indent=2)}
""".strip()

    try:
        response = llm.invoke([
            SystemMessage(content=_AGENT4_SYSTEM_PROMPT),
            HumanMessage(content=user_content),
        ])
        return {"report": response.content}

    except Exception as e:
        return {
            "report": (
                f"**Report generation failed**: Agent 4 raised an exception: {str(e)}"
            )
        }


# ---------------------------------------------------------------------------
# Helper: count routes by tier
# ---------------------------------------------------------------------------
def _count_tiers(screened_routes: list) -> dict:
    """Count routes per tier for the report summary header."""
    tier1 = sum(1 for r in screened_routes if r.get("tier", "").startswith("Tier 1"))
    tier2 = sum(1 for r in screened_routes if r.get("tier", "").startswith("Tier 2"))
    tier3 = sum(1 for r in screened_routes if r.get("tier", "").startswith("Tier 3"))
    return {
        "tier1": tier1,
        "tier2": tier2,
        "tier3": tier3,
        "total": len(screened_routes),
    }


# ---------------------------------------------------------------------------
# Helper: merge screening results into discovery data routes
# ---------------------------------------------------------------------------
def _merge_screening_into_discovery(
    discovery_data: dict,
    screened_routes: list,
) -> dict:
    """
    Attach Agent 3 screening results (tier, flags, flag_summary) to each
    route dict in discovery_data["routes"]. This gives Agent 4 a single
    unified data structure to work with.

    Returns a copy of discovery_data with screening fields added to each route.
    Modifying a copy (not mutating state directly) is safer in LangGraph.
    """
    # Build lookup: route_id → screening result
    screening_by_id: dict[str, dict] = {
        r["route_id"]: r for r in screened_routes
    }

    # Deep-copy routes to avoid mutating state
    import copy
    enriched_routes = copy.deepcopy(discovery_data.get("routes", []))

    for route in enriched_routes:
        rid = route.get("route_id", "")
        screening = screening_by_id.get(rid)
        if screening:
            route["tier"]         = screening.get("tier", "Unknown")
            route["flags"]        = screening.get("flags", [])
            route["flag_summary"] = screening.get("flag_summary", {})
        else:
            route["tier"]         = "Unknown (not screened)"
            route["flags"]        = []
            route["flag_summary"] = {}

    enriched_data = {
        **discovery_data,
        "routes": enriched_routes,
    }
    return enriched_data