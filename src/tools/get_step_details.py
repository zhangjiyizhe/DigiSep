"""
Tool 3: get_step_details

Retrieves complete information about a single ProcessStep:
  - Core properties (step_key, category, description, key_reagent)
  - Category-specific properties (separation_method, reaction_type, sub_steps, etc.)
  - All role-connected ChemicalSpecies (catalysts, solvents, reagents, reactants, entrainers, adsorbents)
  - Auxiliary recovery step (if any)

Note: Uses 6 OPTIONAL MATCHes which can cause Cartesian products.
      In practice each step has 1-2 roles, so collect(DISTINCT) handles it.
"""

from langchain_core.tools import tool
from src.tools.neo4j_connection import neo4j_conn


CYPHER_STEP_DETAILS = """
MATCH (ps:ProcessStep {step_key: $step_key})

OPTIONAL MATCH (ps)-[:HAS_CATALYST]->(cat:ChemicalSpecies)
OPTIONAL MATCH (ps)-[:HAS_SOLVENT]->(sol:ChemicalSpecies)
OPTIONAL MATCH (ps)-[rea_rel:HAS_REAGENT]->(rea:ChemicalSpecies)
OPTIONAL MATCH (ps)-[:HAS_REACTANT]->(rct:ChemicalSpecies)
OPTIONAL MATCH (ps)-[:HAS_ENTRAINER]->(ent:ChemicalSpecies)
OPTIONAL MATCH (ps)-[:HAS_ADSORBENT]->(ads:ChemicalSpecies)

OPTIONAL MATCH (ps)-[:HAS_RECOVERY_STEP]->(rec_ps:ProcessStep)

RETURN
    ps.step_key AS step_key,
    ps.step_category AS step_category,
    ps.description AS description,
    ps.key_reagent AS key_reagent,

    ps.unit_op_class AS unit_op_class,
    ps.separation_method AS separation_method,
    ps.exploited_property AS exploited_property,
    ps.combination_method AS combination_method,
    ps.reaction_type AS reaction_type,
    ps.sub_steps AS sub_steps,
    ps.technique_family AS technique_family,

    collect(DISTINCT {name: cat.name_canonical, cas: cat.cas_number}) AS catalysts,
    collect(DISTINCT {name: sol.name_canonical, cas: sol.cas_number}) AS solvents,
    collect(DISTINCT {name: rea.name_canonical, cas: rea.cas_number, role: rea_rel.role}) AS reagents,
    collect(DISTINCT {name: rct.name_canonical, cas: rct.cas_number}) AS reactants,
    collect(DISTINCT {name: ent.name_canonical, cas: ent.cas_number}) AS entrainers,
    collect(DISTINCT {name: ads.name_canonical, cas: ads.cas_number}) AS adsorbents,

    rec_ps.step_key AS recovery_step_key,
    rec_ps.description AS recovery_step_description
"""


def _filter_null_entries(species_list: list[dict]) -> list[dict]:
    """Remove entries where name is None (from OPTIONAL MATCH with no match)."""
    return [s for s in species_list if s.get("name") is not None]


@tool
def get_step_details(step_key: str) -> dict:
    """
    Get complete details of a process step including its properties
    and all connected chemical species (catalysts, solvents, reagents, etc.)

    Args:
        step_key: ProcessStep.step_key (e.g. "aggregated__reactive_distillation__esterification__methanol")

    Returns:
        dict with step properties and all role-connected species
    """
    try:
        results = neo4j_conn.query(CYPHER_STEP_DETAILS, {"step_key": step_key})

        if not results:
            return {
                "status": "error",
                "data": None,
                "message": f"ProcessStep '{step_key}' not found in the knowledge graph",
            }

        r = results[0]

        # Build recovery step dict (or None)
        recovery_step = None
        if r["recovery_step_key"]:
            recovery_step = {
                "step_key": r["recovery_step_key"],
                "description": r["recovery_step_description"],
            }

        data = {
            "step_key": r["step_key"],
            "step_category": r["step_category"],
            "description": r["description"],
            "key_reagent": r["key_reagent"],
            "technique_family": r["technique_family"],
            # Category-specific fields (None if not applicable)
            "unit_op_class": r["unit_op_class"],
            "separation_method": r["separation_method"],
            "exploited_property": r["exploited_property"],
            "combination_method": r["combination_method"],
            "reaction_type": r["reaction_type"],
            "sub_steps": r["sub_steps"],
            # Role-connected species (filtered to remove null entries)
            "catalysts": _filter_null_entries(r["catalysts"]),
            "solvents": _filter_null_entries(r["solvents"]),
            "reagents": _filter_null_entries(r["reagents"]),
            "reactants": _filter_null_entries(r["reactants"]),
            "entrainers": _filter_null_entries(r["entrainers"]),
            "adsorbents": _filter_null_entries(r["adsorbents"]),
            # Auxiliary recovery step
            "recovery_step": recovery_step,
        }

        return {
            "status": "ok",
            "data": data,
            "message": f"Step details for {step_key}",
        }

    except Exception as e:
        return {
            "status": "error",
            "data": None,
            "message": f"Neo4j query error in get_step_details: {type(e).__name__}: {e}",
        }
