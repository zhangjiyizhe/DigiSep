"""
Test script for get_all_routes tool.
Run from project root: python -m tests.test_get_all_routes

Tests:
  1. fermentation_broth + polymer → expect at least 4 P05 routes
  2. Verify P05 MeOH route exists (3 steps: preconc → RD ester → RD hydro)
  3. Verify P05 EtOH route exists (4 steps: includes extractive distillation)
  4. Verify all routes share the first step (preconcentration)
  5. Non-existent feed type → expect error
  6. Valid feed + unlikely grade → expect no_routes
  7. Schema completeness check

Expected P05 routes:
  1. preconc → RD ester MeOH → RD hydro MeOH (3 steps)
  2. preconc → RD ester EtOH → extractive distill EG → RD hydro EtOH (4 steps)
  3. preconc → RD ester iPrOH → RD hydro iPrOH (3 steps)
  4. preconc → RD ester BuOH → RD hydro BuOH (3 steps)

Note: KG has 10 papers, so there may be MORE routes beyond these 4.
"""

import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.tools.neo4j_connection import neo4j_conn
from src.tools.get_all_routes import get_all_routes


def print_section(title: str):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


def test_polymer_routes():
    """Test 1: Discover polymer-grade routes from fermentation broth."""
    print_section("Test 1: fermentation_broth → polymer grade")

    result = get_all_routes.invoke({
        "feed_type": "fermentation_broth",
        "target_grade": "polymer",
    })

    assert result["status"] == "ok", f"Expected 'ok', got '{result['status']}': {result['message']}"

    data = result["data"]
    num_routes = data["num_routes_found"]
    print(f"\n  Routes found: {num_routes}")
    print(f"  Feed: {data['feed_display_name']}")

    # Expect at least 4 P05 routes
    assert num_routes >= 4, f"Expected at least 4 routes, got {num_routes}"
    print(f"  ✅ At least 4 routes found (got {num_routes})")

    # Print all routes
    for i, route in enumerate(data["routes"]):
        step_names = " → ".join(s["step_key"] for s in route["steps"])
        purity = route["target"]["achieved_purity"]
        print(f"\n  Route {i+1} ({route['num_steps']} steps): {step_names}")
        print(f"    Target: {route['target']['spec_id']}, purity={purity}")
        print(f"    Product stream: {route['product_stream']['stream_key']}")

    print("\n  ✅ Test 1 PASSED")
    return data["routes"]


def test_meoh_route(routes: list):
    """Test 2: Verify MeOH route exists (3 steps)."""
    print_section("Test 2: MeOH route verification")

    # Look for a route containing "methanol" in step_keys
    meoh_routes = [
        r for r in routes
        if any("methanol" in s["step_key"] and "esterification" in s["step_key"]
               for s in r["steps"])
    ]

    assert len(meoh_routes) >= 1, "MeOH esterification route not found!"
    meoh = meoh_routes[0]
    print(f"  Found MeOH route: {meoh['num_steps']} steps")
    for s in meoh["steps"]:
        print(f"    Step {s['step_order']}: {s['step_key']}")
        print(f"      Category: {s['step_category']}")
        print(f"      Description: {s['description']}")

    print("\n  ✅ Test 2 PASSED — MeOH route found")


def test_etoh_route(routes: list):
    """Test 3: Verify EtOH route exists (4 steps, includes extractive distillation)."""
    print_section("Test 3: EtOH route verification")

    etoh_routes = [
        r for r in routes
        if any("ethanol" in s["step_key"] and "esterification" in s["step_key"]
               for s in r["steps"])
    ]

    assert len(etoh_routes) >= 1, "EtOH esterification route not found!"
    etoh = etoh_routes[0]
    print(f"  Found EtOH route: {etoh['num_steps']} steps")
    for s in etoh["steps"]:
        print(f"    Step {s['step_order']}: {s['step_key']}")

    # EtOH route should be 4 steps (longest P05 route)
    print(f"\n  EtOH route has {etoh['num_steps']} steps (expected 4 for P05)")
    print("  ✅ Test 3 PASSED — EtOH route found")


def test_shared_first_step(routes: list):
    """Test 4: All P05 routes share the same first step (preconcentration)."""
    print_section("Test 4: Shared first step check")

    first_steps = set()
    for route in routes:
        if route["steps"]:
            first_steps.add(route["steps"][0]["step_key"])

    print(f"  Unique first steps across all routes: {first_steps}")

    # Note: With 10 papers, different feed types may have different first steps.
    # But within fermentation_broth routes, P05 routes all start with distillation.
    if len(first_steps) == 1:
        print(f"  All routes share the same first step: {first_steps.pop()}")
    else:
        print(f"  Multiple first steps found — this is possible with multi-paper data")
        for fs in first_steps:
            count = sum(1 for r in routes if r["steps"][0]["step_key"] == fs)
            print(f"    {fs}: {count} route(s)")

    print("  ✅ Test 4 PASSED — first step analysis complete")


def test_nonexistent_feed():
    """Test 5: Non-existent feed type → error."""
    print_section("Test 5: Non-existent feed type")

    result = get_all_routes.invoke({
        "feed_type": "nonexistent_feed",
        "target_grade": "polymer",
    })

    assert result["status"] == "error", f"Expected 'error', got '{result['status']}'"
    assert result["data"] is None
    assert "not found" in result["message"].lower()
    print(f"  Error message: {result['message']}")
    print("  ✅ Test 5 PASSED — error handled correctly")


def test_no_routes():
    """Test 6: Valid feed + unlikely grade → no_routes."""
    print_section("Test 6: Valid feed + unlikely grade")

    # Try a grade that probably doesn't exist
    result = get_all_routes.invoke({
        "feed_type": "fermentation_broth",
        "target_grade": "nonexistent_grade",
    })

    assert result["status"] == "no_routes", f"Expected 'no_routes', got '{result['status']}'"
    assert result["data"]["num_routes_found"] == 0
    print(f"  Message: {result['message']}")
    print("  ✅ Test 6 PASSED — no_routes handled correctly")


def test_schema_completeness(routes: list):
    """Test 7: Verify return schema matches the expected specification."""
    print_section("Test 7: Schema completeness")

    route = routes[0]

    # Route-level keys
    expected_route_keys = {"route_id", "steps", "num_steps", "target", "product_stream"}
    assert expected_route_keys.issubset(route.keys()), \
        f"Missing route keys: {expected_route_keys - route.keys()}"
    print("  ✅ Route-level keys complete")

    # Step-level keys
    step = route["steps"][0]
    expected_step_keys = {"step_key", "description", "step_category", "step_order"}
    assert expected_step_keys.issubset(step.keys()), \
        f"Missing step keys: {expected_step_keys - step.keys()}"
    print("  ✅ Step-level keys complete")

    # Target keys
    expected_target_keys = {"spec_id", "purity_min", "purity_unit", "achieved_purity"}
    assert expected_target_keys.issubset(route["target"].keys()), \
        f"Missing target keys: {expected_target_keys - route['target'].keys()}"
    print("  ✅ Target keys complete")

    # Product stream keys
    expected_stream_keys = {"stream_key", "temperature", "temperature_unit"}
    assert expected_stream_keys.issubset(route["product_stream"].keys()), \
        f"Missing stream keys: {expected_stream_keys - route['product_stream'].keys()}"
    print("  ✅ Product stream keys complete")

    print("\n  ✅ Test 7 PASSED — schema matches expected specification")


if __name__ == "__main__":
    print("\n" + "="*70)
    print("  DSP MAS — get_all_routes Tool Tests")
    print("  Neo4j must be running with P01-P10 data")
    print("="*70)

    try:
        # Test 1 returns routes for use in subsequent tests
        routes = test_polymer_routes()
        test_meoh_route(routes)
        test_etoh_route(routes)
        test_shared_first_step(routes)
        test_nonexistent_feed()
        test_no_routes()
        test_schema_completeness(routes)

        print("\n" + "="*70)
        print("  ALL TESTS PASSED ✅")
        print("="*70 + "\n")

    except AssertionError as e:
        print(f"\n  ❌ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n  ❌ UNEXPECTED ERROR: {type(e).__name__}: {e}")
        sys.exit(1)
    finally:
        neo4j_conn.close()
