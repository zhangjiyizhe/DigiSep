"""
Helper: List all available FeedTypes and TargetSpecs in Neo4j.
Run from project root: python -m tests.list_feed_and_targets

Use this to pick a feed_type + target_grade combination for testing.
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.tools.neo4j_connection import neo4j_conn


def main():
    print("\n" + "="*70)
    print("  Available FeedTypes and TargetSpecs in Neo4j")
    print("="*70)

    # All FeedTypes
    print("\n  ── FeedTypes ──")
    feed_results = neo4j_conn.query("""
        MATCH (ft:FeedType)
        OPTIONAL MATCH (ft)-[:FIRST_STEP]->(ps:ProcessStep)
        RETURN ft.name AS name,
               ft.display_name AS display_name,
               count(ps) AS num_first_steps
        ORDER BY ft.name
    """)
    for f in feed_results:
        has_dag = "✅ has DAG entry" if f["num_first_steps"] > 0 else "❌ no FIRST_STEP"
        print(f"    {f['name']:40s} {has_dag}")
        if f["display_name"]:
            print(f"      Display: {f['display_name']}")

    # All TargetSpecs
    print("\n  ── TargetSpecs ──")
    target_results = neo4j_conn.query("""
        MATCH (ts:TargetSpec)
        OPTIONAL MATCH (s:Stream)-[:HAS_PURITY]->(ts)
        RETURN ts.spec_id AS spec_id,
               ts.target_grade AS target_grade,
               ts.target_purity_min AS purity_min,
               ts.purity_unit AS purity_unit,
               ts.display_name AS display_name,
               count(s) AS num_product_streams
        ORDER BY ts.target_grade, ts.spec_id
    """)
    for t in target_results:
        purity = f"{t['purity_min']} {t['purity_unit']}" if t['purity_min'] else "not specified"
        grade = t['target_grade'] or '(none)'
        print(f"    {t['spec_id']:40s} grade={grade:12s} purity={purity}")
        print(f"      {t['display_name'] or ''} ({t['num_product_streams']} product stream(s) reach this)")

    # Cross-check: which feed+grade combos actually have routes?
    print("\n  ── Feed + Grade combinations with routes ──")
    combo_results = neo4j_conn.query("""
        MATCH (ft:FeedType)-[:FIRST_STEP]->(first:ProcessStep),
              path = (first)-[:HAS_NEXT_STEP*0..15]->(last:ProcessStep),
              (last)-[:HAS_PRODUCT]->(ps:Stream)-[:HAS_PURITY]->(ts:TargetSpec)
        RETURN ft.name AS feed, ts.target_grade AS grade, count(DISTINCT [n IN nodes(path) | n.step_key]) AS num_routes
        ORDER BY ft.name, ts.target_grade
    """)
    for c in combo_results:
        grade = c['grade'] or '(none)'
        print(f"    {c['feed']:40s} → {grade:12s} ({c['num_routes']} route(s))")

    print("\n" + "="*70)
    print("  Pick a feed_type + target_grade from the list above,")
    print("  then run: python -m tests.run_option_c <feed_type> <target_grade>")
    print("="*70 + "\n")

    neo4j_conn.close()


if __name__ == "__main__":
    main()
