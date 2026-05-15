# src/tools/get_all_routes.py
# Tool 1: get_all_routes — DAG traversal from FeedType to TargetSpec
#
# Verification strategy:
#   Verification is done INSIDE this tool using verification_shared, so Agent 2
#   reads route["verification"] directly and makes no per-route tool calls.
#
#   Each route["verification"] dict contains:
#     verified    (bool)       — True for exact or superset Pathway match
#     pathway_id  (str|None)   — matched Pathway, or None
#     paper_id    (str|None)   — matched Paper, or None
#     route_name  (str|None)   — matched route name, or None

from langchain_core.tools import tool
from src.tools.neo4j_connection import neo4j_conn
from src.tools.verification_shared import (
    fetch_pathways_and_recovery_steps,
    verify_route,
)


_ROUTE_CYPHER = """
MATCH (ft:FeedType {name: $feed_type})
      -[:FIRST_STEP]->(first:ProcessStep),
      path = (first)-[:HAS_NEXT_STEP*0..15]->(last:ProcessStep),
      (last)-[:HAS_PRODUCT]->(prod_stream:Stream),
      (prod_stream)-[pur:HAS_PURITY]->(ts:TargetSpec)
WHERE ts.target_purity_min >= $target_purity_min
RETURN
    [n IN nodes(path) | n.step_key]          AS step_keys,
    [n IN nodes(path) | n.description]       AS step_descriptions,
    [n IN nodes(path) | n.step_category]     AS step_categories,
    [n IN nodes(path) | n.technique_family]  AS technique_families,
    [n IN nodes(path) | n.dsp_stage]         AS dsp_stages,
    ts.spec_id                               AS target_spec_id,
    ts.target_grade                          AS target_grade,
    ts.target_purity_min                     AS target_purity,
    ts.purity_unit                           AS purity_unit,
    pur.value                                AS achieved_purity,
    prod_stream.stream_key                   AS product_stream,
    prod_stream.temperature                  AS product_temp,
    prod_stream.temperature_unit             AS product_temp_unit,
    length(path) + 1                         AS num_steps,
    ft.display_name                          AS feed_display_name
ORDER BY ts.target_purity_min ASC, num_steps ASC
"""


def _process_routes(raw_results: list) -> list[dict]:
    seen: set[tuple] = set()
    routes: list[dict] = []
    for record in raw_results:
        route_key = tuple(record["step_keys"])
        if route_key in seen:
            continue
        seen.add(route_key)
        steps = [
            {
                "step_key":         sk,
                "description":      desc,
                "step_category":    cat,
                "technique_family": tf,
                "dsp_stage":        stage,
                "step_order":       i + 1,
            }
            for i, (sk, desc, cat, tf, stage) in enumerate(zip(
                record["step_keys"],
                record["step_descriptions"],
                record["step_categories"],
                record["technique_families"],
                record["dsp_stages"],
            ))
        ]
        routes.append({
            "route_id":  "__".join(record["step_keys"]),
            "steps":     steps,
            "num_steps": record["num_steps"],
            "target": {
                "spec_id":         record["target_spec_id"],
                "target_grade":    record["target_grade"],
                "purity_min":      record["target_purity"],
                "purity_unit":     record["purity_unit"],
                "achieved_purity": record["achieved_purity"],
            },
            "product_stream": {
                "stream_key":       record["product_stream"],
                "temperature":      record["product_temp"],
                "temperature_unit": record["product_temp_unit"],
            },
        })
    return routes


def _extract_verification_summary(verify_result: dict) -> dict:
    """
    Map verification_shared.verify_route() output to the flat dict
    expected by Agent 2 and Agent 3.
    """
    if verify_result["verified"]:
        matches = verify_result.get("exact_matches") or verify_result.get("partial_matches") or []
        first = matches[0] if matches else {}
        return {
            "verified":   True,
            "pathway_id": first.get("pathway_id"),
            "paper_id":   first.get("paper_id"),
            "route_name": first.get("route_name"),
        }
    return {
        "verified":   False,
        "pathway_id": None,
        "paper_id":   None,
        "route_name": None,
    }


@tool
def get_all_routes(feed_type: str, target_purity_min: float, verified_only: bool = False) -> dict:
    """
    Discover all lactic acid purification routes from a given feed type that
    meet or exceed a minimum purity threshold, by traversing the process DAG
    in the knowledge graph.

    Use this as your PRIMARY discovery tool. Call it ONCE per query after
    get_feed_info. Returns every feasible route as an ordered list of
    ProcessStep keys, covering ALL TargetSpecs with purity >= target_purity_min.

    Each route already includes a "verification" field indicating whether
    it matches a literature Pathway — no separate verify_against_pathway
    call is needed.

    Args:
        feed_type: FeedType.name property in the KG.
                   Examples: "fermentation_broth", "whey_ultrafiltration_permeate",
                   "biomass_derived_reaction_liquor", "candy_waste_digestate_broth",
                   "glucose_fermentation_medium", "synthetic_lactic_acid_solution"

        target_purity_min: Minimum purity as a decimal fraction (0–1).
                           Examples: 0.50 (50 wt%), 0.82 (82 wt%),
                                     0.87 (87 wt%), 0.88 (88 wt%)

        verified_only: If True, return ONLY routes that exactly match a
                       literature Pathway. Default False.

    Returns:
        dict with keys:
            status  — "ok" | "no_routes" | "error"
            data    — route list with verification attached per route
            message — human-readable summary
    """
    try:
        raw_records = neo4j_conn.query(
            _ROUTE_CYPHER,
            {"feed_type": feed_type, "target_purity_min": target_purity_min},
        )

        if not raw_records:
            return {
                "status": "no_routes",
                "data":   None,
                "message": (
                    f"No routes found from feed_type='{feed_type}' with "
                    f"target_purity_min>={target_purity_min}. "
                    "Check that feed_type matches KG exactly."
                ),
            }

        all_routes = _process_routes(raw_records)

        # Fetch pathways once, then verify all routes in Python
        pathway_records, recovery_step_keys = fetch_pathways_and_recovery_steps()

        for route in all_routes:
            step_keys      = [s["step_key"] for s in route["steps"]]
            verify_result  = verify_route(step_keys, pathway_records, recovery_step_keys)
            route["verification"] = _extract_verification_summary(verify_result)

        if verified_only:
            verified_routes = [r for r in all_routes if r["verification"]["verified"]]
            if not verified_routes:
                return {
                    "status": "no_routes",
                    "data": {
                        "feed_type":            feed_type,
                        "target_purity_min":    target_purity_min,
                        "verified_only":        True,
                        "num_routes_found":     0,
                        "num_total_dag_routes": len(all_routes),
                        "routes":               [],
                    },
                    "message": (
                        f"No literature-verified routes found from '{feed_type}' "
                        f"with purity >= {target_purity_min}. "
                        f"{len(all_routes)} DAG route(s) exist but none match a single-paper Pathway. "
                        "Try verified_only=False to see all routes."
                    ),
                }
            return {
                "status": "ok",
                "data": {
                    "feed_type":            feed_type,
                    "target_purity_min":    target_purity_min,
                    "verified_only":        True,
                    "num_routes_found":     len(verified_routes),
                    "num_total_dag_routes": len(all_routes),
                    "routes":               verified_routes,
                },
                "message": (
                    f"Found {len(verified_routes)} literature-verified route(s) "
                    f"from '{feed_type}' with purity >= {target_purity_min} "
                    f"(out of {len(all_routes)} total DAG routes)."
                ),
            }

        return {
            "status": "ok",
            "data": {
                "feed_type":        feed_type,
                "target_purity_min": target_purity_min,
                "verified_only":    False,
                "num_routes_found": len(all_routes),
                "routes":           all_routes,
            },
            "message": (
                f"Found {len(all_routes)} route(s) from '{feed_type}' "
                f"with target_purity_min >= {target_purity_min}. "
                "Each route includes verification status."
            ),
        }

    except Exception as e:
        return {
            "status":  "error",
            "data":    None,
            "message": f"Neo4j query error in get_all_routes: {e}",
        }
