# scripts/main.py
# Entry point for single-query and resume-from-cache runs.
#
# Usage (single query):
#   python scripts/main.py "your query here"
#
# Usage (resume Agent 3 from existing Agent 2 cache):
#   python scripts/main.py --resume outputs/cache/agent2_T1-01.json "your query"
#
# For experiment batches (T1–T4, ablation conditions), use:
#   python scripts/run_experiments.py --help

import sys
import os
import json
import time
from datetime import datetime

_SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
_PROJECT_DIR = os.path.dirname(_SCRIPT_DIR)   # project root (holds src/ and config.py)
if _PROJECT_DIR not in sys.path:
    sys.path.insert(0, _PROJECT_DIR)

from src.pipeline import run_dsp_discovery, run_dsp_discovery_from_cache


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


def _save_txt_report(result: dict, query: str, elapsed: float, timestamp: str) -> str:
    os.makedirs("outputs", exist_ok=True)
    path = f"outputs/report_{timestamp}.txt"

    screened  = result.get("screened_routes") or []
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


def main():
    args = sys.argv[1:]

    # ── --resume <cache.json> "query" ─────────────────────────────────────
    if "--resume" in args:
        idx = args.index("--resume")
        if idx + 1 >= len(args):
            print("Usage: python scripts/main.py --resume <cache.json> 'query'")
            sys.exit(1)
        cache_file = args[idx + 1]
        remaining  = args[idx + 2:]
        query      = " ".join(remaining) if remaining else None

        if not query:
            print("Usage: python scripts/main.py --resume <cache.json> 'query'")
            sys.exit(1)
        if not os.path.exists(cache_file):
            print(f"Cache file not found: {cache_file}")
            sys.exit(1)

        print(f"\nResume mode: {cache_file}")
        start = time.time()
        with open(cache_file, "r", encoding="utf-8") as f:
            discovery_data = json.load(f)

        result  = run_dsp_discovery_from_cache(query, discovery_data)
        elapsed = time.time() - start

        tier1, tier2, tier3 = _parse_tier_counts(result)
        critical, warning, note = _parse_flag_counts(result)
        print(
            f"\nTier1={tier1}  Tier2={tier2}  Tier3={tier3}  |  "
            f"CRITICAL={critical}  WARNING={warning}  NOTE={note}  |  {elapsed:.1f}s"
        )
        if result.get("zero_route_message"):
            print(f"[INFO] {result['zero_route_message']}")
        _save_txt_report(result, query, elapsed, datetime.now().strftime("%Y%m%d_%H%M%S"))
        return

    # ── Single query mode ────────────────────────────────────────────────
    if args:
        query = " ".join(args)
    else:
        print("=" * 70)
        print("Lactic Acid DSP Multi-Agent System")
        print("=" * 70)
        print("\nUsage:")
        print("  python scripts/main.py 'query'")
        print("  python scripts/main.py --resume cache.json 'query'")
        print("  python scripts/run_experiments.py --help   (for T1–T4 batches)")
        print()
        try:
            user_input = input("Your query (or press Enter for default): ").strip()
        except (EOFError, KeyboardInterrupt):
            user_input = ""
        query = user_input or (
            "Find all lactic acid purification routes from fermentation broth "
            "with at least 88 wt% purity."
        )

    print(f"\nQuery: {query}")
    print("-" * 70)
    print("Running pipeline...\n")

    start   = time.time()
    result  = run_dsp_discovery(query)
    elapsed = time.time() - start

    tier1, tier2, tier3 = _parse_tier_counts(result)
    critical, warning, note = _parse_flag_counts(result)
    routes_found = (result.get("discovery_data") or {}).get("total_routes_found", 0)

    print(f"\nRoutes: {routes_found}  Tier1={tier1}  Tier2={tier2}  Tier3={tier3}")
    print(f"Flags: CRITICAL={critical}  WARNING={warning}  NOTE={note}")
    if result.get("ambiguous"):
        alt = result.get("alternative_feed_type", "")
        print(f"[AMBIGUOUS] Feed type uncertain. Alternative candidate: {alt}")
    if result.get("zero_route_message"):
        print(f"[INFO] {result['zero_route_message']}")
    print(f"Pipeline completed in {elapsed:.1f}s")

    _save_txt_report(result, query, elapsed, datetime.now().strftime("%Y%m%d_%H%M%S"))


if __name__ == "__main__":
    main()
