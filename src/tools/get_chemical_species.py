"""
Tool 7: get_chemical_species

On-demand lookup of a ChemicalSpecies by CAS number or canonical name.
Returns full properties (pKa, boiling point, solubility, density, etc.)

Single-node query using cs {.*} to return all properties.
"""

from langchain_core.tools import tool
from src.tools.neo4j_connection import neo4j_conn


CYPHER_CHEMICAL_SPECIES = """
MATCH (cs:ChemicalSpecies)
WHERE cs.cas_number = $identifier OR cs.name_canonical = $identifier
RETURN cs {.*} AS species
LIMIT 1
"""


@tool
def get_chemical_species(identifier: str) -> dict:
    """
    Look up a chemical species by CAS number or canonical name.

    Args:
        identifier: CAS number (e.g. "50-21-5") or name_canonical (e.g. "lactic_acid")

    Returns:
        dict with all species properties
    """
    try:
        results = neo4j_conn.query(CYPHER_CHEMICAL_SPECIES, {"identifier": identifier})

        if not results:
            return {
                "status": "error",
                "data": None,
                "message": f"ChemicalSpecies '{identifier}' not found in the knowledge graph",
            }

        species = results[0]["species"]

        # Build human-readable message
        name = species.get("name", species.get("name_canonical", identifier))
        cas = species.get("cas_number", "unknown CAS")
        message = f"Found: {name} (CAS {cas})"

        return {
            "status": "ok",
            "data": species,
            "message": message,
        }

    except Exception as e:
        return {
            "status": "error",
            "data": None,
            "message": f"Neo4j query error in get_chemical_species: {type(e).__name__}: {e}",
        }
