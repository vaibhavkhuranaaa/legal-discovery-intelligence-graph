"""PostgreSQL + pgvector storage for semantic retrieval.

Implements the retrieval side of ``docs/DATA_MODEL.md``: the ``documents``,
``chunks``, and ``entity_mentions`` tables plus the HNSW cosine index.
Embeddings are bound as pgvector text literals (``[0.1,0.2,...]``) and cast
server-side, so no driver-level vector adapter registration is needed.

``entity_mentions`` is created here so the schema is complete, but it is
populated at the graph milestone, when mention provenance is first consumed.
"""

import json
from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy import Engine, create_engine, text

from legal_discovery_graph.models import Chunk, Document, EntityMention

_SCHEMA_STATEMENTS: tuple[str, ...] = (
    "CREATE EXTENSION IF NOT EXISTS vector",
    """
    CREATE TABLE IF NOT EXISTS documents (
        document_id TEXT PRIMARY KEY,
        doc_type    TEXT NOT NULL,
        title       TEXT NOT NULL,
        custodian   TEXT,
        sent_at     TIMESTAMPTZ,
        created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS chunks (
        chunk_id    TEXT PRIMARY KEY,
        document_id TEXT NOT NULL REFERENCES documents(document_id),
        sequence    INT  NOT NULL,
        text        TEXT NOT NULL,
        metadata    JSONB NOT NULL DEFAULT '{}'::jsonb,
        embedding   VECTOR(384) NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS entity_mentions (
        entity_id   TEXT NOT NULL,
        chunk_id    TEXT NOT NULL REFERENCES chunks(chunk_id),
        document_id TEXT NOT NULL REFERENCES documents(document_id),
        surface_text TEXT NOT NULL,
        start_char  INT NOT NULL,
        end_char    INT NOT NULL
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS chunks_embedding_idx
    ON chunks USING hnsw (embedding vector_cosine_ops)
    """,
)

_SEARCH_SQL = """
    SELECT chunk_id,
           document_id,
           sequence,
           text,
           metadata,
           1 - (embedding <=> CAST(:query_embedding AS vector)) AS score
    FROM chunks
    ORDER BY embedding <=> CAST(:query_embedding AS vector)
    LIMIT :limit
"""


@dataclass(frozen=True)
class RetrievedChunk:
    """One vector-search hit, with cosine similarity in ``score`` (1 = identical)."""

    chunk_id: str
    document_id: str
    sequence: int
    text: str
    metadata: dict[str, str]
    score: float


def to_sqlalchemy_url(database_url: str) -> str:
    """Pin the psycopg (v3) driver onto a plain ``postgresql://`` URL."""
    if database_url.startswith("postgresql://"):
        return database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    return database_url


def vector_literal(embedding: Sequence[float]) -> str:
    """Render an embedding as a pgvector input literal, e.g. ``[0.1,0.2]``."""
    return "[" + ",".join(repr(float(value)) for value in embedding) + "]"


class PgVectorStore:
    """Semantic retrieval store backed by PostgreSQL + pgvector."""

    def __init__(self, database_url: str) -> None:
        if not database_url:
            raise ValueError("DATABASE_URL is not configured (see .env.example)")
        self._engine: Engine = create_engine(to_sqlalchemy_url(database_url))

    def apply_schema(self) -> None:
        """Create the extension, tables, and HNSW index if they do not exist."""
        with self._engine.begin() as connection:
            for statement in _SCHEMA_STATEMENTS:
                connection.execute(text(statement))

    def replace_corpus(
        self,
        documents: Sequence[Document],
        chunks: Sequence[Chunk],
        embeddings: Sequence[Sequence[float]],
    ) -> None:
        """Atomically replace all stored documents and chunks.

        The corpus is small and regenerated deterministically, so full
        replace-on-index is simpler and safer than incremental upserts.
        """
        if len(chunks) != len(embeddings):
            raise ValueError(f"{len(chunks)} chunks but {len(embeddings)} embeddings")
        with self._engine.begin() as connection:
            connection.execute(text("DELETE FROM entity_mentions"))
            connection.execute(text("DELETE FROM chunks"))
            connection.execute(text("DELETE FROM documents"))
            connection.execute(
                text(
                    "INSERT INTO documents (document_id, doc_type, title, custodian, sent_at)"
                    " VALUES (:document_id, :doc_type, :title, :custodian, :sent_at)"
                ),
                [
                    {
                        "document_id": document.document_id,
                        "doc_type": document.doc_type.value,
                        "title": document.title,
                        "custodian": document.custodian or None,
                        "sent_at": document.sent_at,
                    }
                    for document in documents
                ],
            )
            connection.execute(
                text(
                    "INSERT INTO chunks (chunk_id, document_id, sequence, text, metadata,"
                    " embedding) VALUES (:chunk_id, :document_id, :sequence, :text,"
                    " CAST(:metadata AS jsonb), CAST(:embedding AS vector))"
                ),
                [
                    {
                        "chunk_id": chunk.chunk_id,
                        "document_id": chunk.document_id,
                        "sequence": chunk.sequence,
                        "text": chunk.text,
                        "metadata": json.dumps(chunk.metadata, sort_keys=True),
                        "embedding": vector_literal(embedding),
                    }
                    for chunk, embedding in zip(chunks, embeddings, strict=True)
                ],
            )

    def search(self, query_embedding: Sequence[float], limit: int = 5) -> list[RetrievedChunk]:
        """Return the ``limit`` nearest chunks by cosine similarity, best first."""
        with self._engine.connect() as connection:
            rows = connection.execute(
                text(_SEARCH_SQL),
                {"query_embedding": vector_literal(query_embedding), "limit": limit},
            ).mappings()
            return [
                RetrievedChunk(
                    chunk_id=row["chunk_id"],
                    document_id=row["document_id"],
                    sequence=row["sequence"],
                    text=row["text"],
                    metadata=dict(row["metadata"]),
                    score=float(row["score"]),
                )
                for row in rows
            ]

    def replace_entity_mentions(self, mentions: Sequence[EntityMention]) -> None:
        """Atomically replace mention provenance rows (same rationale as corpus)."""
        with self._engine.begin() as connection:
            connection.execute(text("DELETE FROM entity_mentions"))
            if mentions:
                connection.execute(
                    text(
                        "INSERT INTO entity_mentions (entity_id, chunk_id, document_id,"
                        " surface_text, start_char, end_char) VALUES (:entity_id, :chunk_id,"
                        " :document_id, :surface_text, :start_char, :end_char)"
                    ),
                    [mention.model_dump() for mention in mentions],
                )

    def fetch_chunks(self, chunk_ids: Sequence[str]) -> list[RetrievedChunk]:
        """Hydrate chunks by ID (score 0.0 — no similarity was computed)."""
        if not chunk_ids:
            return []
        with self._engine.connect() as connection:
            rows = connection.execute(
                text(
                    "SELECT chunk_id, document_id, sequence, text, metadata FROM chunks"
                    " WHERE chunk_id = ANY(:chunk_ids)"
                ),
                {"chunk_ids": list(chunk_ids)},
            ).mappings()
            by_id = {
                row["chunk_id"]: RetrievedChunk(
                    chunk_id=row["chunk_id"],
                    document_id=row["document_id"],
                    sequence=row["sequence"],
                    text=row["text"],
                    metadata=dict(row["metadata"]),
                    score=0.0,
                )
                for row in rows
            }
        return [by_id[chunk_id] for chunk_id in chunk_ids if chunk_id in by_id]

    def corpus_counts(self) -> dict[str, int]:
        """Row counts for verification after indexing."""
        with self._engine.connect() as connection:
            return {
                "documents": connection.execute(
                    text("SELECT count(*) FROM documents")
                ).scalar_one(),
                "chunks": connection.execute(text("SELECT count(*) FROM chunks")).scalar_one(),
                "entity_mentions": connection.execute(
                    text("SELECT count(*) FROM entity_mentions")
                ).scalar_one(),
            }
