from __future__ import annotations

from dotenv import load_dotenv
load_dotenv()

from pathlib import Path

from src.validation.graph_validator import (
    GraphValidator,
    get_env_variable,
    write_details_txt,
    write_summary_csv,
)

def main() -> None:
    print("Starting graph validation...")

    neo4j_uri = get_env_variable("NEO4J_URI")
    neo4j_user = get_env_variable("NEO4J_USERNAME")
    neo4j_password = get_env_variable("NEO4J_PASSWORD")
    neo4j_database = get_env_variable("NEO4J_DATABASE", "neo4j")

    output_dir = Path("logs") / "validation"
    summary_csv_path = output_dir / "graph_validation_summary.csv"
    details_txt_path = output_dir / "graph_validation_details.txt"

    validator = GraphValidator(
        uri=neo4j_uri,
        user=neo4j_user,
        password=neo4j_password,
        database=neo4j_database,
    )

    try:
        results = validator.run_all_checks()

        for result in results:
            print(f"[{result.status}] {result.check_name}: {result.count}")

        write_summary_csv(results, summary_csv_path)
        write_details_txt(results, details_txt_path)

        print(f"\nSummary written to: {summary_csv_path}")
        print(f"Details written to: {details_txt_path}")
        print("Graph validation completed.")

    finally:
        validator.close()


if __name__ == "__main__":
    main()