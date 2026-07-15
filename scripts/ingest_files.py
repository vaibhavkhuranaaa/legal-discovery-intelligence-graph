"""Ingest real discovery files (PDF/DOCX/EML) into the corpus pipeline.

Walks a source folder, extracts text with the format readers, deduplicates by
SHA-256 content hash, assigns sequential Bates-style control numbers, and
writes raw JSON records to ``data/raw/`` in the exact shape the existing
pipeline consumes — after ingestion, ``index_pgvector.py`` and
``load_neo4j.py`` work unchanged over the combined corpus. Every file
(ingested, duplicate, or failed) is appended to the chain-of-custody manifest
``data/manifest.jsonl``.

Runs fully offline; nothing is uploaded anywhere by this script.

Usage:
    uv run python scripts/ingest_files.py --src <dir> --custodian <name> \
        [--matter PREFIX] [--data-dir data]
"""

import argparse
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

from legal_discovery_graph.ingestion.readers import read_docx, read_eml, read_pdf

READERS = {".pdf": read_pdf, ".docx": read_docx, ".eml": read_eml}
MANIFEST_NAME = "manifest.jsonl"


def _load_seen(manifest_path: Path, matter: str) -> tuple[dict[str, str], int]:
    """Return (sha256 → bates_id) already ingested and the next Bates sequence."""
    seen: dict[str, str] = {}
    next_seq = 1
    if not manifest_path.is_file():
        return seen, next_seq
    prefix = f"{matter}-"
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if row["status"] == "ingested":
            seen[row["sha256"]] = row["bates_id"]
            if row["bates_id"].startswith(prefix):
                next_seq = max(next_seq, int(row["bates_id"].removeprefix(prefix)) + 1)
    return seen, next_seq


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--src", type=Path, required=True, help="folder of PDF/DOCX/EML files")
    parser.add_argument("--custodian", required=True, help="custodian name for these files")
    parser.add_argument("--matter", default="DOC", help="Bates prefix (default: DOC)")
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    args = parser.parse_args()

    if not args.src.is_dir():
        print(f"source folder not found: {args.src}")
        return 1

    raw_dir = args.data_dir / "raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = args.data_dir / MANIFEST_NAME
    seen, next_seq = _load_seen(manifest_path, args.matter)

    files = sorted(p for p in args.src.rglob("*") if p.suffix.lower() in READERS)
    if not files:
        print(f"no {'/'.join(sorted(READERS))} files under {args.src}")
        return 1

    counts = {"ingested": 0, "duplicate": 0, "failed": 0}
    with manifest_path.open("a", encoding="utf-8") as manifest:

        def record(row: dict) -> None:
            manifest.write(json.dumps(row, sort_keys=True) + "\n")
            counts[row["status"]] += 1

        for path in files:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            base = {
                "path": str(path),
                "sha256": digest,
                "custodian": args.custodian,
                "ingested_at": datetime.now(UTC).isoformat(),
            }
            if digest in seen:
                record({**base, "status": "duplicate", "bates_id": seen[digest]})
                continue
            try:
                document, body = READERS[path.suffix.lower()](path, custodian=args.custodian)
            except ValueError as error:
                record({**base, "status": "failed", "bates_id": None, "error": str(error)})
                continue
            bates_id = f"{args.matter}-{next_seq:06d}"
            next_seq += 1
            seen[digest] = bates_id
            out_path = raw_dir / f"{bates_id}.json"
            out_path.write_text(
                json.dumps(
                    {"document": document.model_dump(mode="json"), "body": body},
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )
            record(
                {
                    **base,
                    "status": "ingested",
                    "bates_id": bates_id,
                    "document_id": document.document_id,
                    "raw_record": str(out_path),
                }
            )

    print(
        f"ingested {counts['ingested']} files, {counts['duplicate']} duplicates, "
        f"{counts['failed']} failed — manifest: {manifest_path}"
    )
    print("next: uv run python scripts/index_pgvector.py && uv run python scripts/load_neo4j.py")
    return 0 if counts["failed"] == 0 else 2


if __name__ == "__main__":
    sys.exit(main())
