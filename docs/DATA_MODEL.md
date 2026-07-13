# Data Model

Planned storage model across the two backends. Source-of-truth Pydantic contracts:
`src/legal_discovery_graph/models.py`. Not yet provisioned — this is the design the retrieval
and graph milestones implement.

## Shared Identity Across Systems

The same identifiers appear in PostgreSQL and Neo4j so a vector search hit can pivot directly
into the graph:

| ID | Minted by | In PostgreSQL | In Neo4j |
|---|---|---|---|
| `document_id` (uuid4 hex) | ingestion | `documents.document_id`, `chunks.document_id` | `(:Document {document_id})` |
| `chunk_id` (uuid4 hex) | ingestion | `chunks.chunk_id` (PK) | `(:Chunk {chunk_id})` (mention provenance) |
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

CREATE TABLE entity_mentions (            -- provenance for extraction evaluation
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
- `(:Money {entity_id, amount, currency})`
- `(:Event {event_id, occurred_at, description})`

**Relationships:**

```
(:Person)-[:SENT]->(:Document)                 // email author / doc custodian
(:Person)-[:RECEIVED]->(:Document)
(:Person|:Organization|:Project|:Location|:Money)-[:MENTIONED_IN {chunk_id}]->(:Document)
(:Person)-[:AFFILIATED_WITH]->(:Organization)
(:Event)-[:EVIDENCED_BY]->(:Document)
(:Event)-[:INVOLVES]->(:Person|:Organization|:Money)
(:Document)-[:REFERENCES]->(:Document)         // e.g. invoice referenced by email
```

`MENTIONED_IN` carries `chunk_id` so every graph edge is traceable to the exact retrievable
passage that evidences it — the graph never asserts a relationship without provenance.

**Constraints** (created by `scripts/load_neo4j.py`): uniqueness on each label's shared-ID
property.

## Gold Labels (`data/labels/`)

Because the corpus is synthetic, ground truth is emitted at generation time: per-document
entity mentions and events, plus retrieval query→relevant-chunk pairs. Format and scoring
methodology: `DATA_AND_EVALUATION.md`.
