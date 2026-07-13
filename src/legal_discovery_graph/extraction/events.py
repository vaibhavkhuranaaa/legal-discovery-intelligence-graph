"""Deterministic dated-event extraction.

An event is emitted for a document when a body paragraph (never the
From/To/Date/Subject header block) contains a transaction-vocabulary trigger.
The event date is the document's primary (first) extracted DATE mention, and
the involved entities are those resolved within the triggering paragraph.

Scope is deliberately high-precision: the trigger lexicon covers
procurement/audit transaction language (awarded, wired, entered into, …), so
recall is bounded by lexicon coverage — a documented limitation, not a bug.
At most one event is emitted per document.
"""

import re
from dataclasses import dataclass
from datetime import UTC, datetime

from legal_discovery_graph.extraction.resolution import ResolvedMention
from legal_discovery_graph.models import EntityType

TRIGGERS = (
    "approved",
    "met with",
    "is awarded",
    "sealed bid",
    "pleased to submit",
    "is issued",
    "entered into",
    "signed",
    "wired",
    "opened engagement",
    "escalation",
    "paid twice",
    "placed on",
    "executed",
    "terminated",
    "resigned",
)

_TRIGGER_RE = re.compile("|".join(re.escape(t) for t in TRIGGERS), re.IGNORECASE)
_HEADER_LINE_RE = re.compile(r"^(From|To|Date|Subject|Bill To|Distribution|Attendees):")


@dataclass(frozen=True)
class ExtractedEvent:
    """A predicted dated event, evidenced by one document."""

    document_id: str
    occurred_at: datetime
    description: str
    entity_ids: tuple[str, ...]
    trigger: str
    trigger_start: int


def _is_header_paragraph(paragraph: str) -> bool:
    lines = [line for line in paragraph.splitlines() if line.strip()]
    return bool(lines) and all(
        _HEADER_LINE_RE.match(line) or ":" not in line and len(line.split()) <= 6 for line in lines
    )


def _primary_date(mentions: list[ResolvedMention]) -> datetime | None:
    dates = sorted(
        (m for m in mentions if m.entity_type is EntityType.DATE),
        key=lambda m: m.start,
    )
    if not dates:
        return None
    try:
        parsed = datetime.strptime(dates[0].surface, "%B %d, %Y")
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC)


def extract_events(
    document_id: str, body: str, mentions: list[ResolvedMention]
) -> list[ExtractedEvent]:
    """Return at most one dated event for the document, if triggered."""
    occurred_at = _primary_date(mentions)
    if occurred_at is None:
        return []

    cursor = 0
    for paragraph in body.split("\n\n"):
        start, end = cursor, cursor + len(paragraph)
        cursor = end + 2
        if not paragraph.strip() or _is_header_paragraph(paragraph):
            continue
        match = _TRIGGER_RE.search(paragraph)
        if not match:
            continue
        involved = tuple(
            dict.fromkeys(  # preserve order, dedupe
                m.entity_id
                for m in mentions
                if start <= m.start < end and m.entity_type is not EntityType.DATE
            )
        )
        if not involved:
            # An event needs participants; trigger words in entity-free prose
            # (e.g. "no escalation was required") are not events.
            continue
        description = " ".join(paragraph.split())
        if len(description) > 240:
            description = description[:237] + "..."
        return [
            ExtractedEvent(
                document_id=document_id,
                occurred_at=occurred_at,
                description=description,
                entity_ids=involved,
                trigger=match.group(0).lower(),
                trigger_start=start + match.start(),
            )
        ]
    return []
