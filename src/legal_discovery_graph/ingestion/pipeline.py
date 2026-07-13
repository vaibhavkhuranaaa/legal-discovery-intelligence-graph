"""Raw-corpus ingestion: read raw document records, chunk, persist.

Reads `data/raw/*.json` records, chunks each body, and writes all chunks to
`processed_dir/chunks.jsonl`. A document that fails to parse is quarantined
as an error record in `failed_dir` and never aborts the batch.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path

from pydantic import BaseModel

from legal_discovery_graph.ingestion.chunker import chunk_document
from legal_discovery_graph.models import Chunk, Document

CHUNKS_FILENAME = "chunks.jsonl"


class RawDocumentRecord(BaseModel):
    """On-disk schema of one raw corpus file."""

    document: Document
    body: str


@dataclass
class IngestionReport:
    """Outcome of one ingestion run."""

    chunks: list[Chunk] = field(default_factory=list)
    processed_documents: int = 0
    failed_documents: int = 0


def load_raw_record(path: Path) -> RawDocumentRecord:
    return RawDocumentRecord.model_validate_json(path.read_text(encoding="utf-8"))


def process_raw_dir(raw_dir: Path, processed_dir: Path, failed_dir: Path) -> IngestionReport:
    """Chunk every raw record; quarantine failures; write chunks.jsonl."""
    report = IngestionReport()
    processed_dir.mkdir(parents=True, exist_ok=True)
    failed_dir.mkdir(parents=True, exist_ok=True)

    for path in sorted(raw_dir.glob("*.json")):
        if path.name == "manifest.json":
            continue
        try:
            record = load_raw_record(path)
            report.chunks.extend(chunk_document(record.document, record.body))
            report.processed_documents += 1
        except (ValueError, OSError) as exc:  # pydantic ValidationError is a ValueError
            report.failed_documents += 1
            failure = {"file": path.name, "error": f"{type(exc).__name__}: {exc}"}
            failed_path = failed_dir / f"{path.stem}.error.json"
            failed_path.write_text(
                json.dumps(failure, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )

    out_path = processed_dir / CHUNKS_FILENAME
    with out_path.open("w", encoding="utf-8") as handle:
        for chunk in report.chunks:
            handle.write(json.dumps(chunk.model_dump(mode="json"), sort_keys=True) + "\n")
    return report
