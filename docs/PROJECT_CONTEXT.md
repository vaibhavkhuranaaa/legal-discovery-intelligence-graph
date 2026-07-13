# Project Context — Read This First In A New Session

Self-contained handoff for the **Legal Discovery Intelligence Graph**. Contains only verified
current state — no aspirations. Last verified: 2026-07-12 (Milestone 2 completion).

## What This Project Is

A Graph RAG eDiscovery investigation platform (portfolio project): synthetic discovery
documents → entity extraction (spaCy + regex) → pgvector semantic retrieval (Supabase) + Neo4j
AuraDB relationship graph → LangChain orchestration → Streamlit investigation dashboard with
cited evidence, entity graph, timeline, and evaluation metrics — intended for public deployment
on Streamlit Community Cloud at Milestone 6. Full design: `product.md`, `architecture.md`,
`DATA_MODEL.md`.

**Repository:** `github.com/vaibhavkhuranaaa/legal-discovery-intelligence-graph` (public).
CI (GitHub Actions): `uv sync --frozen`, `ruff check`, `pytest` on pushes/PRs to `main`.

## Current Status: Milestones 0–2 complete

**Milestone 0 — Foundation (done):** uv-managed Python 3.12 project (Hatchling, src layout),
Ruff/pytest baseline, `config.py` (settings singleton), `models.py` (shared-ID Pydantic
contracts), docs set + 7 imported standards, minimal Streamlit health-check app,
`requirements.txt` exported from `uv.lock` for Community Cloud.

**Milestone 1 — Synthetic corpus & gold labels (done):**

- `datagen/` package: the fictional "Project Falcon" procurement-fraud scenario
  (`scenario.py` — 21 planted evidence documents, 12 timeline events, 32 gold queries),
  seeded noise documents (`generator.py`), composer with exact mention-offset tracking
  (`composer.py`), and `bootstrap.py` orchestration (generate → write raw → ingest → resolve
  labels). Deterministic uuid5 IDs in `ids.py` (ADR-0008).
- `ingestion/` package: paragraph-packing chunker whose chunks are exact body slices with
  document offsets (`chunker.py`), and a pipeline with per-document failure quarantine to
  `data/failed/` (`pipeline.py`).
- `scripts/bootstrap_data.py` CLI. At default seed 42: 111 documents (63 emails, 21 invoices,
  17 memos, 9 meeting notes, 1 contract), 112 chunks, 149 entities, 583 gold mentions,
  12 events, 32 categorized retrieval queries (5 entity, 6 relationship, 7 event, 5 document,
  5 financial, 4 negative with empty relevant sets for refusal evaluation). Generator v2
  gold-labels informal name references and incidental locations.
- Gold label files: `data/labels/{entities.json, mentions.jsonl, events.jsonl,
  retrieval.jsonl}`; formats in `DATA_AND_EVALUATION.md`.

**Milestone 2 — Entity & event extraction + evaluation (done):**

- `extraction/`: regex lane (money/date/project), spaCy `en_core_web_sm` NER lane
  (person/org/location; model pinned as a wheel in the dev group), regex-wins merge,
  per-paragraph NER with location coalescing and identifier rejection, corpus-level majority
  type voting, rule-based entity resolution with deterministic IDs, and trigger-lexicon event
  extraction with a participants-required rule (ADR-0009).
- `evaluation/extraction_eval.py`: strict/relaxed one-to-one span matching, per-type + micro
  P/R/F1, event scoring on (document, date).
- `scripts/evaluate_extraction.py`: runs extraction over `data/raw/`, scores against
  `data/labels/`, writes `artifacts/extraction_metrics.json` + predicted mentions.
- **Measured (seed 42):** micro F1 0.889 strict / 0.903 relaxed; money/date/project 1.000;
  person F1 0.910; organization 0.684/0.767; location 0.789; events 1.000. Honest error
  profile and synthetic-data caveats in `DATA_AND_EVALUATION.md`.
- Integrity: extraction cannot import `datagen` or read gold labels (AST-enforced test);
  regression floors run in CI.

**Verification (run 2026-07-12):** `uv run pytest` — 32 passed (byte-identical same-seed
regeneration, mention offset integrity, gold-label completeness, retrieval-label chunk
resolution, query-set balance, failure quarantine, extraction determinism, gold-leakage ban,
metric regression floors, scoring-math unit checks); `uv run ruff check .` — clean;
`uv run python scripts/bootstrap_data.py` and `scripts/evaluate_extraction.py` — outputs above;
generated data and artifacts correctly gitignored.

**What does NOT exist yet (do not assume otherwise):**

- No cloud services: no Supabase project, no Neo4j AuraDB instance, no Community Cloud app,
  no live URL.
- No retrieval or graph code — those subpackages are empty.
- No retrieval metrics yet (Milestone 3); only extraction metrics exist.
- The Streamlit app is still the foundation health check; no product UI.

## How To Run

```bash
uv sync
uv run pytest                                    # 32 tests
uv run ruff check .
uv run python scripts/bootstrap_data.py          # generate corpus + labels (seed 42)
uv run python scripts/evaluate_extraction.py     # extraction P/R/F1 -> artifacts/
uv run streamlit run src/legal_discovery_graph/ui/streamlit_app.py
```

## Source Tree

```
src/legal_discovery_graph/
├── config.py        # settings singleton — only env-var boundary
├── models.py        # shared Pydantic contracts (IDs shared across pgvector & Neo4j)
├── ids.py           # deterministic uuid5 minting (ADR-0008)
├── datagen/         # scenario, composer, noise generator, bootstrap orchestration
├── ingestion/       # chunker (exact body slices + offsets), pipeline w/ quarantine
├── extraction/      # regex + NER lanes, resolution, events (no gold access — enforced)
├── evaluation/      # strict/relaxed span matching, P/R/F1 scoring
├── retrieval/ graph/    # empty — later milestones
└── ui/streamlit_app.py   # health-check app only
tests/               # 32 tests
scripts/             # bootstrap_data.py, evaluate_extraction.py (real); other 3 are stubs
data/                # generated, gitignored; regenerate via bootstrap_data.py
```

## Known Limitations

- Synthetic documents are short and clean; most fit in a single 900-char chunk (112 chunks for
  111 docs). Chunk granularity may be revisited at the retrieval milestone if needed.
- Extraction metrics on synthetic text will look better than on real-world documents —
  disclosed in `DATA_AND_EVALUATION.md` (ADR-0005).

## Next Phase

**Milestone 3 — Semantic retrieval (pgvector)** (`roadmap.md`): provision Supabase (requires
user account action), apply the `DATA_MODEL.md` schema, embed chunks with sentence-transformers,
implement vector search, index via `scripts/index_pgvector.py`, and score retrieval
(precision/recall@k, hit rate, refusal behavior on the 4 negative queries). Await approval
before starting.
