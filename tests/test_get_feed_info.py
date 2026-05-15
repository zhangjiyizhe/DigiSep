"""
Test script for get_feed_info tool.
Run from project root: python -m tests.test_get_feed_info

Tests:
  1. Neo4j health check
  2. get_feed_info("fermentation_broth") — expect P05 feed data
  3. get_feed_info("nonexistent_feed") — expect error status
  4. Verify returned data structure matches the expected schema
"""

import json
import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.tools.neo4j_connection import neo4j_conn
from src.tools.get_feed_info import get_feed_info


def print_section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def test_health_check():
    """Test 1: Verify Neo4j connectivity."""
    print_section("Test 1: Neo4j Health Check")
    healthy = neo4j_conn.health_check()
    print(f"  Health check result: {healthy}")
    assert healthy, "Neo4j health check failed! Is Neo4j running on bolt://localhost:7687?"
    print("  ✅ PASSED")


def test_feed_info_fermentation_broth():
    """Test 2: Query feed info for fermentation_broth (P05 data)."""
    print_section("Test 2: get_feed_info('fermentation_broth')")

    # Call the tool — note: LangChain @tool wraps the function,
    # so we call .invoke() with a dict for tool testing
    result = get_feed_info.invoke({"feed_type": "fermentation_broth"})

    print(f"\n  Full result:\n{json.dumps(result, indent=2, default=str)}")

    # Verify status
    assert result["status"] == "ok", f"Expected status 'ok', got '{result['status']}'"
    print("\n  ✅ Status is 'ok'")

    data = result["data"]

    # Verify feed properties exist
    assert data["name"] == "fermentation_broth", f"Expected name 'fermentation_broth', got '{data['name']}'"
    print(f"  ✅ Feed name: {data['name']}")
    print(f"     Display name: {data['display_name']}")
    print(f"     Phase: {data['phase']}")
    print(f"     Typical LA concentration: {data['typical_la_concentration']}")
    print(f"     Typical temperature: {data['typical_temperature']}")
    print(f"     Typical pH: {data['typical_pH']}")

    # Verify feed streams
    assert len(data["feed_streams"]) >= 1, "Expected at least 1 feed stream"
    print(f"\n  ✅ Feed streams found: {len(data['feed_streams'])}")
    for stream in data["feed_streams"]:
        print(f"     Stream: {stream['stream_key']}")
        print(f"       T = {stream['temperature']} {stream['temperature_unit']}")
        print(f"       P = {stream['pressure']} {stream['pressure_unit']}")
        print(f"       Flow = {stream['total_flow_rate']} {stream['flow_rate_unit']}")
        print(f"       Components: {len(stream['components'])}")
        for comp in stream["components"]:
            frac_info = ""
            if comp.get("mole_fraction") is not None:
                frac_info += f"mol={comp['mole_fraction']}"
            if comp.get("mass_fraction") is not None:
                if frac_info:
                    frac_info += ", "
                frac_info += f"mass={comp['mass_fraction']}"
            print(f"         {comp['species']} (CAS {comp['cas']}): {frac_info}")

    # Verify key components
    assert len(data["key_components"]) >= 1, "Expected at least 1 key component"
    print(f"\n  ✅ Key components found: {len(data['key_components'])}")
    for kc in data["key_components"]:
        print(f"     {kc['species']} (CAS {kc['cas']}): role={kc['role']}, conc={kc['typical_concentration']}")

    # Check for lactic acid as target product
    la_found = any(
        kc["species"] == "lactic_acid" for kc in data["key_components"]
    )
    assert la_found, "Expected lactic_acid in key components"
    print("\n  ✅ Lactic acid found in key components")

    print("\n  ✅ Test 2 PASSED")


def test_feed_info_nonexistent():
    """Test 3: Query a non-existent feed type — expect error."""
    print_section("Test 3: get_feed_info('nonexistent_feed')")

    result = get_feed_info.invoke({"feed_type": "nonexistent_feed"})
    print(f"  Result: {json.dumps(result, indent=2)}")

    assert result["status"] == "error", f"Expected status 'error', got '{result['status']}'"
    assert result["data"] is None, "Expected data to be None for error"
    assert "not found" in result["message"].lower(), "Expected 'not found' in error message"
    print("  ✅ Test 3 PASSED — error handled correctly")


def test_schema_completeness():
    """Test 4: Verify return schema matches the expected specification."""
    print_section("Test 4: Schema Completeness Check")

    result = get_feed_info.invoke({"feed_type": "fermentation_broth"})
    assert result["status"] == "ok"

    # Check top-level keys
    required_top = {"status", "data", "message"}
    assert required_top.issubset(result.keys()), f"Missing top-level keys: {required_top - result.keys()}"
    print("  ✅ Top-level keys: status, data, message")

    # Check data keys
    data = result["data"]
    expected_data_keys = {
        "name", "display_name", "phase", "description",
        "typical_la_concentration", "typical_temperature", "typical_pH",
        "feed_streams", "key_components"
    }
    assert expected_data_keys.issubset(data.keys()), f"Missing data keys: {expected_data_keys - data.keys()}"
    print("  ✅ Data keys match expected schema")

    # Check stream sub-keys
    if data["feed_streams"]:
        stream = data["feed_streams"][0]
        expected_stream_keys = {
            "stream_key", "temperature", "temperature_unit",
            "pressure", "pressure_unit",
            "total_flow_rate", "flow_rate_unit", "components"
        }
        assert expected_stream_keys.issubset(stream.keys()), f"Missing stream keys: {expected_stream_keys - stream.keys()}"
        print("  ✅ Stream keys match expected schema")

    # Check key component sub-keys
    if data["key_components"]:
        kc = data["key_components"][0]
        expected_kc_keys = {"species", "cas", "role", "typical_concentration"}
        assert expected_kc_keys.issubset(kc.keys()), f"Missing key component keys: {expected_kc_keys - kc.keys()}"
        print("  ✅ Key component keys match expected schema")

    print("\n  ✅ Test 4 PASSED — schema complete")


if __name__ == "__main__":
    print("\n" + "="*60)
    print("  DSP MAS — get_feed_info Tool Tests")
    print("  Neo4j must be running on bolt://localhost:7687")
    print("="*60)

    try:
        test_health_check()
        test_feed_info_fermentation_broth()
        test_feed_info_nonexistent()
        test_schema_completeness()

        print("\n" + "="*60)
        print("  ALL TESTS PASSED ✅")
        print("="*60 + "\n")

    except AssertionError as e:
        print(f"\n  ❌ TEST FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n  ❌ UNEXPECTED ERROR: {type(e).__name__}: {e}")
        sys.exit(1)
    finally:
        neo4j_conn.close()
