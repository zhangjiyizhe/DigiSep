# src/state.py
# DSP Pipeline State Schema
#
# TypedDict shared across all 4 agents in the LangGraph StateGraph.

from __future__ import annotations
from typing import TypedDict, List, Optional, Annotated
from langgraph.graph import add_messages
from langchain_core.messages import BaseMessage


class DSPState(TypedDict):
    # ── LangGraph internal message list (Agent 2 ReAct loop) ──────────────
    messages: Annotated[List[BaseMessage], add_messages]

    # ── Parsed input (set by Agent 1) ─────────────────────────────────────
    feed_type:         str             # e.g. "fermentation_broth"
    target_grade:      str             # numeric purity string: "88wt", "50wt", "82wt", "87wt"
    target_purity_min: Optional[float] # e.g. 0.88 (None = not specified)
    verified_only:     bool            # True = only return literature-verified routes
    constraints:       Optional[dict]  # e.g. {"excluded_species": ["methanol"]}

    # ── Experiment tracking ────────────────────────────────────────────────
    # Set by pipeline.run_dsp_discovery() when running T1 experiments.
    # Used by agent_core.py to name the Agent 2 cache file:
    #   outputs/cache/agent2_<test_id>.json
    # None for single ad-hoc queries.
    test_id: Optional[str]            # e.g. "T1-01", "T1-02", ... or None

    # ── Agent 2 output (set by agent_route_discovery) ─────────────────────
    # Structured route discovery data. Schema:
    #   {
    #     "feed_type": str,
    #     "target_grade": str,
    #     "total_routes_found": int,
    #     "routes": [ { route_id, steps, verification, ... }, ... ],
    #     "query_params": { "target_purity_min": float, ... },
    #   }
    discovery_data: Optional[dict]

    # ── Agent 3 output (set by feasibility_screener) ──────────────────────
    # List of ScreenedRoute dicts. Each contains:
    #   { route_id, tier, flags, num_flags, flag_summary, verified, pathway_id, paper_id }
    screened_routes: Optional[list]

    # ── Agent 4 output (set by report_generator) ──────────────────────────
    report: Optional[str]             # Final NL report (Markdown)

    # ── Agent 1 ambiguity flags (Change 2) ────────────────────────────────
    ambiguous:             Optional[bool]  # True when Agent 1 is uncertain between two feed types
    alternative_feed_type: Optional[str]   # Second-best feed type key when ambiguous

    # ── Zero-route message (Change 3) ─────────────────────────────────────
    zero_route_message: Optional[str]      # Set when Agent 2 returns zero routes for a valid feed

    # ── Error tracking ─────────────────────────────────────────────────────
    error: Optional[str]              # Set by any agent on failure; triggers early END