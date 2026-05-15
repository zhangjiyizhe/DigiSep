"""
neo4j_import.py

Uploads one or more .cypher files to your local Neo4j Desktop database.
Each statement is sanitized before execution to fix unescaped quote issues.

Folder convention for this project:
  project_root/
  ├── .env                        ← credentials live here
  └── scripts/
      └── neo4j_import.py         ← this script lives here

Usage (run from the project root):

  # Upload a single paper
  python scripts/neo4j_import.py --file path/to/P01_import.cypher

  # Upload ALL .cypher files in a folder (sorted by filename)
  python scripts/neo4j_import.py --dir path/to/import_folder/

Requirements:
  pip install neo4j python-dotenv
"""

import argparse
import os
import re
import glob
from pathlib import Path
from dotenv import load_dotenv
from neo4j import GraphDatabase

# ── Load .env from the project root ─────────────────────────────────────────
SCRIPT_DIR   = Path(__file__).parent          # scripts/
PROJECT_ROOT = SCRIPT_DIR.parent              # project root (holds .env)
ENV_PATH     = PROJECT_ROOT / ".env"

load_dotenv(dotenv_path=ENV_PATH)

NEO4J_URI      = os.getenv("NEO4J_URI",      "bolt://localhost:7687")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")


def sanitize_statement(stmt: str) -> str:
    """
    Fix unescaped double-quotes inside Cypher single-quoted string values.

    The problem: GPT sometimes generates property values like:
        basis: 'Maximum capacity at pH 5.0" Amberlite IRA-400'
    where a stray " inside a '-quoted string breaks Neo4j parsing.

    Fix: replace any " that appears inside a single-quoted string with
    a regular apostrophe-safe space or just remove it.
    """
    result = []
    i = 0
    inside_single_quote = False

    while i < len(stmt):
        ch = stmt[i]

        if ch == "'" and (i == 0 or stmt[i-1] != '\\'):
            inside_single_quote = not inside_single_quote
            result.append(ch)

        elif ch == '"' and inside_single_quote:
            # Replace stray double-quote inside a single-quoted string with escaped version
            result.append('\\"')

        else:
            result.append(ch)

        i += 1

    return "".join(result)


def parse_statements(cypher_text: str) -> list[str]:
    """
    Split a .cypher file into individual statements by semicolons,
    but ONLY split on semicolons that are outside of quoted strings.

    This avoids breaking statements that contain semicolons inside
    property values like:  species_involved: 'lactic acid; water'
    """
    statements = []
    current = []
    inside_single_quote = False
    inside_double_quote = False
    i = 0

    while i < len(cypher_text):
        ch = cypher_text[i]

        # Track single-quote strings (skip escaped quotes)
        if ch == "'" and not inside_double_quote and (i == 0 or cypher_text[i-1] != '\\'):
            inside_single_quote = not inside_single_quote
            current.append(ch)

        # Track double-quote strings (skip escaped quotes)
        elif ch == '"' and not inside_single_quote and (i == 0 or cypher_text[i-1] != '\\'):
            inside_double_quote = not inside_double_quote
            current.append(ch)

        # Semicolon outside any quotes = statement boundary
        elif ch == ';' and not inside_single_quote and not inside_double_quote:
            raw = "".join(current)
            # Filter out comment-only lines and blank lines
            lines = [
                line for line in raw.splitlines()
                if line.strip() and not line.strip().startswith("//")
            ]
            cleaned = "\n".join(lines).strip()
            if cleaned:
                statements.append(cleaned)
            current = []

        else:
            current.append(ch)

        i += 1

    # Handle any remaining text after the last semicolon
    raw = "".join(current)
    lines = [
        line for line in raw.splitlines()
        if line.strip() and not line.strip().startswith("//")
    ]
    cleaned = "\n".join(lines).strip()
    if cleaned:
        statements.append(cleaned)

    return statements


def run_cypher_file(driver, filepath: str):
    """Run all statements in a single .cypher file."""
    print(f"\n{'='*60}")
    print(f"Importing: {filepath}")
    print(f"{'='*60}")

    with open(filepath, "r", encoding="utf-8") as f:
        cypher_text = f.read()

    statements = parse_statements(cypher_text)
    print(f"Found {len(statements)} statements to execute.\n")

    success = 0
    errors  = 0

    with driver.session() as session:
        for i, stmt in enumerate(statements, 1):
            sanitized = sanitize_statement(stmt)
            try:
                result  = session.run(sanitized)
                summary = result.consume()
                c = summary.counters
                print(
                    f"  [{i:03d}] ✅  "
                    f"nodes_created={c.nodes_created}  "
                    f"rels_created={c.relationships_created}  "
                    f"props_set={c.properties_set}"
                )
                success += 1
            except Exception as e:
                print(f"  [{i:03d}] ❌  ERROR: {e}")
                print(f"         Statement preview: {sanitized[:120]}...")
                errors += 1

    print(f"\nDone: {success} succeeded, {errors} failed.")
    return success, errors


def main():
    parser = argparse.ArgumentParser(description="Upload .cypher files to Neo4j")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--file", help="Single .cypher file, e.g. ../import/P01_import.cypher")
    group.add_argument("--dir",  help="Folder of .cypher files, e.g. ../import/")
    args = parser.parse_args()

    # Collect files
    if args.file:
        files = [args.file]
    else:
        files = sorted(glob.glob(os.path.join(args.dir, "*.cypher")))
        if not files:
            print(f"No .cypher files found in: {args.dir}")
            return

    print(f"Loading .env from: {ENV_PATH}")
    print(f"Connecting to Neo4j at {NEO4J_URI} as '{NEO4J_USERNAME}' ...")

    try:
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USERNAME, NEO4J_PASSWORD))
        driver.verify_connectivity()
        print("✅ Connected successfully.\n")
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        print(f"\nCheck your .env file at: {ENV_PATH}")
        print("Make sure NEO4J_URI, NEO4J_USERNAME, NEO4J_PASSWORD are correct.")
        print("Also make sure your Neo4j Desktop database is running (green dot).")
        return

    total_success = 0
    total_errors  = 0

    for filepath in files:
        s, e = run_cypher_file(driver, filepath)
        total_success += s
        total_errors  += e

    driver.close()

    print(f"\n{'='*60}")
    print(f"All files done.")
    print(f"Total: {total_success} succeeded, {total_errors} failed.")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()