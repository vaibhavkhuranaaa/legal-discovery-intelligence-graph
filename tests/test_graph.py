"""Graph loading tests: payload building, provenance, shared IDs, leakage ban.

No Neo4j or PostgreSQL connection is made here — cloud round-trips are
verified by running scripts/load_neo4j.py.
"""

from datetime import UTC, datetime
from pathlib import Path

from legal_discovery_graph.extraction.events import ExtractedEvent
from legal_discovery_graph.extraction.extractor import ExtractionResult
from legal_discovery_graph.extraction.resolution import ResolvedMention
from legal_discovery_graph.graph import build_graph_payload
from legal_discovery_graph.graph.loader import chunk_for_offset, parse_email_participants
from legal_discovery_graph.graph.store import _CONSTRAINTS, NODE_LABELS
from legal_discovery_graph.ingestion.pipeline import RawDocumentRecord
from legal_discovery_graph.models import Chunk, Document, DocumentType, Entity, EntityType

GRAPH_SRC = Path(__file__).parent.parent / "src" / "legal_discovery_graph" / "graph"
RETRIEVAL_SRC = Path(__file__).parent.parent / "src" / "legal_discovery_graph" / "retrieval"

EMAIL_BODY = (
    "From: Omar Tran <omar@meridian-aero.example>\n"
    "To: Dana Reyes <dana@meridian-aero.example>\n"
    "Date: March 3, 2023\n"
    "Subject: Northgate invoice\n\n"
    "Omar Tran approved the Northgate Supply payment of $45,000."
)


def _record(document_id: str, body: str, doc_type: DocumentType = DocumentType.EMAIL):
    return RawDocumentRecord(
        document=Document(document_id=document_id, doc_type=doc_type, title="t"),
        body=body,
    )


def _chunk(chunk_id: str, document_id: str, start: int, end: int) -> Chunk:
    return Chunk(
        chunk_id=chunk_id,
        document_id=document_id,
        text="x",
        sequence=0,
        metadata={"start_char": str(start), "end_char": str(end)},
    )


def _mention(document_id: str, entity: Entity, start: int) -> ResolvedMention:
    return ResolvedMention(
        document_id=document_id,
        entity_type=entity.entity_type,
        surface=entity.name,
        start=start,
        end=start + len(entity.name),
        entity_id=entity.entity_id,
        canonical_name=entity.name,
    )


PERSON = Entity(entity_id="p" * 32, entity_type=EntityType.PERSON, name="Omar Tran")
ORG = Entity(entity_id="o" * 32, entity_type=EntityType.ORGANIZATION, name="Northgate Supply")
DATE = Entity(entity_id="t" * 32, entity_type=EntityType.DATE, name="2023-03-03")


class TestEmailHeaderParsing:
    def test_parses_from_and_to_with_addresses(self):
        senders, recipients = parse_email_participants(EMAIL_BODY)
        assert senders == ["Omar Tran"]
        assert recipients == ["Dana Reyes"]

    def test_quoted_headers_in_message_body_are_ignored(self):
        body = "From: A Person\n\nAs I wrote earlier:\nFrom: Someone Else\nplease review."
        senders, recipients = parse_email_participants(body)
        assert senders == ["A Person"]
        assert recipients == []


class TestChunkMapping:
    def test_offset_maps_to_containing_chunk(self):
        chunks = [_chunk("c1", "d1", 0, 100), _chunk("c2", "d1", 100, 200)]
        assert chunk_for_offset(chunks, 99).chunk_id == "c1"
        assert chunk_for_offset(chunks, 100).chunk_id == "c2"
        assert chunk_for_offset(chunks, 250) is None


class TestBuildGraphPayload:
    def _build(self):
        record = _record("d" * 32, EMAIL_BODY)
        chunks = [_chunk("c" * 32, "d" * 32, 0, len(EMAIL_BODY))]
        extraction = ExtractionResult(
            entities=[PERSON, ORG, DATE],
            mentions=[
                _mention("d" * 32, PERSON, EMAIL_BODY.index("Omar Tran approved")),
                _mention("d" * 32, ORG, EMAIL_BODY.index("Northgate")),
                _mention("d" * 32, DATE, 40),
            ],
            events=[
                ExtractedEvent(
                    document_id="d" * 32,
                    occurred_at=datetime(2023, 3, 3, tzinfo=UTC),
                    description="approved payment",
                    entity_ids=(PERSON.entity_id, ORG.entity_id, DATE.entity_id),
                    trigger="approved",
                    trigger_start=EMAIL_BODY.index("approved"),
                )
            ],
        )
        return build_graph_payload([record], extraction, chunks)

    def test_mention_edges_carry_chunk_provenance_and_exclude_dates(self):
        payload, _ = self._build()
        assert {edge.entity_id for edge in payload.mention_edges} == {
            PERSON.entity_id,
            ORG.entity_id,
        }
        assert all(edge.chunk_id == "c" * 32 for edge in payload.mention_edges)
        assert DATE.entity_id not in {entity.entity_id for entity in payload.entities}

    def test_entity_mentions_keep_shared_ids_and_document_offsets(self):
        _, entity_mentions = self._build()
        assert len(entity_mentions) == 3  # DATE keeps Postgres provenance
        omar = next(m for m in entity_mentions if m.entity_id == PERSON.entity_id)
        assert omar.chunk_id == "c" * 32
        assert omar.document_id == "d" * 32
        assert EMAIL_BODY[omar.start_char : omar.end_char] == "Omar Tran"

    def test_sender_edge_resolved_from_header(self):
        payload, _ = self._build()
        sent = [edge for edge in payload.participant_edges if edge.relation == "sent"]
        assert sent == [next(iter(sent))] and sent[0].entity_id == PERSON.entity_id
        assert sent[0].chunk_id == "c" * 32
        # "Dana Reyes" is not an extracted entity, so no RECEIVED edge is guessed.
        assert not any(edge.relation == "received" for edge in payload.participant_edges)

    def test_event_ids_are_deterministic_and_dates_dropped_from_involves(self):
        payload_a, _ = self._build()
        payload_b, _ = self._build()
        assert payload_a.events[0].event_id == payload_b.events[0].event_id
        assert DATE.entity_id not in payload_a.events[0].entity_ids
        assert set(payload_a.events[0].entity_ids) == {PERSON.entity_id, ORG.entity_id}
        assert payload_a.events[0].chunk_id == "c" * 32

    def test_mention_without_containing_chunk_is_skipped(self):
        record = _record("d" * 32, EMAIL_BODY)
        chunks = [_chunk("c" * 32, "d" * 32, 0, 10)]  # covers almost nothing
        extraction = ExtractionResult(
            entities=[ORG], mentions=[_mention("d" * 32, ORG, 500)], events=[]
        )
        payload, entity_mentions = self._build_from(record, extraction, chunks)
        assert payload.mention_edges == ()
        assert entity_mentions == []

    @staticmethod
    def _build_from(record, extraction, chunks):
        return build_graph_payload([record], extraction, chunks)


class TestGraphSchema:
    def test_every_node_label_has_a_uniqueness_constraint(self):
        constrained = " ".join(_CONSTRAINTS)
        for label in ("Document", "Event", *NODE_LABELS.values()):
            assert f"FOR (n:{label})" in constrained

    def test_date_is_not_a_graph_label(self):
        assert EntityType.DATE not in NODE_LABELS


def test_no_datagen_or_gold_leakage_in_graph_and_retrieval_sources() -> None:
    """Graph/retrieval runtime code must never consult datagen or gold labels."""
    import ast

    for src_dir in (GRAPH_SRC, RETRIEVAL_SRC):
        for path in src_dir.glob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                    assert "data/labels" not in node.value, f"{path.name} references gold labels"
                    continue
                else:
                    continue
                for name in names:
                    assert "datagen" not in name, f"{path.name} imports {name}"
