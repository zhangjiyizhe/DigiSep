from __future__ import annotations

import csv
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from neo4j import GraphDatabase, Driver


@dataclass
class ValidationResult:
    check_name: str
    status: str
    count: int
    details: list[dict[str, Any]]


class GraphValidator:
    def __init__(self, uri: str, user: str, password: str, database: str = "neo4j") -> None:
        self.uri = uri
        self.user = user
        self.password = password
        self.database = database
        self.driver: Driver = GraphDatabase.driver(self.uri, auth=(self.user, self.password))

    def close(self) -> None:
        self.driver.close()

    def _run_query(self, query: str, parameters: dict[str, Any] | None = None) -> list[dict[str, Any]]:
        with self.driver.session(database=self.database) as session:
            result = session.run(query, parameters or {})
            return [record.data() for record in result]

    def validate_total_nodes(self) -> ValidationResult:
        query = """
        MATCH (n)
        RETURN count(n) AS total_nodes
        """
        rows = self._run_query(query)
        total_nodes = int(rows[0]["total_nodes"]) if rows else 0
        return ValidationResult(
            check_name="total_nodes",
            status="INFO",
            count=total_nodes,
            details=rows,
        )

    def validate_total_relationships(self) -> ValidationResult:
        query = """
        MATCH ()-[r]->()
        RETURN count(r) AS total_relationships
        """
        rows = self._run_query(query)
        total_relationships = int(rows[0]["total_relationships"]) if rows else 0
        return ValidationResult(
            check_name="total_relationships",
            status="INFO",
            count=total_relationships,
            details=rows,
        )

    def validate_relationship_counts(self) -> ValidationResult:
        query = """
        MATCH ()-[r]->()
        RETURN type(r) AS relationship_type, count(r) AS relationship_count
        ORDER BY relationship_type
        """
        rows = self._run_query(query)
        return ValidationResult(
            check_name="relationship_counts",
            status="INFO",
            count=len(rows),
            details=rows,
        )

    def validate_orphan_nodes(self) -> ValidationResult:
        query = """
        MATCH (n)
        WHERE NOT (n)--()
        RETURN labels(n) AS labels, n.name AS name, n.cas_number AS cas_number, n.step_key AS step_key
        ORDER BY labels(n)[0], n.name
        """
        rows = self._run_query(query)
        status = "PASS" if len(rows) == 0 else "FAIL"
        return ValidationResult(
            check_name="orphan_nodes",
            status=status,
            count=len(rows),
            details=rows,
        )

    def validate_orphan_species(self) -> ValidationResult:
        query = """
        MATCH (sp:Species)
        WHERE NOT (sp)--()
        RETURN sp.name AS name, sp.cas_number AS cas_number
        ORDER BY sp.name
        """
        rows = self._run_query(query)
        status = "PASS" if len(rows) == 0 else "FAIL"
        return ValidationResult(
            check_name="orphan_species",
            status=status,
            count=len(rows),
            details=rows,
        )

    def validate_recycle_streams_missing_feeds(self) -> ValidationResult:
        query = """
        MATCH (ps:ProcessStep)-[:PRODUCES]->(s:Stream)
        WHERE s.stream_type = "recycle"
          AND NOT (s)-[:FEEDS]->(:ProcessStep)
        RETURN ps.step_key AS source_step, s.stream_key AS stream_key, s.description AS description
        ORDER BY s.stream_key
        """
        rows = self._run_query(query)
        status = "PASS" if len(rows) == 0 else "FAIL"
        return ValidationResult(
            check_name="recycle_streams_missing_feeds",
            status=status,
            count=len(rows),
            details=rows,
        )

    def validate_process_steps_missing_produces(self) -> ValidationResult:
        query = """
        MATCH (ps:ProcessStep)
        WHERE NOT (ps)-[:PRODUCES]->(:Stream)
        RETURN ps.step_key AS step_key, ps.description AS description
        ORDER BY ps.step_key
        """
        rows = self._run_query(query)

        critical_steps: list[dict[str, Any]] = []
        warning_steps: list[dict[str, Any]] = []

        for row in rows:
            step_key = (row.get("step_key") or "").lower()

            if "thermal_decomposition" in step_key:
                critical_steps.append(row)
            else:
                warning_steps.append(row)

        if len(critical_steps) == 0 and len(warning_steps) == 0:
            status = "PASS"
        elif len(critical_steps) > 0:
            status = "FAIL"
        else:
            status = "WARN"

        details = {
            "critical_steps": critical_steps,
            "warning_steps": warning_steps,
        }

        return ValidationResult(
            check_name="process_steps_missing_produces",
            status=status,
            count=len(rows),
            details=[details],
        )

    def validate_terminal_streams(self) -> ValidationResult:
        query = """
        MATCH (ps:ProcessStep)-[:PRODUCES]->(s:Stream)
        WHERE NOT (s)-[:FEEDS]->(:ProcessStep)
        RETURN ps.step_key AS source_step,
               s.stream_key AS stream_key,
               s.stream_type AS stream_type,
               s.description AS description
        ORDER BY s.stream_key
        """
        rows = self._run_query(query)
        return ValidationResult(
            check_name="terminal_streams",
            status="INFO",
            count=len(rows),
            details=rows,
        )

    def validate_has_component_count(self) -> ValidationResult:
        query = """
        MATCH ()-[r:HAS_COMPONENT]->()
        RETURN count(r) AS has_component_count
        """
        rows = self._run_query(query)
        has_component_count = int(rows[0]["has_component_count"]) if rows else 0
        return ValidationResult(
            check_name="has_component_count",
            status="INFO",
            count=has_component_count,
            details=rows,
        )

    def run_all_checks(self) -> list[ValidationResult]:
        return [
            self.validate_total_nodes(),
            self.validate_total_relationships(),
            self.validate_relationship_counts(),
            self.validate_orphan_nodes(),
            self.validate_orphan_species(),
            self.validate_recycle_streams_missing_feeds(),
            self.validate_process_steps_missing_produces(),
            self.validate_terminal_streams(),
            self.validate_has_component_count(),
        ]


def write_summary_csv(results: list[ValidationResult], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(
            csvfile,
            fieldnames=["check_name", "status", "count"],
        )
        writer.writeheader()
        for result in results:
            writer.writerow(
                {
                    "check_name": result.check_name,
                    "status": result.status,
                    "count": result.count,
                }
            )


def write_details_txt(results: list[ValidationResult], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        for result in results:
            f.write(f"=== {result.check_name} ===\n")
            f.write(f"Status: {result.status}\n")
            f.write(f"Count: {result.count}\n")
            f.write("Details:\n")
            if result.details:
                for row in result.details:
                    f.write(f"{row}\n")
            else:
                f.write("None\n")
            f.write("\n")


def get_env_variable(name: str, default: str | None = None) -> str:
    value = os.getenv(name, default)
    if value is None or value == "":
        raise ValueError(f"Missing required environment variable: {name}")
    return value