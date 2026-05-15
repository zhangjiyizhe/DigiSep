"""
Tool 5: get_cases_and_metrics

Retrieves Case data (per-paper design variables, operating conditions) and
associated PerformanceMetrics for a ProcessStep. Optional paper_id filter.

Query pattern: ProcessStep -[HAS_CASE]-> Case -[ACHIEVES]-> PerformanceMetric
                                         Case -[REPORTED_IN]-> Paper
"""

from langchain_core.tools import tool
from src.tools.neo4j_connection import neo4j_conn


CYPHER_CASES_AND_METRICS = """
MATCH (ps:ProcessStep {step_key: $step_key})-[:HAS_CASE]->(c:Case)
WHERE $paper_id IS NULL OR c.paper_id = $paper_id

OPTIONAL MATCH (c)-[:ACHIEVES]->(pm:PerformanceMetric)
OPTIONAL MATCH (c)-[:REPORTED_IN]->(p:Paper)

RETURN
    c.case_id AS case_id,
    c.paper_id AS paper_id,
    c.design_variables AS design_variables,
    c.feed_composition AS feed_composition,
    c.operating_temperature AS operating_temperature,
    c.operating_temperature_unit AS operating_temperature_unit,
    c.operating_pressure AS operating_pressure,
    c.operating_pressure_unit AS operating_pressure_unit,
    c.thermodynamic_model AS thermodynamic_model,
    c.simulation_software AS simulation_software,
    c.evidence_page AS evidence_page,
    c.evidence_table AS evidence_table,

    collect({
        metric_id: pm.metric_id,
        metric_type: pm.metric_type,
        value: pm.value,
        value_unit: pm.value_unit,
        species: pm.species,
        basis: pm.basis
    }) AS metrics,

    p.paper_id AS source_paper,
    p.title AS paper_title,
    p.year AS paper_year

ORDER BY c.paper_id
"""

CYPHER_CHECK_STEP = """
MATCH (ps:ProcessStep {step_key: $step_key})
RETURN ps.step_key AS step_key
LIMIT 1
"""


@tool
def get_cases_and_metrics(step_key: str, paper_id: str = None) -> dict:
    """
    Get case data (design variables) and performance metrics for a process step.
    Optionally filter by paper_id.

    Args:
        step_key: ProcessStep.step_key
        paper_id: Optional paper_id filter (e.g. "P05")

    Returns:
        dict with cases and their associated metrics
    """
    try:
        # Check if step exists
        step_check = neo4j_conn.query(CYPHER_CHECK_STEP, {"step_key": step_key})
        if not step_check:
            return {
                "status": "error",
                "data": None,
                "message": f"ProcessStep '{step_key}' not found in the knowledge graph",
            }

        params = {"step_key": step_key, "paper_id": paper_id}
        results = neo4j_conn.query(CYPHER_CASES_AND_METRICS, params)

        cases = []
        for r in results:
            # Filter out null metrics (from OPTIONAL MATCH with no PerformanceMetric)
            metrics = [
                m for m in r["metrics"]
                if m.get("metric_id") is not None
            ]

            case = {
                "case_id": r["case_id"],
                "paper_id": r["paper_id"],
                "design_variables": r["design_variables"],
                "feed_composition": r["feed_composition"],
                "operating_temperature": r["operating_temperature"],
                "operating_temperature_unit": r["operating_temperature_unit"],
                "operating_pressure": r["operating_pressure"],
                "operating_pressure_unit": r["operating_pressure_unit"],
                "thermodynamic_model": r["thermodynamic_model"],
                "simulation_software": r["simulation_software"],
                "evidence": {
                    "page": r["evidence_page"],
                    "table": r["evidence_table"],
                },
                "metrics": metrics,
                "source": {
                    "paper_id": r["source_paper"],
                    "title": r["paper_title"],
                    "year": r["paper_year"],
                },
            }
            cases.append(case)

        filter_msg = f" (filtered by paper_id={paper_id})" if paper_id else ""

        data = {
            "step_key": step_key,
            "num_cases": len(cases),
            "cases": cases,
        }

        return {
            "status": "ok",
            "data": data,
            "message": f"Found {len(cases)} case(s) for {step_key}{filter_msg}",
        }

    except Exception as e:
        return {
            "status": "error",
            "data": None,
            "message": f"Neo4j query error in get_cases_and_metrics: {type(e).__name__}: {e}",
        }
