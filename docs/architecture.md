# Architecture

Target cloud architecture for the deployed system. Foundation milestone status: scaffold and
health-check app only — components below are **planned** and marked implemented in
`roadmap.md` as they are verified.

## System Overview

```
Synthetic discovery documents (scripts/bootstrap_data.py → data/raw/)
        │
        ▼
Ingestion (src/.../ingestion) ── parse, normalize, chunk ──► data/processed/
        │
        ▼
Extraction (src/.../extraction) ── spaCy NER + deterministic regex ──► entities, mentions, events
        │
        ├────────────────► PostgreSQL + pgvector (Supabase)
        │                    chunks + sentence-transformer embeddings + metadata
        │
        └────────────────► Neo4j AuraDB
                             (:Person)(:Organization)(:Document)(:Event)… + relationships
        ▼
Retrieval orchestration (src/.../retrieval, LangChain)
   vector top-k from pgvector  ─┐
   graph expansion from Neo4j  ─┴─► evidence bundle (chunks + subgraph + events)
        │
        ▼
Streamlit dashboard (src/.../ui, Streamlit Community Cloud)
   cited evidence · Plotly entity graph · Plotly timeline · evaluation metrics
        ▲
Evaluation (src/.../evaluation) — precision/recall/F1 vs gold labels (data/labels/)
```

## Component Responsibilities

| Component | Responsibility |
|---|---|
| `scripts/bootstrap_data.py` | Deterministic, seedable synthetic corpus + gold labels generation |
| `ingestion/` | Document loading, normalization, chunking; owns the `Document`/`Chunk` contract |
| `extraction/` | Entity/mention/event extraction (spaCy + regex), entity resolution |
| `retrieval/` | Embedding, pgvector search, LangChain orchestration of vector + graph retrieval |
| `graph/` | Neo4j driver boundary: schema constraints, loading, Cypher query API |
| `evaluation/` | Gold-label scoring: extraction and retrieval precision/recall/F1 |
| `ui/` | Streamlit app: search, graph view, timeline, metrics; no business logic |
| `config.py` | Single settings accessor (`get_settings()`); the only env-var boundary |
| `models.py` | Pydantic contracts shared across all subsystems; shared IDs across both stores |

Database access is isolated: only `retrieval/` touches PostgreSQL and only `graph/` touches the
Neo4j driver. The UI and orchestration layers depend on those modules' interfaces, never on
drivers directly — mirroring the vendor-isolation adapter pattern that keeps business logic
independently testable.

## Data Flow & Shared Identity

Documents, chunks, and entities carry UUID identifiers minted once at ingestion/extraction time
and stored in **both** systems: pgvector rows and Neo4j nodes reference the same
`document_id`/`chunk_id`/`entity_id`. This is the join that makes Graph RAG work — a vector hit
in Postgres pivots directly to its Neo4j neighborhood without fuzzy matching. Details:
`DATA_MODEL.md`.

## Deployment Topology

- **Streamlit Community Cloud** runs the app from GitHub (`requirements.txt` exported from
  `uv.lock`); secrets injected via Streamlit secrets.
- **Supabase** hosts PostgreSQL with the pgvector extension (managed, free tier).
- **Neo4j AuraDB Free** hosts the graph.
- Indexing (`scripts/index_pgvector.py`, `scripts/load_neo4j.py`) runs from the developer
  machine against the cloud backends; the deployed app is read-only against both stores.

## Failure Boundaries

- **Postgres unavailable** → semantic search degrades to an explicit error state in the UI;
  the app must render and say so, never pretend with empty results.
- **Neo4j unavailable** → retrieval still returns vector evidence; graph/timeline panels show a
  degraded-mode notice. Vector and graph legs fail independently.
- **Embedding model download failure** (cold start on Community Cloud) → surfaced at startup
  health check, not mid-query.
- **Ingestion/extraction failures** → failed documents quarantined to `data/failed/` with error
  records; a bad document never aborts a batch.
- **Configuration errors** → validated once at startup via `get_settings()`; missing secrets
  produce a clear startup error, not runtime stack traces.
