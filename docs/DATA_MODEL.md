# Data Model

Storage model across the two backends. Source-of-truth Pydantic contracts:
`src/legal_discovery_graph/models.py`. Both stores are provisioned and implemented:
PostgreSQL + pgvector in Milestone 3, the Neo4j graph in Milestone 4 (loaded by
`scripts/load_neo4j.py`; relationship derivations in ADR-0011).

## Shared Identity Across Systems

The same identifiers appear in PostgreSQL and Neo4j so a vector search hit can pivot directly
into the graph:

| ID | Minted by | In PostgreSQL | In Neo4j |
|---|---|---|---|
| `document_id` (uuid4 hex) | ingestion | `documents.document_id`, `chunks.document_id` | `(:Document {document_id})` |
| `chunk_id` (uuid4 hex) | ingestion | `chunks.chunk_id` (PK) | `chunk_id` property on `MENTIONED_IN` edges (mention provenance) |
| `entity_id` (uuid4 hex) | extraction (post-resolution) | `entity_mentions.entity_id` | `(:Person/:Organization/… {entity_id})` |
| `event_id` (uuid4 hex) | extraction | `events.event_id` | `(:Event {event_id})` |

IDs are minted exactly once, at ingestion/extraction time, then written to both stores. Neither
store generates its own identity for shared objects.

## PostgreSQL + pgvector (Supabase)

Semantic retrieval store. Managed via SQLAlchemy + psycopg; embeddings via
`sentence-transformers/all-MiniLM-L6-v2` (384 dimensions — revisit in an ADR if the model
changes).

```sql
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE documents (
    document_id TEXT PRIMARY KEY,
    doc_type    TEXT NOT NULL,          -- email | contract | memo | invoice | meeting_notes
    title       TEXT NOT NULL,
    custodian   TEXT,
    sent_at     TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE chunks (
    chunk_id    TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(document_id),
    sequence    INT  NOT NULL,
    text        TEXT NOT NULL,
    metadata    JSONB NOT NULL DEFAULT '{}'::jsonb,
    embedding   VECTOR(384) NOT NULL
);

CREATE TABLE entity_mentions (            -- mention provenance (loaded by load_neo4j.py);
                                          -- start/end are document-body character offsets
    entity_id   TEXT NOT NULL,
    chunk_id    TEXT NOT NULL REFERENCES chunks(chunk_id),
    document_id TEXT NOT NULL REFERENCES documents(document_id),
    surface_text TEXT NOT NULL,
    start_char  INT NOT NULL,
    end_char    INT NOT NULL
);

-- ANN index; HNSW with cosine distance to match normalized sentence-transformer embeddings
CREATE INDEX chunks_embedding_idx ON chunks USING hnsw (embedding vector_cosine_ops);
```

## Neo4j AuraDB Graph Model

Relationship store for investigation queries.

**Nodes** (label per entity type; all carry the shared ID as a uniqueness-constrained key):

- `(:Document {document_id, doc_type, title, sent_at})`
- `(:Person {entity_id, name})`
- `(:Organization {entity_id, name})`
- `(:Project {entity_id, name})`
- `(:Location {entity_id, name})`
- `(:Money {entity_id, name})` — name is the canonical amount surface, e.g. `$45,000`
- `(:Event {event_id, occurred_at, description})`

DATE entities are deliberately **not** graph nodes: a shared date would edge-connect unrelated
documents into one hub. Dates stay in Postgres mention provenance for timeline work (ADR-0011).

**Relationships** (all derived from extracted/runtime facts — never from gold labels):

```
(:Person)-[:SENT {chunk_id}]->(:Document)      // email From: header / doc custodian
(:Person)-[:RECEIVED {chunk_id}]->(:Document)  // email To: header
(:Person|:Organization|:Project|:Location|:Money)-[:MENTIONED_IN {chunk_id}]->(:Document)
(:Event)-[:EVIDENCED_BY {chunk_id}]->(:Document)
(:Event)-[:INVOLVES {chunk_id}]->(:Person|:Organization|:Project|:Location|:Money)
```

Every relationship carries the source `chunk_id` that evidences it. `MENTIONED_IN` records the
mention itself; correspondence edges point to the parsed header or custodian mention, and event
edges point to the extracted trigger. The graph never asserts a relationship without provenance.

`AFFILIATED_WITH` and `REFERENCES` from the original design are **not materialized**: no
extraction lane produces them as facts, and co-mention reasoning happens at query time through
`MENTIONED_IN` paths (ADR-0011). Header names that don't resolve to an extracted person entity
are skipped, never guessed.

**Constraints** (created by `scripts/load_neo4j.py`): uniqueness on each label's shared-ID
property.

## Gold Labels (`data/labels/`)

Because the corpus is synthetic, ground truth is emitted at generation time: per-document
entity mentions and events, plus retrieval query→relevant-chunk pairs. Format and scoring
methodology: `DATA_AND_EVALUATION.md`.
