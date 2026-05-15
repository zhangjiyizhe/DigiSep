"""
Tool 4: get_decision_rules

Retrieves all DecisionRules governing a specific ProcessStep:
  - Constraints, phenomena, design rules
  - Condition/action pairs with confidence scores
  - Phenomenon details (name, category, mechanism, species involved)

Simple 1-hop query: ProcessStep -[GOVERNED_BY]-> DecisionRule
"""

from langchain_core.tools import tool
from src.tools.neo4j_connection import neo4j_conn


CYPHER_DECISION_RULES = """
MATCH (ps:ProcessStep {step_key: $step_key})-[:GOVERNED_BY]->(dr:DecisionRule)
RETURN
    dr.rule_key AS rule_key,
    dr.condition AS condition,
    dr.action AS action,
    dr.rule_type AS rule_type,
    dr.confidence AS confidence,
    dr.is_negative AS is_negative,
    dr.phenomenon_name AS phenomenon_name,
    dr.phenomenon_category AS phenomenon_category,
    dr.mechanism AS mechanism,
    dr.species_involved AS species_involved,
    [l IN labels(dr) WHERE l IN ['DesignConstraint','DesignGuideline','Observation']][0] AS decision_label
    ORDER BY dr.rule_type, dr.confidence DESC
"""

# Check if step exists (to distinguish "no rules" from "step not found")
CYPHER_CHECK_STEP = """
MATCH (ps:ProcessStep {step_key: $step_key})
RETURN ps.step_key AS step_key
LIMIT 1
"""


@tool
def get_decision_rules(step_key: str) -> dict:
    """
    Get all decision rules (constraints, phenomena, design rules)
    governing a specific process step.

    Args:
        step_key: ProcessStep.step_key

    Returns:
        dict with list of decision rules
    """
    try:
        params = {"step_key": step_key}

        # Check if step exists
        step_check = neo4j_conn.query(CYPHER_CHECK_STEP, params)
        if not step_check:
            return {
                "status": "error",
                "data": None,
                "message": f"ProcessStep '{step_key}' not found in the knowledge graph",
            }

        results = neo4j_conn.query(CYPHER_DECISION_RULES, params)

        rules = []
        for r in results:
            rule = {
                "rule_key": r["rule_key"],
                "condition": r["condition"],
                "action": r["action"],
                "rule_type": r["rule_type"],
                "decision_label": r["decision_label"],
                "confidence": r["confidence"],
                "is_negative": r["is_negative"],
                "phenomenon": {
                    "name": r["phenomenon_name"],
                    "category": r["phenomenon_category"],
                    "mechanism": r["mechanism"],
                    "species_involved": r["species_involved"],
                },
            }
            rules.append(rule)

        data = {
            "step_key": step_key,
            "num_rules": len(rules),
            "rules": rules,
        }

        return {
            "status": "ok",
            "data": data,
            "message": f"Found {len(rules)} decision rule(s) for {step_key}",
        }

    except Exception as e:
        return {
            "status": "error",
            "data": None,
            "message": f"Neo4j query error in get_decision_rules: {type(e).__name__}: {e}",
        }
