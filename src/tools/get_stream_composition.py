"""
Tool 6: get_stream_composition

Retrieves a Stream's thermodynamic properties and full composition
(connected ChemicalSpecies with mass/mole fractions).

Simple 1-hop query: Stream -[HAS_COMPONENT]-> ChemicalSpecies
"""

from langchain_core.tools import tool
from src.tools.neo4j_connection import neo4j_conn


CYPHER_STREAM_COMPOSITION = """
MATCH (s:Stream {stream_key: $stream_key})
OPTIONAL MATCH (s)-[comp:HAS_COMPONENT]->(cs:ChemicalSpecies)
RETURN
    s.stream_key AS stream_key,
    s.stream_type AS stream_type,
    s.phase AS phase,
    s.temperature AS temperature,
    s.temperature_unit AS temperature_unit,
    s.pressure AS pressure,
    s.pressure_unit AS pressure_unit,
    s.total_flow_rate AS total_flow_rate,
    s.flow_rate_unit AS flow_rate_unit,
    s.description AS description,
    collect({
        species: cs.name_canonical,
        cas: cs.cas_number,
        formula: cs.formula,
        mass_fraction: comp.mass_fraction,
        mole_fraction: comp.mole_fraction
    }) AS components
"""


@tool
def get_stream_composition(stream_key: str) -> dict:
    """
    Get the composition of a process stream (species and their fractions).

    Args:
        stream_key: Stream.stream_key (e.g. "hydrolysis__meoh__to__product")

    Returns:
        dict with stream properties and composition
    """
    try:
        results = neo4j_conn.query(CYPHER_STREAM_COMPOSITION, {"stream_key": stream_key})

        if not results:
            return {
                "status": "error",
                "data": None,
                "message": f"Stream '{stream_key}' not found in the knowledge graph",
            }

        r = results[0]

        # Filter out null components (from OPTIONAL MATCH with no HAS_COMPONENT)
        components = [
            c for c in r["components"]
            if c.get("species") is not None
        ]

        data = {
            "stream_key": r["stream_key"],
            "stream_type": r["stream_type"],
            "phase": r["phase"],
            "temperature": r["temperature"],
            "temperature_unit": r["temperature_unit"],
            "pressure": r["pressure"],
            "pressure_unit": r["pressure_unit"],
            "total_flow_rate": r["total_flow_rate"],
            "flow_rate_unit": r["flow_rate_unit"],
            "description": r["description"],
            "components": components,
        }

        return {
            "status": "ok",
            "data": data,
            "message": f"Stream {stream_key}: {len(components)} component(s)",
        }

    except Exception as e:
        return {
            "status": "error",
            "data": None,
            "message": f"Neo4j query error in get_stream_composition: {type(e).__name__}: {e}",
        }
