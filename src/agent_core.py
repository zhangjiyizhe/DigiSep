# src/agent_core.py
# Agent 2: Route Discovery
#
# LangGraph ReAct agent using create_react_agent with Neo4j tools.
# Agent 2 runs its ReAct loop (Phase 1–3) and then outputs structured
# discovery_data JSON in Phase 4. The node wrapper parses the JSON and
# stores it in state["discovery_data"].
#
# Architecture:
#   - Agent 2 is a create_react_agent (LangGraph prebuilt)
#   - System prompt in src/prompts/agent_core_prompt.py
#   - Phase 4 requires Final Answer = valid JSON (discovery_data schema)
#   - This node wrapper extracts the JSON and stores it in state
#
# Cache behaviour:
#   - Raw output always saved to outputs/agent2_raw_output.txt (overwritten each run)
#   - If state["test_id"] is set, also saved to outputs/cache/agent2_<test_id>.json
#     so that failed runs after Agent 2 can be resumed without re-running Agent 2.
#
# LLM provider:
#   - Controlled by LLM_PROVIDER in config.py ("anthropic" | "groq")
#   - Switch model by changing GROQ_MODEL or ANTHROPIC_MODEL in config.py
#   - No code changes needed here to switch providers.

from __future__ import annotations
import json
import os
import re

from langchain_core.messages import HumanMessage
from langgraph.prebuilt import create_react_agent

from config import RECURSION_LIMIT, MAX_OUTPUT_TOKENS
from src.llm_factory import get_llm
from src.state import DSPState
from src.prompts.agent_core_prompt import AGENT2_SYSTEM_PROMPT

from src.tools.get_feed_info import get_feed_info
from src.tools.get_all_routes import get_all_routes

# Verification is now handled inside get_all_routes (via verification_shared).
# get_step_details, get_decision_rules, get_cases_and_metrics,
# get_stream_composition, get_chemical_species, verify_against_pathway
# are NOT registered — the system prompt forbids calling them and they
# add unused schema tokens to every request.


# ---------------------------------------------------------------------------
# Build the ReAct agent (module-level — created once at import)
# ---------------------------------------------------------------------------
_llm = get_llm(temperature=0.0, max_tokens=MAX_OUTPUT_TOKENS)

_tools = [
    get_feed_info,
    get_all_routes,
]

_react_agent = create_react_agent(
    model=_llm,
    tools=_tools,
    prompt=AGENT2_SYSTEM_PROMPT,
)


# ---------------------------------------------------------------------------
# JSON extraction helper
# ---------------------------------------------------------------------------
def _extract_json_from_text(text: str) -> dict | None:
    """
    Extract discovery_data JSON from Agent 2's Final Answer.
    Strategy: find the first '{', then handle trailing text after the JSON.
    """
    start_idx = text.find("{")
    if start_idx == -1:
        return None

    candidate = text[start_idx:]

    # Attempt 1: direct parse
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as e:
        truncated  = candidate[: e.pos]
        last_brace = truncated.rfind("}")
        if last_brace == -1:
            return None
        try:
            return json.loads(truncated[: last_brace + 1])
        except json.JSONDecodeError:
            return None


# ---------------------------------------------------------------------------
# Cache helpers
# ---------------------------------------------------------------------------
def _save_cache(test_id: str | None, discovery_data: dict):
    """
    Save parsed discovery_data JSON to the test-specific cache file.
    Only called when JSON extraction succeeds AND test_id is set.
    """
    if not test_id:
        return
    os.makedirs("outputs/cache", exist_ok=True)
    cache_path = f"outputs/cache/agent2_{test_id}.json"
    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(discovery_data, f, indent=2, ensure_ascii=False)
        print(f"[Agent 2] Cache saved: {cache_path}")
    except Exception as e:
        print(f"[Agent 2] Warning: could not save cache: {e}")


# ---------------------------------------------------------------------------
# Node wrapper: agent_route_discovery
# ---------------------------------------------------------------------------
def agent_route_discovery(state: DSPState) -> dict:
    """
    Agent 2 (Route Discovery) — LangGraph node.

    1. Builds the discovery prompt from parsed state fields.
    2. Runs the ReAct agent — it calls Neo4j tools in Phase 1–3.
    3. Extracts the Phase 4 JSON output from the agent's final message.
    4. Saves cache to outputs/cache/agent2_<test_id>.json if test_id is set.
    5. Stores the parsed discovery_data dict in state.
    """
    feed_type     = state.get("feed_type", "")
    target_grade  = state.get("target_grade", "")
    target_purity = state.get("target_purity_min")
    verified_only = state.get("verified_only", False)
    constraints   = state.get("constraints") or {}
    test_id       = state.get("test_id")   # used for cache file naming

    purity_clause = (
        f" with minimum purity {target_purity * 100:.1f}%"
        if target_purity is not None
        else ""
    )
    verified_clause = (
        " Return only literature-verified routes." if verified_only else ""
    )
    constraints_clause = (
        f" Additional constraints: {json.dumps(constraints)}" if constraints else ""
    )

    user_prompt = (
        f"Discover all {target_grade}-grade lactic acid purification routes "
        f"from feed type '{feed_type}'{purity_clause}. "
        f"verified_only={verified_only}.{verified_clause}{constraints_clause} "
        "Follow the 4-phase workflow. "
        "IMPORTANT TOKEN BUDGET RULE: In Phase 3, only call get_step_details and "
        "get_decision_rules for steps that appear in VERIFIED routes (those with "
        "verification.verified=True from get_all_routes). "
        "For unverified routes, use only the step data already returned by "
        "get_all_routes — do NOT call get_step_details for every unverified route. "
        "This is critical to stay within API rate limits. "
        "Output structured JSON in Phase 4."
    )

    try:
        agent_result = _react_agent.invoke(
            {"messages": [HumanMessage(content=user_prompt)]},
            config={"recursion_limit": RECURSION_LIMIT},
        )

        agent_messages = agent_result.get("messages", [])
        if not agent_messages:
            return {"error": "Agent 2 returned no messages.", "discovery_data": None}

        last_message = agent_messages[-1]
        final_text   = (
            last_message.content
            if isinstance(last_message.content, str)
            else str(last_message.content)
        )

        # Always save raw output (overwritten each run — useful for debugging)
        os.makedirs("outputs", exist_ok=True)
        raw_path = (
            f"outputs/agent2_raw_{test_id}.txt" if test_id
            else "outputs/agent2_raw_output.txt"
        )
        with open(raw_path, "w", encoding="utf-8") as f:
            f.write(final_text)
        print(f"[Agent 2] Raw output cached: {len(final_text)} chars → {raw_path}")

        # Extract JSON
        discovery_data = _extract_json_from_text(final_text)

        if discovery_data is None:
            return {
                "error": (
                    "Agent 2 Phase 4 output could not be parsed as JSON. "
                    f"JSON start position: {final_text.find('{')}, "
                    f"Total output length: {len(final_text)} chars. "
                    f"First 200 chars: {final_text[:200]}"
                ),
                "discovery_data": None,
            }

        if "routes" not in discovery_data or "total_routes_found" not in discovery_data:
            return {
                "error": (
                    "Agent 2 JSON output is missing required fields "
                    "('routes' or 'total_routes_found'). "
                    f"Keys found: {list(discovery_data.keys())}"
                ),
                "discovery_data": None,
            }

        # Save to test-specific cache (enables resume without re-running Agent 2)
        _save_cache(test_id, discovery_data)

        return {"discovery_data": discovery_data, "error": None}

    except Exception as e:
        return {
            "error": f"Agent 2 (Route Discovery) raised an exception: {str(e)}",
            "discovery_data": None,
        }