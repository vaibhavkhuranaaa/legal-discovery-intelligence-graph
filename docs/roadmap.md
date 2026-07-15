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

## Milestone 2 — Entity & event extraction ✅

`extraction/`: two-lane extraction (deterministic regex for money/date/project + spaCy
`en_core_web_sm` NER for person/organization/location, regex wins on overlap), deterministic
entity resolution (short-form folding, majority type voting, uuid5 IDs), and trigger-lexicon
event extraction (ADR-0009). `evaluation/`: strict/relaxed one-to-one span matching with
per-type and micro P/R/F1. Gold-leakage ban enforced by test.

Exit criteria met: metrics reproducible via `uv run python scripts/evaluate_extraction.py`
(micro F1 0.889 strict / 0.903 relaxed, events 1.000 at seed 42) and documented with an honest
error profile in `DATA_AND_EVALUATION.md`; regression floors in CI; 32 tests passing.

## Milestone 3 — Semantic retrieval (pgvector) ✅

Supabase provisioned; `DATA_MODEL.md` schema applied (documents/chunks/entity_mentions +
HNSW cosine index). `retrieval/`: lazy sentence-transformers embedder (normalized MiniLM-L6-v2,
384-dim, asserted against the schema), `PgVectorStore` (atomic replace-on-index, cosine
search), `SemanticRetriever` (ADR-0010). `scripts/index_pgvector.py` embeds and loads the
corpus with DB-side count verification; `scripts/evaluate_retrieval.py` scores all 32 gold
queries and writes `artifacts/retrieval_metrics.json`.

Exit criteria met: cloud round-trip verified against Supabase (111 documents, 112 chunks
indexed and searched); metrics recorded at seed 42 — macro R@5 0.857 / hit@5 0.893, R@10 0.929
/ hit@10 0.964; relationship queries weakest (hit@5 0.500 — the measured baseline for the
Milestone 4 graph); negative-query top-1 scores overlap answerable ones, so refusal needs more
than a similarity threshold (`DATA_AND_EVALUATION.md`). 43 tests passing.

## Milestone 4 — Relationship graph (Neo4j AuraDB) ✅

AuraDB provisioned. `graph/`: `Neo4jGraphStore` driver boundary (idempotent uniqueness
constraints, wipe-and-reload MERGE batches, parameterized Cypher, three evidence-backed
expansion queries) and a pure payload builder deriving edges from extracted facts only —
`MENTIONED_IN {chunk_id}`, `SENT`/`RECEIVED` from email headers + custodians,
`EVIDENCED_BY`/`INVOLVES` from events (ADR-0011). `scripts/load_neo4j.py` loads AuraDB and
populates Supabase `entity_mentions` with shared IDs. `retrieval/hybrid.py`: deterministic
LangChain runnable pipeline (vector leg seeds graph expansion, constant-free rank
interleaving, explicit degraded mode when Neo4j is down). Evaluation scores vector-only vs
graph-expanded from the same pass.

Exit criteria met: cloud round-trip verified (186 nodes / 536 relationships in AuraDB, 566
`entity_mentions` rows in Supabase, counts confirmed from both databases); measured at seed
42 — relationship hit@5 0.500 → 0.833, overall hit@5 0.893 → 0.964, R@5 0.857 → 0.929, hit@1
unchanged, no category degraded at any k (`DATA_AND_EVALUATION.md`). 63 tests passing.

## Milestone 5 — Investigation dashboard ✅

Full Streamlit UI (`ui/`): investigation tab (question → ranked, cited evidence with
vector/graph source badges, cosine scores, and per-chunk graph evidence trails), interactive
Plotly entity graph built only from evidence-backed relations, extracted-event timeline
(Plotly + cited table view, events read from Neo4j via `Neo4jGraphStore.timeline_events()`),
and an evaluation panel rendering `artifacts/*.json` with vector-only vs graph-expanded kept
separate. Layered as `backend.py` (the UI's only data boundary) → pure `presenters.py` /
`figures.py` → `streamlit_app.py` (ADR-0012). Degraded modes are explicit per
`architecture.md`: vector failure → error state, graph failure → vector evidence retained with
a visible notice, missing artifacts → reproduction-command empty state. No LLM answer
generation.

Exit criteria met: all four panels verified locally against live Supabase + AuraDB (browser
session run 2026-07-13); no-credential and degraded states covered by headless `AppTest` tests;
demo script outline drafted in `DEMO_SCRIPT.md` (finalized at Milestone 6). 88 tests passing.

## Milestone 6 — Public deployment ✅

Published from `main` to Streamlit Community Cloud (Python 3.12), with Supabase and AuraDB
credentials held only in Streamlit Secrets. The live app is
`https://legal-discovery-intelligence-graph-ma2dfvnresf84ytk4nzelm.streamlit.app/`.

Exit criteria met: live startup reports both backends configured; a hybrid retrieval returned
cited evidence; the entity graph, timeline, and evaluation tabs rendered successfully. The
initial embedding-model warm-up may take longer than subsequent searches.

Exit criteria: every smoke-test item checked against the live URL; README claims match reality.

## Milestone 7 — Flask product web UI ✅ (local; deployment pending)

Replaced the presentation layer with a designed Flask app (`webapp/`, ADR-0013): server-rendered
Jinja pages (Investigate, Entity graph, Timeline, Evaluation) over the unchanged
`ui/backend.py` → `presenters.py`/`figures.py` core, a hand-written CSS design system
(paper/navy/brass, serif display type, status pills, evidence cards, stat tiles), stateless
shareable search URLs, plotly.js served from the installed package (no CDN), and a
CVD-validated vector-vs-hybrid comparison chart. Only new dependency: `flask`. The Streamlit
app remains deployed and untouched until the Flask app ships publicly.

Exit criteria met: all four pages verified locally against live Supabase + AuraDB (2026-07-15);
degraded/no-credential states covered by 22 Flask test-client tests; 110 tests passing; ruff
clean.

## Milestone 8 — Flask public deployment ✅

Deployed to Render free tier via committed blueprint (`render.yaml`): gunicorn 1 worker /
4 threads, secrets in Render env vars, health check on `/`. The first deploy OOM-killed the
worker (torch > 512 MB), fixed by the ONNX embedding backend (ADR-0015) — same MiniLM vectors
(parity test cosine > 0.9999; live retrieval evaluation byte-identical), worker RSS 362 MB.
Live at `https://legal-discovery-intelligence-graph.onrender.com`, smoke-test checklist passed
2026-07-15; README links updated. The Streamlit Community Cloud app remains up as the legacy
dashboard. 113 tests passing.

## Milestone 9 — Richer corpus & designed views ✅

4x corpus with new planted evidence (ADR-0016): 450 documents, 25 timeline events, 3 new cast
members, queries fixed at 32; bootstrap stale-output bug found and fixed; all metrics
re-measured against live backends and re-documented honestly (hybrid R@10 0.964 / hit@10 1.000,
relationship hit@5 0.500 → 0.833; measured k=5 entity/financial dip reported). Product UI
(ADR-0017): interactive cytoscape.js entity graph with click-through provenance, month-grouped
vertical timeline rail with entity chips and citations, and an evaluation page led by a
transparent total model score (mean of the four headline metrics — 0.963) with detail tables
collapsed. Verified locally against live Supabase + AuraDB and re-deployed to Render.
116 tests passing.

## Milestone 10 — eDiscovery readiness ✅

Client-safe citations (ADR-0018): investigator pages cite title · type · passage — internal
hash IDs never render. Calibrated evidence refusal (ADR-0019): 10 negative gold queries
(from 4), max-accuracy top-1 cosine threshold 0.5089 measured by `evaluate_retrieval.py`
(7/10 negatives refused, 2/28 false refusals), explicit "no supporting evidence" state with
override. Privilege/PII flags (ADR-0020): `review/flags.py` rules + gold
`privilege_pii.json` + `evaluate_flags.py` (P/R/F1 1.0 on clean synthetic text; one
gold-label error found and fixed). Real-file ingestion (ADR-0021): PDF/DOCX/EML readers,
`ingest_files.py` with SHA-256 dedup, Bates numbers, chain-of-custody manifest. Search audit
trail (ADR-0022): append-only `audit_log` in PostgreSQL + `/audit` page. Corpus v3: 455
documents, 30 events, 38 queries; all metrics re-measured honestly — hybrid @10 now *loses*
to vector-only on the denser graph (hit@10 0.929 → 0.893; total model score 0.909), recorded
as a real interleaving finding, not tuned away. Free-tier limits documented in
`docs/SCALING.md` with a keep-alive workflow. 169 tests passing.

## Milestone 11 — Case-study site ✅

The live demo now explains and verifies itself (ADR-0023). Landing page `/` is a case brief:
the Project Falcon matter, corpus composition with synthetic disclosure, a six-step guided
tour of prefilled gold-query searches (semantic evidence → graph expansion → privilege badge →
PII badge → calibrated refusal; each step's behavior verified live), a full label glossary,
a "how to verify" section, and the complete story collapsed as a spoiler. Investigate moved
to `/investigate`. New `/document/<id>` page renders any stored source document (metadata,
privilege/PII flags, all passages in order); every citation on evidence cards, graph trails,
and the timeline links to it — the verification path for every passage shown. Glossary
include rendered collapsed above results and expanded on the case page; tooltips on badges
and scores. Display layer only: no retrieval, datagen, or metric changes. 176 tests passing.
