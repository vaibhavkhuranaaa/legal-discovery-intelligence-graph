# Roadmap

Milestones are implemented strictly in order; each is verified (tests, lint, and a real run)
and approved before the next begins. Status legend: ✅ done · 🔄 in progress · ⬜ not started.

## Milestone 0 — Foundation ✅ (this milestone)

Repository scaffold: uv + Hatchling src layout, Ruff/pytest baseline, Pydantic settings and
domain models, documentation set, standards imported, minimal Streamlit health-check app.
**No cloud services, data, or product features.**

Exit criteria: `uv sync`, `uv run pytest`, `uv run ruff check .` all pass; health-check app
serves locally.

## Milestone 1 — Synthetic corpus & gold labels ✅

Implemented `scripts/bootstrap_data.py`: seedable generator producing the fictional
"Project Falcon" procurement-fraud corpus (111 documents at seed 42 — emails, contracts, memos,
invoices, meeting notes) into `data/raw/` plus gold entity/event/retrieval labels into
`data/labels/` (see `DATA_AND_EVALUATION.md` and ADR-0008), including **32 categorized gold
queries** (entity, relationship, event, document-evidence, financial, plus 4 negative queries
with empty relevant sets for refusal evaluation). Ingestion module chunks into
`data/processed/` with failure quarantine to `data/failed/`.

Exit criteria met: byte-identical regeneration for the same seed (regression-tested);
gold-label completeness regression test (every canonical name/alias occurrence in every body is
covered by an exact-offset mention of the same entity); 20 tests passing.

## Milestone 2 — Entity & event extraction ⬜

`extraction/`: spaCy NER + deterministic regex extractors (money, dates, invoice IDs), entity
resolution to canonical IDs, event extraction. First evaluation run: extraction
precision/recall/F1 against gold labels.

Exit criteria: extraction metrics reproducible via a single `uv run` command; documented in
`DATA_AND_EVALUATION.md`.

## Milestone 3 — Semantic retrieval (pgvector) ⬜

Provision Supabase; apply the `DATA_MODEL.md` schema; `retrieval/` embeds chunks
(sentence-transformers) and implements vector search; `scripts/index_pgvector.py` loads the
corpus. Retrieval metrics (precision/recall@k, hit rate) against gold queries.

Exit criteria: cloud round-trip verified from local app; retrieval metrics recorded.

## Milestone 4 — Relationship graph (Neo4j AuraDB) ⬜

Provision AuraDB; `graph/` implements constraints, loading, and investigation Cypher queries;
`scripts/load_neo4j.py` populates the graph with shared IDs. LangChain orchestration combining
vector retrieval + graph expansion; measure graph contribution vs vector-only.

Exit criteria: graph queries verified against cloud instance; combined-retrieval evaluation
recorded.

## Milestone 5 — Investigation dashboard ⬜

Full Streamlit UI: question → cited evidence view, interactive Plotly entity graph, timeline
view, evaluation metrics page, degraded-mode handling per `architecture.md` failure boundaries.

Exit criteria: all four panels working locally against cloud backends; demo script drafted.

## Milestone 6 — Public deployment ⬜

Publish GitHub repo, export `requirements.txt` from `uv.lock`, deploy to Streamlit Community
Cloud, configure secrets, run the full `DEPLOYMENT.md` smoke-test checklist, finish
`DEMO_SCRIPT.md`, update `README.md` with the verified live URL and reproducible metrics.

Exit criteria: every smoke-test item checked against the live URL; README claims match reality.
