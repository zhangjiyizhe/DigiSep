import os
from dotenv import load_dotenv

load_dotenv()

# ── LLM provider ───────────────────────────────────────────────
# Change this line to switch provider: "anthropic" | "groq"
LLM_PROVIDER = "groq"

# ── Anthropic config ───────────────────────────────────────────
ANTHROPIC_MODEL = "claude-sonnet-4-6"

# ── Groq config ────────────────────────────────────────────────
GROQ_MODEL = "llama-3.3-70b-versatile"

# ── Shared parameters ──────────────────────────────────────────
RECURSION_LIMIT = 20

# Max output tokens — set per provider:
#   Anthropic claude-sonnet-4-6 : up to 64,000
#   Groq llama-3.3-70b-versatile: up to 8,192
MAX_OUTPUT_TOKENS = 8192

# ── Neo4j connection ───────────────────────────────────────────
# Reads from .env file. Key names must match exactly.
NEO4J_URI      = os.getenv("NEO4J_URI",      "bolt://localhost:7687")
NEO4J_USERNAME = os.getenv("NEO4J_USERNAME", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")
