"""
Tool 2: get_feed_info

Retrieves complete information about a FeedType:
  - Descriptive properties (name, phase, typical conditions)
  - Associated feed streams (T, P, flow rate, composition)
  - Key chemical components (target product, solvent, impurities)

Uses 3 sub-queries to avoid Cartesian product from multiple OPTIONAL MATCHes.
"""

from langchain_core.tools import tool
from src.tools.neo4j_connection import neo4j_conn


# --- Cypher Templates (3 sub-queries) ---

CYPHER_FEED_PROPS = """
MATCH (ft:FeedType {name: $feed_type})
RETURN ft {.*} AS feed_props
"""

CYPHER_FEED_STREAMS = """
MATCH (ft:FeedType {name: $feed_type})-[:HAS_FEED_STREAM]->(fs:Stream)
OPTIONAL MATCH (fs)-[comp:HAS_COMPONENT]->(cs:ChemicalSpecies)
RETURN fs.stream_key AS stream_key,
       fs.temperature AS temperature,
       fs.temperature_unit AS temperature_unit,
       fs.pressure AS pressure,
       fs.pressure_unit AS pressure_unit,
       fs.total_flow_rate AS total_flow_rate,
       fs.flow_rate_unit AS flow_rate_unit,
       collect({
           species: cs.name_canonical,
           cas: cs.cas_number,
           mass_fraction: comp.mass_fraction,
           mole_fraction: comp.mole_fraction
       }) AS components
"""

CYPHER_KEY_COMPONENTS = """
MATCH (ft:FeedType {name: $feed_type})-[kc:HAS_KEY_COMPONENT]->(cs:ChemicalSpecies)
RETURN cs.name_canonical AS species,
       cs.cas_number AS cas,
       kc.role AS role,
       kc.typical_concentration AS typical_concentration
"""


@tool
def get_feed_info(feed_type: str) -> dict:
    """
    Get complete information about a feed type including its properties,
    associated feed streams, and key chemical components.

    Args:
        feed_type: FeedType.name (e.g. "fermentation_broth")

    Returns:
        dict with feed properties, streams, and key components
    """
    try:
        params = {"feed_type": feed_type}

        # Sub-query A: FeedType properties
        props_result = neo4j_conn.query(CYPHER_FEED_PROPS, params)
        if not props_result:
            return {
                "status": "error",
                "data": None,
                "message": f"FeedType '{feed_type}' not found in the knowledge graph",
            }

        feed_props = props_result[0]["feed_props"]

        # Sub-query B: Feed streams + composition
        streams_result = neo4j_conn.query(CYPHER_FEED_STREAMS, params)

        feed_streams = []
        for record in streams_result:
            # Filter out null components (from OPTIONAL MATCH with no HAS_COMPONENT)
            components = [
                c for c in record["components"]
                if c.get("species") is not None
            ]
            feed_streams.append({
                "stream_key": record["stream_key"],
                "temperature": record["temperature"],
                "temperature_unit": record["temperature_unit"],
                "pressure": record["pressure"],
                "pressure_unit": record["pressure_unit"],
                "total_flow_rate": record["total_flow_rate"],
                "flow_rate_unit": record["flow_rate_unit"],
                "components": components,
            })

        # Sub-query C: Key components
        key_comp_result = neo4j_conn.query(CYPHER_KEY_COMPONENTS, params)

        key_components = [
            {
                "species": record["species"],
                "cas": record["cas"],
                "role": record["role"],
                "typical_concentration": record["typical_concentration"],
            }
            for record in key_comp_result
        ]

        # Assemble return data
        data = {
            "name": feed_props.get("name"),
            "display_name": feed_props.get("display_name"),
            "phase": feed_props.get("phase"),
            "description": feed_props.get("description"),
            "typical_la_concentration": feed_props.get("typical_la_concentration"),
            "typical_temperature": feed_props.get("typical_temperature"),
            "typical_pH": feed_props.get("typical_pH"),
            "feed_streams": feed_streams,
            "key_components": key_components,
        }

        message = (
            f"Feed info for {feed_type}: "
            f"{len(feed_streams)} stream(s), "
            f"{len(key_components)} key component(s)"
        )

        return {"status": "ok", "data": data, "message": message}

    except Exception as e:
        return {
            "status": "error",
            "data": None,
            "message": f"Neo4j query error in get_feed_info: {type(e).__name__}: {e}",
        }
