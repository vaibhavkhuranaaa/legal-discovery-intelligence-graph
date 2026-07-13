"""Statistical NER lane (spaCy `en_core_web_sm`, pinned in pyproject.toml).

Handles the name-shaped types: PERSON, ORGANIZATION, LOCATION. Money and date
spans from the model are deliberately discarded — the regex lane owns those
types (patterns.py). The model is loaded once per process.

Integrity rule: extraction must never consult the corpus generator or the
gold label files — doing so would inflate evaluation metrics. Enforced by
tests/test_extraction.py.
"""

import re
from functools import lru_cache

from legal_discovery_graph.extraction.patterns import RawSpan
from legal_discovery_graph.models import EntityType

_LABEL_MAP = {
    "PERSON": EntityType.PERSON,
    "ORG": EntityType.ORGANIZATION,
    "GPE": EntityType.LOCATION,
    "LOC": EntityType.LOCATION,
}


@lru_cache(maxsize=1)
def _nlp():
    import spacy

    # Only the NER component is needed; disabling the rest keeps runs fast.
    return spacy.load("en_core_web_sm", disable=["tagger", "parser", "lemmatizer"])


_IDENTIFIER_RE = re.compile(r"^[A-Z]+-\d+$")  # document identifiers, e.g. RFP-2023


def _coalesce_locations(spans: list[RawSpan], text: str) -> list[RawSpan]:
    """Merge adjacent location spans separated by ", " (Denver + Colorado →
    "Denver, Colorado") — comma-joined place names are one location."""
    merged: list[RawSpan] = []
    for span in spans:
        previous = merged[-1] if merged else None
        if (
            previous is not None
            and previous.entity_type is EntityType.LOCATION
            and span.entity_type is EntityType.LOCATION
            and text[previous.end : span.start] == ", "
        ):
            merged[-1] = RawSpan(
                entity_type=EntityType.LOCATION,
                surface=text[previous.start : span.end],
                start=previous.start,
                end=span.end,
            )
        else:
            merged.append(span)
    return merged


def extract_ner_spans(text: str) -> list[RawSpan]:
    """Return PERSON/ORGANIZATION/LOCATION spans predicted by spaCy.

    NER runs per paragraph (paragraphs are the semantic units of these
    documents; a span must never cross a paragraph boundary), spans containing
    line breaks or shaped like document identifiers are rejected, and
    comma-adjacent location spans are coalesced.
    """
    spans: list[RawSpan] = []
    cursor = 0
    for paragraph in text.split("\n\n"):
        if paragraph.strip():
            doc = _nlp()(paragraph)
            for ent in doc.ents:
                if (
                    ent.label_ in _LABEL_MAP
                    and "\n" not in ent.text
                    and not _IDENTIFIER_RE.match(ent.text)
                ):
                    spans.append(
                        RawSpan(
                            entity_type=_LABEL_MAP[ent.label_],
                            surface=ent.text,
                            start=cursor + ent.start_char,
                            end=cursor + ent.end_char,
                        )
                    )
        cursor += len(paragraph) + 2
    spans.sort(key=lambda span: (span.start, span.end))
    return _coalesce_locations(spans, text)
