"""Extraction orchestration: regex lane + NER lane → resolved mentions + events.

Merge policy: the deterministic regex lane wins on span overlap — a statistical
span never overrides a rule-derived one, and NER money/date/cardinal output is
discarded entirely (patterns.py owns those types).

Corpus-level majority type voting: when the same surface is typed differently
across documents (spaCy tags "Nadia Osei" PERSON in one memo, ORG in another),
every occurrence is re-typed to the strict majority type. Ties keep the
original per-span prediction.
"""

from collections import Counter
from dataclasses import dataclass, field, replace

from legal_discovery_graph.extraction.events import ExtractedEvent, extract_events
from legal_discovery_graph.extraction.ner import extract_ner_spans
from legal_discovery_graph.extraction.patterns import RawSpan, extract_pattern_spans
from legal_discovery_graph.extraction.resolution import ResolvedMention, resolve_mentions
from legal_discovery_graph.ingestion.pipeline import RawDocumentRecord
from legal_discovery_graph.models import Entity, EntityType


@dataclass
class ExtractionResult:
    """Corpus-level extraction output."""

    entities: list[Entity] = field(default_factory=list)
    mentions: list[ResolvedMention] = field(default_factory=list)
    events: list[ExtractedEvent] = field(default_factory=list)


def _merge_spans(pattern_spans: list[RawSpan], ner_spans: list[RawSpan]) -> list[RawSpan]:
    """Combine lanes; drop any NER span overlapping a regex span."""
    merged = list(pattern_spans)
    for span in ner_spans:
        overlaps = any(span.start < other.end and other.start < span.end for other in pattern_spans)
        if not overlaps:
            merged.append(span)
    return sorted(merged, key=lambda span: (span.start, span.end))


def extract_document_spans(body: str) -> list[RawSpan]:
    """Run both extraction lanes over one document body and merge them."""
    return _merge_spans(extract_pattern_spans(body), extract_ner_spans(body))


_VOTED_TYPES = (EntityType.PERSON, EntityType.ORGANIZATION, EntityType.LOCATION)


def _majority_type_vote(
    spans_by_document: list[tuple[str, RawSpan]],
) -> list[tuple[str, RawSpan]]:
    """Re-type each NER surface to its strict corpus-wide majority type."""
    votes: dict[str, Counter[EntityType]] = {}
    for _, span in spans_by_document:
        if span.entity_type in _VOTED_TYPES:
            votes.setdefault(" ".join(span.surface.split()), Counter())[span.entity_type] += 1

    winners: dict[str, EntityType] = {}
    for surface, counter in votes.items():
        ranked = counter.most_common(2)
        if len(ranked) == 1 or ranked[0][1] > ranked[1][1]:
            winners[surface] = ranked[0][0]

    revoted: list[tuple[str, RawSpan]] = []
    for document_id, span in spans_by_document:
        winner = winners.get(" ".join(span.surface.split()))
        if winner is not None and span.entity_type in _VOTED_TYPES and winner != span.entity_type:
            span = replace(span, entity_type=winner)
        revoted.append((document_id, span))
    return revoted


def extract_corpus(records: list[RawDocumentRecord]) -> ExtractionResult:
    """Extract and resolve entities, mentions, and events for a whole corpus.

    Resolution is corpus-wide (short name forms fold into full names seen in
    other documents; surface types are majority-voted), so extraction is a
    batch operation by design.
    """
    spans_by_document: list[tuple[str, RawSpan]] = []
    for record in records:
        for span in extract_document_spans(record.body):
            spans_by_document.append((record.document.document_id, span))
    spans_by_document = _majority_type_vote(spans_by_document)

    entities, mentions = resolve_mentions(spans_by_document)

    events: list[ExtractedEvent] = []
    mentions_by_doc: dict[str, list[ResolvedMention]] = {}
    for mention in mentions:
        mentions_by_doc.setdefault(mention.document_id, []).append(mention)
    for record in records:
        doc_id = record.document.document_id
        events.extend(extract_events(doc_id, record.body, mentions_by_doc.get(doc_id, [])))

    return ExtractionResult(entities=entities, mentions=mentions, events=events)
