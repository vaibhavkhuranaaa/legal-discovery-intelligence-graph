"""Embed the processed corpus and load it into PostgreSQL + pgvector.

Reads data/raw/ (document metadata) and data/processed/chunks.jsonl
(regenerate first with bootstrap_data.py), embeds every chunk with the
configured sentence-transformers model, applies the docs/DATA_MODEL.md
schema, and atomically replaces the stored corpus. Requires DATABASE_URL.

Usage:
    uv run python scripts/index_pgvector.py [--data-dir PATH]
"""

import argparse
import json
import sys
from pathlib import Path

from legal_discovery_graph.config import get_settings
from legal_discovery_graph.ingestion.pipeline import load_raw_record
from legal_discovery_graph.models import Chunk
from legal_discovery_graph.retrieval import PgVectorStore, SentenceTransformerEmbedder


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    args = parser.parse_args()

    raw_dir = args.data_dir / "raw"
    chunks_path = args.data_dir / "processed" / "chunks.jsonl"
    if not raw_dir.is_dir() or not chunks_path.is_file():
        print("corpus not found — run `uv run python scripts/bootstrap_data.py` first")
        return 1

    settings = get_settings()
    if not settings.database_url:
        print("DATABASE_URL is not configured — see .env.example")
        return 1

    documents = [
        load_raw_record(path).document
        for path in sorted(raw_dir.glob("*.json"))
        if path.name != "manifest.json"
    ]
    chunks = [
        Chunk.model_validate_json(line)
        for line in chunks_path.read_text(encoding="utf-8").splitlines()
    ]

    print(f"embedding {len(chunks)} chunks with {settings.embedding_model_name} ...")
    embedder = SentenceTransformerEmbedder(settings.embedding_model_name)
    embeddings = embedder.embed_texts([chunk.text for chunk in chunks])

    store = PgVectorStore(settings.database_url)
    store.apply_schema()
    store.replace_corpus(documents, chunks, embeddings)

    counts = store.corpus_counts()
    print(f"indexed: {counts['documents']} documents, {counts['chunks']} chunks (from database)")
    if (counts["documents"], counts["chunks"]) != (len(documents), len(chunks)):
        print(f"MISMATCH: expected {len(documents)} documents, {len(chunks)} chunks")
        return 1

    manifest = json.loads((raw_dir / "manifest.json").read_text(encoding="utf-8"))
    print(f"corpus seed: {manifest['seed']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
