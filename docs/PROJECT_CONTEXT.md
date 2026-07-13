# Project Context — Read This First In A New Session

Self-contained handoff for the **Legal Discovery Intelligence Graph**. Contains only verified
current state — no aspirations. Last verified: 2026-07-12 (foundation milestone completion).

## What This Project Is

A Graph RAG eDiscovery investigation platform (portfolio project): synthetic discovery
documents → entity extraction (spaCy + regex) → pgvector semantic retrieval (Supabase) + Neo4j
AuraDB relationship graph → LangChain orchestration → Streamlit investigation dashboard with
cited evidence, entity graph, timeline, and evaluation metrics — to be deployed publicly on
Streamlit Community Cloud. Full design: `product.md`, `architecture.md`, `DATA_MODEL.md`.

## Current Status: Milestone 0 (Foundation) complete — nothing else

**What exists and is verified:**

- uv-managed Python 3.12 project (Hatchling, src layout), `pyproject.toml` + `uv.lock` source
  of truth; `requirements.txt` generated via `uv export` for Streamlit Community Cloud.
- `src/legal_discovery_graph/`: `config.py` (Pydantic Settings singleton via `get_settings()`),
  `models.py` (Document/Chunk/Entity/EntityMention/Event contracts with shared UUIDs), empty
  subsystem packages (`ingestion`, `extraction`, `retrieval`, `graph`, `evaluation`), and a
  minimal Streamlit health-check app (`ui/streamlit_app.py`).
- `tests/test_package.py`: 6 foundation tests.
- `scripts/`: four stubs (`bootstrap_data.py`, `index_pgvector.py`, `load_neo4j.py`,
  `verify_deployment.py`) that print not-implemented and exit 1.
- Documentation set (this file, product, architecture, roadmap, decisions ADR-0001…0007,
  DATA_MODEL, DATA_AND_EVALUATION, DEPLOYMENT, DEMO_SCRIPT placeholder) and
  `docs/standards/` (7 imported standards). `CLAUDE.md`/`AGENTS.md` operating manuals.

**Verification results (run 2026-07-12):**

- `uv sync` — succeeded (156 packages resolved/installed).
- `uv run pytest` — 6 passed.
- `uv run ruff check .` — all checks passed.
- `uv run streamlit run src/legal_discovery_graph/ui/streamlit_app.py` — served locally
  (verified via HTTP against the local server), renders "Legal Discovery Intelligence Graph —
  Foundation Ready".

**What does NOT exist yet (do not assume otherwise):**

- No cloud services: no Supabase project, no Neo4j AuraDB instance, no Streamlit Community
  Cloud app, no live URL.
- No GitHub repository, no git history / commits.
- No data (raw/processed/labels are empty), no extraction, retrieval, graph, or evaluation
  code, no metrics of any kind.

## How To Run

```bash
uv sync
uv run pytest
uv run ruff check .
uv run streamlit run src/legal_discovery_graph/ui/streamlit_app.py
```

## Source Tree

```
src/legal_discovery_graph/
├── config.py        # settings singleton — only env-var boundary
├── models.py        # shared Pydantic contracts (IDs shared across pgvector & Neo4j)
├── ingestion/ extraction/ retrieval/ graph/ evaluation/   # empty — later milestones
└── ui/streamlit_app.py   # health-check app only
tests/               # 6 foundation tests
scripts/             # 4 not-implemented stubs
docs/                # product, architecture, data model, evaluation plan, deployment plan,
                     # roadmap, ADRs, demo placeholder, standards/
data/ artifacts/ logs/   # gitignored, .gitkeep only
```

## Known Limitations

- Scripts are stubs; the health-check app has no features.
- The dependency set is heavy (sentence-transformers → torch); acceptable locally, must be
  re-checked against Community Cloud's memory ceiling at deployment (ADR-0006/0007).
- No git repository initialized yet — Conventional Commit history starts at the next milestone.

## Next Phase

**Milestone 1 — Synthetic corpus & gold labels** (`roadmap.md`): implement
`scripts/bootstrap_data.py` (seedable fictional-investigation corpus + gold labels) and the
ingestion/chunking module, with deterministic-regeneration tests. Await approval before
starting.
