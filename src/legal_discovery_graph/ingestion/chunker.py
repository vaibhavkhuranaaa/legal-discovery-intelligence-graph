"""Deterministic paragraph-packing chunker.

Chunks are exact slices of the document body: paragraphs (split on blank
lines) are packed greedily up to `max_chars`, and each chunk's text is taken
as `body[start:end]`, so character offsets in chunk metadata map mentions and
evidence snippets back to the source text without any normalization drift.
"""

from dataclasses import dataclass

from legal_discovery_graph.ids import stable_id
from legal_discovery_graph.models import Chunk, Document

DEFAULT_MAX_CHARS = 900
_SEPARATOR = "\n\n"


@dataclass(frozen=True)
class _Paragraph:
    start: int
    end: int


def _paragraph_spans(body: str) -> list[_Paragraph]:
    spans: list[_Paragraph] = []
    cursor = 0
    for part in body.split(_SEPARATOR):
        if part.strip():
            spans.append(_Paragraph(start=cursor, end=cursor + len(part)))
        cursor += len(part) + len(_SEPARATOR)
    return spans


def chunk_document(
    document: Document, body: str, max_chars: int = DEFAULT_MAX_CHARS
) -> list[Chunk]:
    """Split `body` into ordered chunks with document-offset metadata.

    A paragraph longer than `max_chars` becomes its own chunk rather than
    being split mid-sentence; citation alignment matters more than a hard cap.
    """
    paragraphs = _paragraph_spans(body)
    chunks: list[Chunk] = []
    group_start: int | None = None
    group_end = 0

    def flush() -> None:
        nonlocal group_start
        if group_start is None:
            return
        sequence = len(chunks)
        chunks.append(
            Chunk(
                chunk_id=stable_id("chunk", document.document_id, sequence),
                document_id=document.document_id,
                sequence=sequence,
                text=body[group_start:group_end],
                metadata={
                    "title": document.title,
                    "doc_type": document.doc_type.value,
                    "start_char": str(group_start),
                    "end_char": str(group_end),
                },
            )
        )
        group_start = None

    for para in paragraphs:
        if group_start is not None and (para.end - group_start) > max_chars:
            flush()
        if group_start is None:
            group_start = para.start
        group_end = para.end
    flush()
    return chunks
