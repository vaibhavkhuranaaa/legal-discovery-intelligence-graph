"""Chunker and ingestion-pipeline tests."""

import json
from datetime import UTC, datetime
from pathlib import Path

from legal_discovery_graph.ingestion.chunker import chunk_document
from legal_discovery_graph.ingestion.pipeline import process_raw_dir
from legal_discovery_graph.models import Document, DocumentType


def _doc() -> Document:
    return Document(
        document_id="d" * 32,
        doc_type=DocumentType.MEMO,
        title="Test memo",
        sent_at=datetime(2023, 5, 1, tzinfo=UTC),
    )


def test_chunks_are_exact_body_slices() -> None:
    body = "Header line\n\n" + "\n\n".join(f"Paragraph {i} " + "x" * 200 for i in range(8))
    chunks = chunk_document(_doc(), body, max_chars=500)
    assert len(chunks) > 1
    for chunk in chunks:
        start = int(chunk.metadata["start_char"])
        end = int(chunk.metadata["end_char"])
        assert chunk.text == body[start:end]
    # Every paragraph's content is preserved across the chunk set, in order.
    reassembled = "\n\n".join(chunk.text for chunk in chunks)
    assert reassembled == body


def test_chunk_size_respected_except_single_long_paragraph() -> None:
    body = "short one\n\n" + "y" * 1200 + "\n\nshort two"
    chunks = chunk_document(_doc(), body, max_chars=300)
    lengths = [len(chunk.text) for chunk in chunks]
    assert lengths == [9, 1200, 9]  # long paragraph is its own chunk, never split


def test_chunk_ids_are_deterministic_and_sequenced() -> None:
    body = "a\n\nb\n\nc"
    first = chunk_document(_doc(), body, max_chars=1)
    second = chunk_document(_doc(), body, max_chars=1)
    assert [c.chunk_id for c in first] == [c.chunk_id for c in second]
    assert [c.sequence for c in first] == list(range(len(first)))


def test_pipeline_quarantines_bad_files_and_continues(tmp_path: Path) -> None:
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()
    good = {
        "document": _doc().model_dump(mode="json"),
        "body": "First paragraph.\n\nSecond paragraph.",
    }
    (raw_dir / "000_memo.json").write_text(json.dumps(good))
    (raw_dir / "001_memo.json").write_text("{not valid json")

    report = process_raw_dir(raw_dir, tmp_path / "processed", tmp_path / "failed")

    assert report.processed_documents == 1
    assert report.failed_documents == 1
    assert len(report.chunks) >= 1
    failures = list((tmp_path / "failed").glob("*.error.json"))
    assert len(failures) == 1
    error_record = json.loads(failures[0].read_text())
    assert error_record["file"] == "001_memo.json"
    chunk_lines = (tmp_path / "processed" / "chunks.jsonl").read_text().splitlines()
    assert len(chunk_lines) == len(report.chunks)
