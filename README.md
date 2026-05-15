# MAS-DSP: A Multi-Agent System for Bioseparation Route Discovery

A knowledge-graph-grounded multi-agent system that autonomously discovers feasible
downstream-separation (DSP) routes for bio-derived chemicals and returns a tiered
feasibility report. Lactic acid (LA) is the first case study.

The system pairs a curated Neo4j knowledge graph (KG) of DSP unit operations,
streams, decision rules, performance metrics, and literature pathways with a
four-agent LangGraph pipeline:

- **Agent 1 — Input Parser** (LLM, Pydantic): natural-language query to structured
  `(feed_type, target_purity)` with ambiguity handling.
- **Agent 2 — Route Discovery** (LangGraph ReAct + Neo4j tools): traverses the KG
  DAG and returns every candidate route with literature-pathway verification baked
  in (no per-route LLM calls).
- **Agent 3 — Feasibility Screener** (deterministic Python rules): applies six
  active rules (R-01, R-02, R-05, R-06 by default; R-07–R-10 in the enhanced
  ablation variant) and tags each route Tier 1 / Tier 2 / Tier 3.
- **Agent 4 — Report Generator** (LLM): produces a natural-language tiered
  report. Implemented in `src/report_generator.py` but **not wired into the
  default pipeline** during the evaluation phase; the CLI prints a text summary
  via Agent 3 output instead. Reconnect by adding the node back into
  `src/pipeline.py` when full NL report generation is required.

```
User NL query
   |
   v
[Agent 1] Input Parser  ---> structured (feed_type, target_purity)
   |
   v
[Agent 2] Route Discovery  ---> N candidate routes + verification status
   |
   v
[Agent 3] Feasibility Screener  ---> Tier 1 / 2 / 3 + rule flags
   |
   v
[Agent 4] Report Generator (optional)  ---> NL tiered report
```

---

## Repository layout

```
.
├── README.md
├── LICENSE                              ← MIT
├── .env.example                         ← copy to .env, fill in your keys
├── .gitignore
├── requirements.txt
├── config.py                            ← LLM provider + Neo4j connection
│
├── src/                                 ← core pipeline code
│   ├── pipeline.py                      ← LangGraph StateGraph wiring
│   ├── state.py                         ← shared DSPState TypedDict
│   ├── input_parser.py                  ← Agent 1
│   ├── agent_core.py                    ← Agent 2 (ReAct + Neo4j tools)
│   ├── rule_engine.py                   ← Agent 3 (default rules)
│   ├── rule_engine_baseline.py          ← Agent 3 ablation A1
│   ├── rule_engine_enhanced.py          ← Agent 3 ablation A2
│   ├── rule_engine_no_rules.py          ← Agent 3 ablation A0
│   ├── feasibility_screener_node.py     ← Agent 3 LangGraph node wrapper
│   ├── report_generator.py              ← Agent 4 (not wired by default)
│   ├── llm_factory.py                   ← Anthropic / Groq provider switch
│   ├── run_graph_validator.py           ← optional KG consistency check CLI
│   ├── prompts/
│   │   └── agent_core_prompt.py         ← Agent 2 system prompt
│   ├── tools/                           ← Neo4j Cypher tools
│   │   ├── neo4j_connection.py          ← driver singleton
│   │   ├── get_feed_info.py             ← Tool 2 (registered)
│   │   ├── get_all_routes.py            ← Tool 1 (registered, includes verification)
│   │   ├── verification_shared.py       ← Pathway-match logic used by Tool 1
│   │   ├── get_step_details.py          ← Tool 3 (available, not registered)
│   │   ├── get_decision_rules.py        ← Tool 4 (available, not registered)
│   │   ├── get_cases_and_metrics.py     ← Tool 5 (available, not registered)
│   │   ├── get_stream_composition.py    ← Tool 6 (available, not registered)
│   │   └── get_chemical_species.py      ← Tool 7 (available, not registered)
│   └── validation/
│       └── graph_validator.py           ← KG checks implementation
│
├── scripts/                             ← CLI entry points
│   ├── main.py                          ← single-query runner
│   ├── run_experiments.py               ← batch ablation experiments
│   └── neo4j_import.py                  ← optional: bulk-load .cypher files
│
├── tests/                               ← smoke tests / KG helpers
│   ├── test_get_feed_info.py            ← Tool 2 unit test
│   ├── test_get_all_routes.py           ← Tool 1 unit test
│   └── list_feed_and_targets.py         ← prints all FeedTypes / TargetSpecs
│
└── neo4j/
    └── neo4j-2026-04-19T23-09-00.dump   ← Neo4j 5.x database dump (~450 KB)
```

**Tools 3–7** are fully implemented but not registered with the Agent 2 ReAct
loop by default, to keep prompt-token cost bounded. They are available for
direct use, KG exploration, or future agent extensions.

---

## Setup

### 1. Prerequisites

- Python 3.11+
- Neo4j 5.x (Desktop or Community Server)
- An LLM API key (Anthropic recommended; Groq is the cheaper fallback)

### 2. Clone and install

```bash
git clone <your-repo-url>
cd <repo>
python -m venv venv
# Windows
venv\Scripts\activate
# macOS / Linux
source venv/bin/activate
pip install -r requirements.txt
```

### 3. Configure environment

```bash
cp .env.example .env
```

Edit `.env`:

```
ANTHROPIC_API_KEY=sk-ant-...
GROQ_API_KEY=gsk_...
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your_password
```

Then open `config.py` and pick a provider:

```python
LLM_PROVIDER = "anthropic"   # or "groq"
ANTHROPIC_MODEL = "claude-sonnet-4-6"
GROQ_MODEL = "llama-3.3-70b-versatile"
```

### 4. Restore the Neo4j database

The included dump (`neo4j/neo4j-2026-04-19T23-09-00.dump`) contains the full
curated KG: ten extracted papers, 74 ProcessStep nodes, 31 verified literature
pathways, and 284 DecisionRule nodes.

Stop your Neo4j DBMS first, then:

```bash
neo4j-admin database load neo4j --from-path=./neo4j --overwrite-destination=true
```

If you use Neo4j Desktop, open the DBMS settings, click **Backup / Restore** and
select the `.dump` file.

Start the DBMS and verify with a smoke test:

```cypher
MATCH (f:FeedType) RETURN f.name, f.feed_type LIMIT 10;
MATCH (p:Pathway) RETURN count(p);   // expect 31
```

---

## Usage

### Single query (Agent 1 → 2 → 3, text summary)

From the project root:

```bash
python scripts/main.py "I have a lactic acid fermentation broth. I want polymer-grade lactic acid."
```

Output: a `report_<timestamp>.txt` summary in `outputs/` with per-route tier and
rule flags. Agent 2's raw JSON is cached under `outputs/cache/` so re-runs of
the same query skip the LLM call. Resume Agent 3 from an existing Agent 2 cache:

```bash
python scripts/main.py --resume outputs/cache/agent2_T1-01.json "<same query>"
```

### Experiment batch

From the project root:

```bash
python scripts/run_experiments.py --run-t1 --rule-engine baseline
python scripts/run_experiments.py --run-t1 --rule-engine enhanced
python scripts/run_experiments.py --run-t1 --rule-engine no_rules

# other suites
python scripts/run_experiments.py --run-t2 --rule-engine baseline
python scripts/run_experiments.py --run-t3 --rule-engine baseline
python scripts/run_experiments.py --run-t4 --rule-engine baseline

# resume / progress
python scripts/run_experiments.py --rerun T1-03 T1-07 --rule-engine baseline
python scripts/run_experiments.py --progress --rule-engine baseline
```

Results are written to `experiments/<series>_results_<rule_engine>.json`.
Agent 2's cache is shared across rule-engine conditions — only Agent 3 reruns.

### Ablation variants

| Variant | File | Rules |
|---------|------|-------|
| A0 (no rules) | `src/rule_engine_no_rules.py` | none — every route tagged Tier 2 |
| A1 (baseline) | `src/rule_engine_baseline.py` | R-01, R-02, R-05, R-06 (same as default) |
| Default | `src/rule_engine.py` | R-01, R-02, R-05, R-06 |
| A2 (enhanced) | `src/rule_engine_enhanced.py` | R-01 through R-10 |

R-03 (DecisionRule lookup) is implemented but disabled by default for latency
reasons; re-enable in `rule_engine.py` for a production run. R-04 is deprecated.

---

## Knowledge graph schema

Brief reference:

| Layer | Node | Count | Key |
|-------|------|-------|-----|
| 1 SUBSTANCE | ChemicalSpecies | (varies) | cas_number |
| 2 PROCESS | FeedType | 12 | name |
| 2 PROCESS | TargetSpec | 4 | spec_id |
| 2 PROCESS | ProcessStep | 74 | step_key |
| 2 PROCESS | Stream | ~136 | stream_key |
| 3 KNOWLEDGE | DecisionRule | ~284 | rule_key |
| 4 CASE | Case | 116 | case_id |
| 4 CASE | PerformanceMetric | 146 | metric_id |
| 4 CASE | Pathway | 31 | pathway_id |
| 5 EVIDENCE | Paper | 10 | doi |

Key relationships: `FIRST_STEP`, `HAS_NEXT_STEP`, `HAS_PRODUCT`, `HAS_PURITY`,
`GOVERNED_BY`, `HAS_CASE`, `ACHIEVES`, `INCLUDES_STEP`, `REPORTED_IN`.

The DAG is rooted at `FeedType` nodes; route discovery walks `FIRST_STEP` then
`HAS_NEXT_STEP*` until a `Stream(:Product)` connects to a `TargetSpec` via
`HAS_PURITY`.

---

## Scope

**In scope.** Technical route selection, separation performance, physicochemical
constraints, design rules, species properties, multi-paper evidence comparison.

**Out of scope.** Economics (TAC, MSP, IRR, CAPEX, OPEX), equipment sizing,
process-simulation integration.

---

## Status & known limitations

- The default Agent 2 setup registers only two Neo4j tools (`get_feed_info`,
  `get_all_routes`); the other five (Tools 3–7) exist in `src/tools/` for
  direct use and future extension but are not attached to the ReAct agent.
  Verification runs inside `get_all_routes` (pure Python) to keep token cost
  bounded; see `src/tools/verification_shared.py`.
- For very large route sets (`fermentation_broth` currently has more than a
  thousand candidate paths) you may need to add `LIMIT 100` to `_ROUTE_CYPHER`
  in `src/tools/get_all_routes.py`, or switch from Groq to Anthropic so the
  larger context window absorbs the volume.
- `synthetic_lactic_acid_solution` is recognised by Agent 1 but has no mapped
  routes in the KG — the pipeline returns an informative zero-route message
  rather than a silent empty report.

---

## Citation

If you build on this work, please cite the accompanying dissertation (details
to be filled in upon publication) and reference this repository.

---

## License

MIT — see [`LICENSE`](LICENSE).
