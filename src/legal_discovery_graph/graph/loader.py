"""Build the graph payload from pipeline outputs — pure, driver-free.

Everything here derives from runtime facts already produced by the ingestion
and extraction pipeline (never from ``datagen`` or gold labels):

- mention provenance: each :class:`ResolvedMention` is mapped to the chunk
  whose document-offset slice contains it, giving every graph edge a
  retrievable ``chunk_id``;
- correspondence: ``From:``/``To:`` lines in email header blocks are parsed
  and resolved against the extracted person entities (exact canonical-name or
  alias match; unresolvable names are skipped, never guessed);
- events: deterministic ``event_id``s minted from (document, date) with
  :func:`legal_discovery_graph.ids.stable_id`.
"""

import re
from dataclasses import dataclass
from datetime import datetime

from legal_discovery_graph.extraction.extractor import ExtractionResult
from legal_discovery_graph.ids import stable_id
from legal_discovery_graph.ingestion.pipeline import RawDocumentRecord
from legal_discovery_graph.models import Chunk, Document, Entity, EntityMention, EntityType

_HEADER_RE = re.compile(r"^(From|To): ([^<\n]+?)(?: <[^>\n]*>)?\s*$", re.MULTILINE)

# DATE entities are timeline attributes, not graph nodes (docs/DATA_MODEL.md
# defines no Date label; a shared date would edge-connect unrelated documents).
_GRAPH_ENTITY_TYPES = frozenset(
    {
        EntityType.PERSON,
        EntityType.ORGANIZATION,
        EntityType.PROJECT,
        EntityType.LOCATION,
        EntityType.MONEY,
    }
)


@dataclass(frozen=True)
class MentionEdge:
    """``(entity)-[:MENTIONED_IN {chunk_id}]->(document)``."""

    entity_id: str
    document_id: str
    chunk_id: str


@dataclass(frozen=True)
class ParticipantEdge:
    """A provenance-bearing ``SENT`` or ``RECEIVED`` relationship."""

    entity_id: str
    document_id: str
    relation: str
    chunk_id: str


@dataclass(frozen=True)
class GraphEvent:
    """An extracted event with its deterministic graph identity."""

    event_id: str
    document_id: str
    occurred_at: datetime
    description: str
    entity_ids: tuple[str, ...]
    chunk_id: str


@dataclass(frozen=True)
class GraphPayload:
    """Everything ``Neo4jGraphStore.replace_graph`` needs, in plain data."""

    documents: tuple[Document, ...]
    entities: tuple[Entity, ...]
    events: tuple[GraphEvent, ...]
    mention_edges: tuple[MentionEdge, ...]
    participant_edges: tuple[ParticipantEdge, ...]


def chunk_for_offset(chunks: list[Chunk], offset: int) -> Chunk | None:
    """Return the chunk whose document slice contains ``offset``, if any."""
    for chunk in chunks:
        start = int(chunk.metadata["start_char"])
        end = int(chunk.metadata["end_char"])
        if start <= offset < end:
            return chunk
    return None


def parse_email_participants(body: str) -> tuple[list[str], list[str]]:
    """Extract (sender names, recipient names) from an email header block.

    Only the header block (before the first blank line) is scanned, so a
    quoted "From:" inside the message body never creates an edge.
    """
    parsed = _parse_email_participants_with_offsets(body)
    return [name for name, _ in parsed[0]], [name for name, _ in parsed[1]]


def _parse_email_participants_with_offsets(
    body: str,
) -> tuple[list[tuple[str, int]], list[tuple[str, int]]]:
    """Return header participant names and their document-body offsets."""
    header_block = body.split("\n\n", 1)[0]
    senders: list[tuple[str, int]] = []
    recipients: list[tuple[str, int]] = []
    for match in _HEADER_RE.finditer(header_block):
        name = " ".join(match.group(2).split())
        (senders if match.group(1) == "From" else recipients).append((name, match.start(2)))
    return senders, recipients


def _person_index(entities: list[Entity]) -> dict[str, str]:
    """Exact name/alias → entity_id for person entities; ambiguous names dropped."""
    index: dict[str, str] = {}
    ambiguous: set[str] = set()
    for entity in entities:
        if entity.entity_type is not EntityType.PERSON:
            continue
        for name in (entity.name, *entity.aliases):
            if name in index and index[name] != entity.entity_id:
                ambiguous.add(name)
            index.setdefault(name, entity.entity_id)
    return {name: eid for name, eid in index.items() if name not in ambiguous}


def build_graph_payload(
    records: list[RawDocumentRecord],
    extraction: ExtractionResult,
    chunks: list[Chunk],
) -> tuple[GraphPayload, list[EntityMention]]:
    """Assemble the Neo4j payload and the Postgres ``entity_mentions`` rows.

    Both outputs use the same shared IDs (``docs/DATA_MODEL.md``): the
    returned :class:`EntityMention` rows carry document-level character
    offsets and the containing ``chunk_id``.
    """
    chunks_by_document: dict[str, list[Chunk]] = {}
    for chunk in sorted(chunks, key=lambda c: (c.document_id, c.sequence)):
        chunks_by_document.setdefault(chunk.document_id, []).append(chunk)

    mention_edges: dict[MentionEdge, None] = {}  # ordered de-dupe
    entity_mentions: list[EntityMention] = []
    referenced_entity_ids: set[str] = set()
    mention_chunks: dict[tuple[str, str], str] = {}
    for mention in extraction.mentions:
        chunk = chunk_for_offset(chunks_by_document.get(mention.document_id, []), mention.start)
        if chunk is None:
            continue  # mention outside any chunk slice: no provenance, no edge
        entity_mentions.append(
            EntityMention(
                entity_id=mention.entity_id,
                chunk_id=chunk.chunk_id,
                document_id=mention.document_id,
                surface_text=mention.surface,
                start_char=mention.start,
                end_char=mention.end,
            )
        )
        if mention.entity_type in _GRAPH_ENTITY_TYPES:
            referenced_entity_ids.add(mention.entity_id)
            mention_chunks.setdefault((mention.document_id, mention.entity_id), chunk.chunk_id)
            mention_edges.setdefault(
                MentionEdge(
                    entity_id=mention.entity_id,
                    document_id=mention.document_id,
                    chunk_id=chunk.chunk_id,
                )
            )

    person_ids = _person_index(extraction.entities)
    participant_edges: dict[ParticipantEdge, None] = {}
    for record in records:
        document = record.document
        if document.doc_type.value == "email":
            senders, recipients = _parse_email_participants_with_offsets(record.body)
            for names, relation in ((senders, "sent"), (recipients, "received")):
                for name, offset in names:
                    entity_id = person_ids.get(name)
                    if entity_id is None:
                        continue
                    chunk = chunk_for_offset(
                        chunks_by_document.get(document.document_id, []), offset
                    )
                    chunk_id = chunk.chunk_id if chunk is not None else mention_chunks.get(
                        (document.document_id, entity_id)
                    )
                    if chunk_id is None:
                        continue
                    referenced_entity_ids.add(entity_id)
                    participant_edges.setdefault(
                        ParticipantEdge(
                            entity_id=entity_id,
                            document_id=document.document_id,
                            relation=relation,
                            chunk_id=chunk_id,
                        )
                    )
        else:
            # Custodian SENT provenance is the chunk containing an actual
            # custodian mention — never a positional proxy. No mention in any
            # chunk means no evidence, so no edge.
            custodian_id = person_ids.get(document.custodian)
            custodian_chunk = mention_chunks.get((document.document_id, custodian_id or ""))
            if custodian_id is not None and custodian_chunk is not None:
                referenced_entity_ids.add(custodian_id)
                participant_edges.setdefault(
                    ParticipantEdge(
                        entity_id=custodian_id,
                        document_id=document.document_id,
                        relation="sent",
                        chunk_id=custodian_chunk,
                    )
                )

    graph_entities = tuple(
        entity
        for entity in extraction.entities
        if entity.entity_type in _GRAPH_ENTITY_TYPES and entity.entity_id in referenced_entity_ids
    )

    events = tuple(
        GraphEvent(
            event_id=stable_id(
                "event", event.document_id, event.occurred_at.date().isoformat()
            ),
            document_id=event.document_id,
            occurred_at=event.occurred_at,
            description=event.description,
            entity_ids=tuple(
                entity_id for entity_id in event.entity_ids if entity_id in referenced_entity_ids
            ),
            chunk_id=chunk_for_offset(
                chunks_by_document.get(event.document_id, []), event.trigger_start
            ).chunk_id,
        )
        for event in extraction.events
        if chunk_for_offset(chunks_by_document.get(event.document_id, []), event.trigger_start)
        is not None
    )

    payload = GraphPayload(
        documents=tuple(record.document for record in records),
        entities=graph_entities,
        events=events,
        mention_edges=tuple(mention_edges),
        participant_edges=tuple(participant_edges),
    )
    return payload, entity_mentions


__all__ = [
    "GraphEvent",
    "GraphPayload",
    "MentionEdge",
    "ParticipantEdge",
    "build_graph_payload",
    "chunk_for_offset",
    "parse_email_participants",
]
