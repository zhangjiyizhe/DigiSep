"""
Shared verification logic for route-pathway matching.

Used by get_all_routes for verified_only filtering and per-route
verification status.

Superset match uses an order-aware subsequence check (not order-blind set
membership), so a discovered route that contains extra steps still verifies
when the Pathway steps appear in the correct relative order within it.
"""

from src.tools.neo4j_connection import neo4j_conn


CYPHER_ALL_PATHWAYS = """
MATCH (pw:Pathway)-[inc:INCLUDES_STEP]->(ps:ProcessStep)
OPTIONAL MATCH (pw)-[:REPORTED_IN]->(p:Paper)
WITH pw, p,
     inc.step_order AS step_order,
     ps.step_key    AS step_key
ORDER BY pw.pathway_id, step_order
WITH pw, p,
     collect(step_key) AS pathway_steps
RETURN
    pw.pathway_id    AS pathway_id,
    pw.route_name    AS route_name,
    pw.step_sequence AS step_sequence,
    pw.num_steps     AS num_steps,
    pathway_steps,
    p.paper_id       AS paper_id,
    p.title          AS paper_title
"""

CYPHER_RECOVERY_STEPS = """
MATCH ()-[:HAS_RECOVERY_STEP]->(ps:ProcessStep)
RETURN collect(DISTINCT ps.step_key) AS recovery_step_keys
"""


def fetch_pathways_and_recovery_steps() -> tuple[list[dict], set[str]]:
    """
    Fetch all Pathway records and recovery step keys from Neo4j.
    Returns (pathway_records, recovery_step_keys).
    """
    pathway_records = neo4j_conn.query(CYPHER_ALL_PATHWAYS)

    recovery_result = neo4j_conn.query(CYPHER_RECOVERY_STEPS)
    recovery_step_keys = set(
        recovery_result[0]["recovery_step_keys"]
    ) if recovery_result and recovery_result[0]["recovery_step_keys"] else set()

    return pathway_records, recovery_step_keys


def _is_subsequence(needle: list[str], haystack: list[str]) -> bool:
    """
    Check if needle appears as an ordered subsequence in haystack.
    Elements do not need to be contiguous, but must appear in order.

    Example:
      needle   = [UF, IX, RO, evap]
      haystack = [fermentation, UF, IX, RO, evap]
      → True (all needle elements appear in order in haystack)

      needle   = [UF, RO, IX]   (wrong order)
      haystack = [UF, IX, RO]
      → False
    """
    it = iter(haystack)
    return all(step in it for step in needle)


def verify_route(
    discovered_steps: list[str],
    pathway_records: list[dict],
    recovery_step_keys: set[str],
) -> dict:
    """
    Compare a discovered route against all Pathways.

    Before comparison, recovery steps (HAS_RECOVERY_STEP targets) are
    filtered out of each Pathway's step list (Q1 fix — these are auxiliary
    solvent recovery columns, not part of the main product path).

    Matching logic (in priority order):
      1. Exact match: Pathway main steps == discovered steps (same order)
      2. Superset match: Pathway main steps are an ordered subsequence of
         discovered steps (discovered has extra steps, e.g. fermentation
         as first step, but Pathway steps all appear in correct order)
      3. Subset match: discovered steps are an ordered subsequence of
         Pathway main steps (discovered is a prefix/suffix of Pathway)

    Returns:
        dict with keys: verification, exact_matches, partial_matches
    """
    matches         = []
    partial_matches = []

    for pw in pathway_records:
        # Filter out auxiliary recovery steps from Pathway step list
        pw_main_steps = [
            s for s in pw["pathway_steps"]
            if s not in recovery_step_keys
        ]

        if not pw_main_steps:
            continue

        # ── 1. Exact match ────────────────────────────────────────────────
        if pw_main_steps == discovered_steps:
            matches.append({
                "pathway_id": pw["pathway_id"],
                "route_name": pw["route_name"],
                "paper_id":   pw["paper_id"],
                "match_type": "exact",
            })

        # ── 2. Superset match: Pathway is ordered subsequence of discovered
        #    i.e. discovered has EXTRA steps but covers the full Pathway ───
        elif (
            len(discovered_steps) > len(pw_main_steps)
            and _is_subsequence(pw_main_steps, discovered_steps)
        ):
            novel = [s for s in discovered_steps if s not in pw_main_steps]
            partial_matches.append({
                "pathway_id":  pw["pathway_id"],
                "route_name":  pw["route_name"],
                "paper_id":    pw["paper_id"],
                "match_type":  "superset",
                "novel_steps": novel,
            })

        # ── 3. Subset match: discovered is ordered subsequence of Pathway
        #    i.e. Pathway has MORE steps than discovered ──────────────────
        elif (
            len(discovered_steps) < len(pw_main_steps)
            and _is_subsequence(discovered_steps, pw_main_steps)
        ):
            extra = [s for s in pw_main_steps if s not in discovered_steps]
            partial_matches.append({
                "pathway_id": pw["pathway_id"],
                "route_name": pw["route_name"],
                "paper_id":   pw["paper_id"],
                "match_type": "subset",
                "extra_steps": extra,
            })

    if matches:
        verification = "verified"
    elif partial_matches:
        # Superset match = discovered route CONTAINS the complete Pathway
        # sequence as an ordered subsequence. The route is longer but the
        # full validated sequence is present → treat as verified.
        # Subset match = discovered route is only PART of a Pathway → not verified.
        has_superset = any(m["match_type"] == "superset" for m in partial_matches)
        verification = "verified" if has_superset else "partially_verified"
    else:
        verification = "unverified"

    return {
        "verification":  verification,
        "verified":      verification == "verified",   # convenience bool for Agent 3
        "exact_matches":   matches,
        "partial_matches": partial_matches,
    }