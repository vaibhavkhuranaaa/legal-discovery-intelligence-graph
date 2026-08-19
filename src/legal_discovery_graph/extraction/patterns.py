"""Deterministic regex extraction lane.

Rule-shaped entity types (money, dates, project codenames) are extracted with
regular expressions rather than statistical NER: the pattern *is* the
definition, results are exactly reproducible, and this lane takes precedence
over the NER lane on span overlap (see extractor.py).
"""

import re
from dataclasses import dataclass

from legal_discovery_graph.models import EntityType

_MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"

MONEY_RE = re.compile(r"\$\d{1,3}(?:,\d{3})*(?:\.\d{2})?")
DATE_RE = re.compile(rf"(?:{_MONTHS}) \d{{1,2}}, \d{{4}}")
PROJECT_RE = re.compile(r"Project [A-Z][A-Za-z]+")

_PATTERNS: list[tuple[EntityType, re.Pattern[str]]] = [
    (EntityType.MONEY, MONEY_RE),
    (EntityType.DATE, DATE_RE),
    (EntityType.PROJECT, PROJECT_RE),
]


@dataclass(frozen=True)
class RawSpan:
    """A typed extraction span with document-level character offsets."""

    entity_type: EntityType
    surface: str
    start: int
    end: int


def extract_pattern_spans(text: str) -> list[RawSpan]:
    """Return all regex-lane spans in `text`, sorted by position."""
    spans = [
        RawSpan(
            entity_type=entity_type,
            surface=match.group(0),
            start=match.start(),
            end=match.end(),
        )
        for entity_type, pattern in _PATTERNS
        for match in pattern.finditer(text)
    ]
    return sorted(spans, key=lambda span: (span.start, span.end))
