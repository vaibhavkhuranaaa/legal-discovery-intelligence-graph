# Project Context — Read This First In A New Session

Self-contained handoff for the **Legal Discovery Intelligence Graph**. Contains only verified
current state — no aspirations. Last verified: 2026-07-12 (Milestone 1 completion).

## What This Project Is

A Graph RAG eDiscovery investigation platform (portfolio project): synthetic discovery
documents → entity extraction (spaCy + regex) → pgvector semantic retrieval (Supabase) + Neo4j
AuraDB relationship graph → LangChain orchestration → Streamlit investigation dashboard with
cited evidence, entity graph, timeline, and evaluation metrics — intended for public deployment
on Streamlit Community Cloud at Milestone 6. Full design: `product.md`, `architecture.md`,
`DATA_MODEL.md`.

**Repository:** `github.com/vaibhavkhuranaaa/legal-discovery-intelligence-graph` (public).
CI (GitHub Actions): `uv sync --frozen`, `ruff check`, `pytest` on pushes/PRs to `main`.

## Current Status: Milestones 0–1 complete

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
  17 memos, 9 meeting notes, 1 contract), 112 chunks, 147 entities, 573 gold mentions,
  12 events, 32 categorized retrieval queries (5 entity, 6 relationship, 7 event, 5 document,
  5 financial, 4 negative with empty relevant sets for refusal evaluation).
- Gold label files: `data/labels/{entities.json, mentions.jsonl, events.jsonl,
  retrieval.jsonl}`; formats in `DATA_AND_EVALUATION.md`.

**Verification (run 2026-07-12):** `uv run pytest` — 20 passed (incl. byte-identical
same-seed regeneration, mention offset integrity, gold-label completeness — every canonical
name/alias occurrence in every body covered by an exact-offset mention of the same entity —
retrieval-label chunk resolution, query-set balance, failure quarantine); `uv run ruff check .`
— clean; `uv run python scripts/bootstrap_data.py` — output above, generated data correctly
gitignored.

**What does NOT exist yet (do not assume otherwise):**

- No cloud services: no Supabase project, no Neo4j AuraDB instance, no Community Cloud app,
  no live URL.
- No extraction, retrieval, graph, or evaluation code — those subpackages are empty.
- No quality metrics of any kind (extraction/retrieval scoring starts at Milestone 2).
- The Streamlit app is still the foundation health check; no product UI.

## How To Run

```bash
uv sync
uv run pytest                                    # 20 tests
uv run ruff check .
uv run python scripts/bootstrap_data.py          # generate corpus + labels (seed 42)
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
├── extraction/ retrieval/ graph/ evaluation/   # empty — later milestones
└── ui/streamlit_app.py   # health-check app only
tests/               # 20 tests
scripts/             # bootstrap_data.py (real); other 3 are stubs
data/                # generated, gitignored; regenerate via bootstrap_data.py
```

## Known Limitations

- Synthetic documents are short and clean; most fit in a single 900-char chunk (112 chunks for
  111 docs). Chunk granularity may be revisited at the retrieval milestone if needed.
- Extraction metrics on synthetic text will look better than on real-world documents —
  disclosed in `DATA_AND_EVALUATION.md` (ADR-0005).

## Next Phase

**Milestone 2 — Entity & event extraction** (`roadmap.md`): spaCy NER + deterministic regex
extractors (money, dates, invoice IDs), entity resolution to canonical IDs, event extraction,
and the first precision/recall/F1 evaluation against the gold labels. Await approval before
starting.
