"""Core domain models shared across ingestion, extraction, retrieval, and graph layers.

These models define the contract between subsystems. Identifiers are shared
between PostgreSQL (semantic retrieval) and Neo4j (relationship graph):
``Document.document_id``, ``Chunk.chunk_id``, and ``Entity.entity_id`` are the
join keys across both stores. See ``docs/DATA_MODEL.md`` for the full schema.
"""

from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import BaseModel, Field


def _new_id() -> str:
    return uuid4().hex


class DocumentType(StrEnum):
    """Synthetic discovery document categories."""

    EMAIL = "email"
    CONTRACT = "contract"
    MEMO = "memo"
    INVOICE = "invoice"
    MEETING_NOTES = "meeting_notes"
    OTHER = "other"  # ingested real files without a mapped category (PDF/DOCX)


class EntityType(StrEnum):
    """Entity categories produced by extraction (spaCy + deterministic regex)."""

    PERSON = "person"
    ORGANIZATION = "organization"
    MONEY = "money"
    DATE = "date"
    PROJECT = "project"
    LOCATION = "location"


class Document(BaseModel):
    """A single synthetic discovery document."""

    document_id: str = Field(default_factory=_new_id)
    doc_type: DocumentType
    title: str
    source_path: str = ""
    custodian: str = ""
    sent_at: datetime | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class Chunk(BaseModel):
    """A retrievable slice of a document; embedded and stored in pgvector."""

    chunk_id: str = Field(default_factory=_new_id)
    document_id: str
    text: str
    sequence: int = 0
    metadata: dict[str, str] = Field(default_factory=dict)


class Entity(BaseModel):
    """A canonical entity extracted from one or more documents."""

    entity_id: str = Field(default_factory=_new_id)
    entity_type: EntityType
    name: str
    aliases: list[str] = Field(default_factory=list)


class EntityMention(BaseModel):
    """A single occurrence of an entity within a chunk."""

    entity_id: str
    chunk_id: str
    document_id: str
    surface_text: str
    start_char: int
    end_char: int


class Event(BaseModel):
    """A dated event extracted for timeline analysis."""

    event_id: str = Field(default_factory=_new_id)
    document_id: str
    occurred_at: datetime
    description: str
    entity_ids: list[str] = Field(default_factory=list)
