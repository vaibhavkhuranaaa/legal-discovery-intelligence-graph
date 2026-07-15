"""Shared helpers for file-format readers (not part of the public API)."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from legal_discovery_graph.ids import stable_id

_COLLAPSE_NEWLINES = re.compile(r"\n{3,}")


def file_document_id(path: Path) -> str:
    """Return a deterministic document ID derived from the file's raw bytes."""
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    return stable_id("ingested", digest)


def normalize_paragraphs(paragraphs: list[str]) -> str:
    """Join non-empty paragraphs with blank lines, stripping trailing whitespace per line.

    Runs of 3+ consecutive newlines are collapsed to exactly two.
    """
    cleaned: list[str] = []
    for paragraph in paragraphs:
        if not paragraph:
            continue
        lines = [line.rstrip() for line in paragraph.strip("\n").splitlines()]
        text = "\n".join(lines).strip()
        if text:
            cleaned.append(text)
    body = "\n\n".join(cleaned)
    body = _COLLAPSE_NEWLINES.sub("\n\n", body)
    return body.strip()
