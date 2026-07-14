# Project Context — Read This First In A New Session

Self-contained handoff for the **Legal Discovery Intelligence Graph**. Contains only verified
current state — no aspirations. Last verified: 2026-07-14 (Milestone 6 completion).

## What This Project Is

A Graph RAG eDiscovery investigation platform (portfolio project): synthetic discovery
documents → entity extraction (spaCy + regex) → pgvector semantic retrieval (Supabase) + Neo4j
AuraDB relationship graph → LangChain orchestration → Streamlit investigation dashboard with
cited evidence, entity graph, timeline, and evaluation metrics — intended for public deployment
on Streamlit Community Cloud at Milestone 6. Full design: `product.md`, `architecture.md`,
`DATA_MODEL.md`.

**Repository:** `github.com/vaibhavkhuranaaa/legal-discovery-intelligence-graph` (public).
CI (GitHub Actions): `uv sync --frozen`, `ruff check`, `pytest` on pushes/PRs to `main`.

## Current Status: Milestones 0–6 complete

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

**Milestone 3 — pgvector semantic retrieval (done):**

- Supabase project provisioned by the user; `DATABASE_URL` in `.env` (pooler, port 6543).
  pgvector 0.8.2 extension enabled; `DATA_MODEL.md` schema applied: `documents`, `chunks`,
  `entity_mentions` (created, empty until Milestone 4) + HNSW `vector_cosine_ops` index.
- `retrieval/`: `SentenceTransformerEmbedder` (lazy-loaded `all-MiniLM-L6-v2`, normalized,
  384-dim asserted against schema), `PgVectorStore` (atomic replace-on-index, embeddings bound
  as pgvector text literals + server-side CAST, cosine search returning scored
  `RetrievedChunk`s), `SemanticRetriever` composing both (ADR-0010).
- `scripts/index_pgvector.py` embeds `data/processed/chunks.jsonl` and loads the corpus with
  DB-side count verification; `scripts/evaluate_retrieval.py` runs all 32 gold queries against
  the live store → `artifacts/retrieval_metrics.json` + `retrieval_results.jsonl`;
  `evaluation/retrieval_eval.py` computes macro P/R/hit@{1,3,5,10}, overall and per category.
- **Measured (seed 42, vector-only):** overall R@5 0.857 / hit@5 0.893, R@10 0.929 / hit@10
  0.964; event/financial/document near-perfect by k=5; relationship weakest (hit@5 0.500) —
  the recorded baseline Milestone 4's graph expansion must beat. Negative-query top-1
  similarity (max 0.492) overlaps answerable top-1 (min 0.379): refusal cannot be a bare score
  threshold; no threshold was tuned (`DATA_AND_EVALUATION.md`).

**Milestone 4 — Neo4j relationship graph + hybrid retrieval (done):**

- AuraDB provisioned by the user; `NEO4J_*` in `.env`. `graph/store.py` is the only Neo4j
  driver boundary: idempotent uniqueness constraints per label, single-transaction
  wipe-and-reload MERGE batches,
  parameterized Cypher (labels from a fixed mapping), three evidence-backed expansion queries
  (co-mention, SENT/RECEIVED correspondence, event involvement), `GraphUnavailableError` as
  the degraded-mode signal.
- `graph/loader.py` (pure, driver-free) derives the payload from extracted facts only:
  `MENTIONED_IN {chunk_id}` via mention→chunk offset mapping, `SENT`/`RECEIVED` from email
  `From:`/`To:` headers + custodians resolved against extracted person entities, events with
  deterministic uuid5 `event_id`s. DATE entities are not graph nodes; `AFFILIATED_WITH` and
  `REFERENCES` are not materialized (ADR-0011). No datagen/gold access (AST-enforced).
- `retrieval/hybrid.py`: `HybridRetriever` — deterministic LangChain `RunnableLambda` pipeline
  (vector leg → graph leg → merge). Top-5 vector hits seed expansion; fusion is constant-free
  rank interleaving (vector wins ties, top-1 never displaced); every graph hit carries its
  `GraphEvidence` (entity, relation, document, chunk). If Neo4j is down/unconfigured the
  result still carries the vector leg with `graph_available=False` + reason.
- `scripts/load_neo4j.py` extracts the corpus, loads AuraDB, and populates Supabase
  `entity_mentions` (shared IDs, document-offset spans + containing `chunk_id`).
  `scripts/evaluate_retrieval.py` now scores vector-only and graph-expanded from one pass.
- **Measured (seed 42):** relationship hit@5 0.500 → 0.833 (R@5 0.417 → 0.667), overall hit@5
  0.893 → 0.964, R@5 0.857 → 0.929, top-1 metrics unchanged, no category degraded at any k.
  Summed RRF was measured and rejected (hit@1 collapsed to 0.143 — ADR-0011). Relationship
  R@10 stays 0.750: multi-hop evidence beyond one hop is a known limitation.

**Milestone 5 — Investigation dashboard (done):**

- `ui/` is now three layers (ADR-0012): `backend.py` — the UI's only data boundary
  (`HybridRetriever.from_settings()`, vector-leg failures converted to an explicit
  `InvestigationOutcome` error, timeline via the graph store, artifact loading);
  `presenters.py` + `figures.py` — pure shaping/Plotly builders (evidence rows, evidence-only
  graph elements, chronological timeline frame, metric tables); `streamlit_app.py` — Streamlit
  wiring and caching only (`st.cache_resource` retriever, `st.cache_data` searches/timeline;
  body under `main()` so plain import is side-effect-free). No drivers in UI code, no LLM
  anywhere.
- Four tabs: **Investigate** (question → ranked cited chunks with vector/graph badges, cosine
  for vector hits only, fused rank score, per-chunk `GraphEvidence` trails), **Entity graph**
  (bipartite Plotly graph drawn exclusively from the current result's evidence rows),
  **Timeline** (new `Neo4jGraphStore.timeline_events()` reads `Event` nodes with `EVIDENCED_BY`
  document provenance + `INVOLVES` entity names; Plotly scatter + cited table), **Evaluation**
  (renders `artifacts/extraction_metrics.json` / `retrieval_metrics.json`; vector-only vs
  graph-expanded side by side, never blended).
- Degraded states are explicit: unconfigured `DATABASE_URL` → search disabled with an error;
  vector failure → error banner, never empty-as-success; `graph_available=False` → vector
  evidence retained + visible reason; Neo4j down → timeline notice; missing artifacts → the
  reproduction command.
- Streamlit's module file watcher is disabled in `.streamlit/config.toml`
  (`fileWatcherType = "none"`): with sentence-transformers/torch loaded it segfaulted the
  local server (exit 139, observed during verification). Streamlit floor raised to 1.59
  (`width="stretch"` replaces the deprecated `use_container_width`).

**Verification (run 2026-07-13, Milestone 5):** `uv run pytest` — 88 passed (25 new: presenter
shaping, evidence-only graph elements, figure construction/empty states, timeline record
conversion incl. neo4j `DateTime`, backend outcome conversion, artifact absent/present, and
headless `AppTest` renders of the no-credential, degraded-timeline, and missing-artifact
states); `uv run ruff check .` — clean; `uv run streamlit run …/ui/streamlit_app.py` — served
locally and inspected in a browser against live Supabase + AuraDB: hybrid search returned 10
chunks (5 graph-contributed) with evidence trails, entity graph rendered 16 nodes / 44
evidence-backed edges, timeline showed all 12 events, evaluation tables matched the committed
artifacts.

**Verification (run 2026-07-13, Milestone 4):** `uv run pytest` — 63 passed; `uv run ruff
check .` — clean; `uv run python scripts/load_neo4j.py` — 186 nodes / 536 relationships in
AuraDB (111 documents, 12 events, 349 mention edges, 138 SENT/RECEIVED) and 566
`entity_mentions` rows in Supabase, all confirmed by database counts; `uv run python
scripts/evaluate_retrieval.py` — metrics above against live Supabase + AuraDB.

**Verification (run 2026-07-13, Milestone 3):** `uv run pytest` — 43 passed (prior 32 plus retrieval metric
math, aggregation incl. negative queries, gold-query loading, store URL/vector-literal
helpers, blank-env-var config fallback); `uv run ruff check .` — clean; `uv run python scripts/index_pgvector.py` — 111
documents / 112 chunks confirmed by DB counts; `uv run python scripts/evaluate_retrieval.py` —
metrics above. Milestone 2 verification (run 2026-07-12): `uv run pytest` — 32 passed (byte-identical same-seed
regeneration, mention offset integrity, gold-label completeness, retrieval-label chunk
resolution, query-set balance, failure quarantine, extraction determinism, gold-leakage ban,
metric regression floors, scoring-math unit checks); `uv run ruff check .` — clean;
`uv run python scripts/bootstrap_data.py` and `scripts/evaluate_extraction.py` — outputs above;
generated data and artifacts correctly gitignored.

**What does NOT exist yet (do not assume otherwise):**

- No Community Cloud app, no live URL. Supabase and AuraDB are the only cloud services in use.
- No LLM answer generation anywhere — the dashboard displays retrieved, cited evidence only.
- No refusal threshold in runtime code (ADR-0010); negative questions display their retrieved
  chunks with scores — the UI does not fabricate a refusal.

## How To Run

```bash
uv sync
uv run pytest                                    # 88 tests
uv run ruff check .
uv run python scripts/bootstrap_data.py          # generate corpus + labels (seed 42)
uv run python scripts/evaluate_extraction.py     # extraction P/R/F1 -> artifacts/
uv run python scripts/index_pgvector.py          # embed + load Supabase (needs DATABASE_URL)
uv run python scripts/load_neo4j.py              # extract + load AuraDB graph (needs NEO4J_*)
uv run python scripts/evaluate_retrieval.py      # vector vs graph-expanded P/R/hit@k -> artifacts/
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
├── evaluation/      # extraction span matching + retrieval P/R/hit@k scoring
├── retrieval/       # embedder, PgVectorStore, SemanticRetriever, HybridRetriever (LangChain)
├── graph/           # Neo4j driver boundary (store) + fact-derived payload builder (loader)
└── ui/              # dashboard: backend (data boundary) → presenters/figures (pure) →
                     # streamlit_app (wiring); ADR-0012
tests/               # 88 tests
scripts/             # bootstrap_data, evaluate_extraction, index_pgvector, load_neo4j,
                     # evaluate_retrieval (real); verify_deployment is a stub
data/                # generated, gitignored; regenerate via bootstrap_data.py
```

## Known Limitations

- Synthetic documents are short and clean; most fit in a single 900-char chunk (112 chunks for
  111 docs). Retrieval recall at this granularity measured fine (R@10 0.929), so chunking was
  left unchanged.
- Extraction metrics on synthetic text will look better than on real-world documents —
  disclosed in `DATA_AND_EVALUATION.md` (ADR-0005).
- Graph expansion is one hop from seed-chunk entities; relationship R@10 stays 0.750 in both
  modes because evidence more than one hop out is unreachable (ADR-0011).
- Graph relationships are bounded by extraction quality: unresolved header names produce no
  SENT/RECEIVED edge, and missed entities produce no mention edge.

## Deployment

The public dashboard is live at
`https://legal-discovery-intelligence-graph-ma2dfvnresf84ytk4nzelm.streamlit.app/` on
Streamlit Community Cloud (Python 3.12). Supabase and AuraDB credentials are held only in
Streamlit Secrets. Live checks on 2026-07-14 confirmed both backend health indicators, hybrid
retrieval with cited evidence, and the entity graph, timeline, and evaluation views.
