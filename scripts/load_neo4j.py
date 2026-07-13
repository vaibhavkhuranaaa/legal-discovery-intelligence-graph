"""Extract the corpus and load the relationship graph into Neo4j AuraDB.

Reads data/raw/ and data/processed/chunks.jsonl (regenerate first with
bootstrap_data.py), runs the extraction pipeline (never gold labels), builds
the graph payload with chunk-level provenance, replaces the AuraDB graph,
and populates the Supabase entity_mentions provenance table with the same
shared IDs. Requires NEO4J_* and DATABASE_URL.

Usage:
    uv run python scripts/load_neo4j.py [--data-dir PATH]
"""

import argparse
import sys
from pathlib import Path

from legal_discovery_graph.config import get_settings
from legal_discovery_graph.extraction.extractor import extract_corpus
from legal_discovery_graph.graph import Neo4jGraphStore, build_graph_payload
from legal_discovery_graph.ingestion.pipeline import load_raw_record
from legal_discovery_graph.models import Chunk
from legal_discovery_graph.retrieval import PgVectorStore


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    args = parser.parse_args()

    raw_dir = args.data_dir / "raw"
    chunks_path = args.data_dir / "processed" / "chunks.jsonl"
    if not raw_dir.is_dir() or not chunks_path.is_file():
        print("corpus not found — run `uv run python scripts/bootstrap_data.py` first")
        return 1

    records = [
        load_raw_record(path)
        for path in sorted(raw_dir.glob("*.json"))
        if path.name != "manifest.json"
    ]
    chunks = [
        Chunk.model_validate_json(line)
        for line in chunks_path.read_text(encoding="utf-8").splitlines()
    ]

    print(f"extracting entities/events from {len(records)} documents ...")
    extraction = extract_corpus(records)
    payload, entity_mentions = build_graph_payload(records, extraction, chunks)
    print(
        f"payload: {len(payload.documents)} documents, {len(payload.entities)} entities, "
        f"{len(payload.events)} events, {len(payload.mention_edges)} mention edges, "
        f"{len(payload.participant_edges)} participant edges"
    )

    settings = get_settings()
    with Neo4jGraphStore(
        settings.neo4j_uri, settings.neo4j_username, settings.neo4j_password
    ) as graph:
        graph.verify_connectivity()
        graph.apply_constraints()
        graph.replace_graph(payload)
        counts = graph.graph_counts()
    print(
        f"neo4j: {counts['nodes']} nodes, {counts['relationships']} relationships "
        f"({counts['documents']} documents, {counts['events']} events, "
        f"{counts['mention_edges']} mention edges) — from database"
    )
    if counts["documents"] != len(payload.documents):
        print(f"MISMATCH: expected {len(payload.documents)} documents in graph")
        return 1

    store = PgVectorStore(settings.database_url)
    store.replace_entity_mentions(entity_mentions)
    stored = store.corpus_counts()["entity_mentions"]
    print(f"postgres entity_mentions: {stored} rows — from database")
    if stored != len(entity_mentions):
        print(f"MISMATCH: expected {len(entity_mentions)} entity_mentions rows")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
