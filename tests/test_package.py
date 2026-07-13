"""Foundation tests: package imports, configuration, and core models."""

from datetime import UTC, datetime

from legal_discovery_graph import __version__
from legal_discovery_graph.config import Settings
from legal_discovery_graph.models import (
    Chunk,
    Document,
    DocumentType,
    Entity,
    EntityMention,
    EntityType,
    Event,
)


def test_package_has_version() -> None:
    assert __version__ == "0.1.0"


def test_settings_load_without_environment() -> None:
    settings = Settings(_env_file=None)
    assert settings.database_url == ""
    assert settings.neo4j_uri == ""
    assert settings.embedding_model_name.startswith("sentence-transformers/")


def test_document_and_chunk_share_document_id() -> None:
    doc = Document(doc_type=DocumentType.EMAIL, title="Re: Project Falcon pricing")
    chunk = Chunk(document_id=doc.document_id, text="Pricing discussion...", sequence=0)
    assert chunk.document_id == doc.document_id
    assert len(doc.document_id) == 32  # uuid4 hex


def test_entity_mention_links_entity_chunk_and_document() -> None:
    entity = Entity(entity_type=EntityType.PERSON, name="Jane Doe")
    doc = Document(doc_type=DocumentType.MEMO, title="Internal memo")
    chunk = Chunk(document_id=doc.document_id, text="Jane Doe approved the transfer.")
    mention = EntityMention(
        entity_id=entity.entity_id,
        chunk_id=chunk.chunk_id,
        document_id=doc.document_id,
        surface_text="Jane Doe",
        start_char=0,
        end_char=8,
    )
    assert mention.entity_id == entity.entity_id
    assert mention.chunk_id == chunk.chunk_id


def test_event_is_timeline_ready() -> None:
    event = Event(
        document_id="d" * 32,
        occurred_at=datetime(2024, 3, 15, tzinfo=UTC),
        description="Wire transfer approved",
    )
    assert event.occurred_at.year == 2024
    assert event.entity_ids == []


def test_ids_are_unique() -> None:
    ids = {Document(doc_type=DocumentType.INVOICE, title="inv").document_id for _ in range(50)}
    assert len(ids) == 50
