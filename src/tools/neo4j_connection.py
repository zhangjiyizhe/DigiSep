"""
Neo4j connection singleton.

All tool functions share this single connection instance.
"""

from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable, AuthError

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
from config import NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD


class Neo4jConnection:
    """
    Singleton Neo4j connection wrapper.

    Usage:
        neo4j_conn = Neo4jConnection(uri, user, password)
        results = neo4j_conn.query("MATCH (n:FeedType) RETURN n.name", {})
        neo4j_conn.close()
    """

    def __init__(self, uri: str, user: str, password: str):
        self._driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self):
        """Close the Neo4j driver connection."""
        self._driver.close()

    def query(self, cypher: str, params: dict | None = None) -> list[dict]:
        """
        Execute a parameterized Cypher query and return results as a list of dicts.

        Args:
            cypher: Parameterized Cypher string (use $param for variables).
            params: Dict of parameter values. All user inputs MUST go through
                    params — never use string interpolation (security requirement).

        Returns:
            List of dicts, one per result record.

        Raises:
            Exception on Neo4j connection or query errors.
        """
        with self._driver.session() as session:
            result = session.run(cypher, params or {})
            return [record.data() for record in result]

    def health_check(self) -> bool:
        """
        Verify Neo4j connectivity by running a trivial query.

        Returns:
            True if connection is healthy, False otherwise.
        """
        try:
            result = self.query("RETURN 1 AS ok")
            return len(result) == 1 and result[0].get("ok") == 1
        except (ServiceUnavailable, AuthError, Exception) as e:
            print(f"[Neo4j Health Check FAILED] {type(e).__name__}: {e}")
            return False


# --- Singleton instance (initialized once at startup) ---
neo4j_conn = Neo4jConnection(NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD)
