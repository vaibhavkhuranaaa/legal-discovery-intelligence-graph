"""End-to-end corpus bootstrap: generate → write raw → ingest → resolve labels.

Single deterministic pass per seed:

1. Generate the corpus in memory (`generator.generate_corpus`).
2. Write one raw JSON record per document to `data/raw/` plus a manifest.
3. Run the real ingestion pipeline over the written files (exercising the
   same path any re-processing would take) to produce `data/processed/`.
4. Resolve gold labels against the produced chunks — entity mentions get the
   chunk that covers their character span; retrieval queries get the chunk(s)
   containing their planted evidence snippets — and write `data/labels/`.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from legal_discovery_graph.datagen.generator import CorpusBundle, generate_corpus
from legal_discovery_graph.datagen.scenario import COUNSEL_DOMAINS
from legal_discovery_graph.ids import stable_id
from legal_discovery_graph.ingestion.pipeline import IngestionReport, process_raw_dir
from legal_discovery_graph.models import Chunk, Entity, EntityMention, Event

GENERATOR_VERSION = "3"  # v3: privileged/PII planted documents and gold flags; 10 negative queries


@dataclass
class BootstrapResult:
    """Everything written by one bootstrap run, for reporting and tests."""

    bundle: CorpusBundle
    ingestion: IngestionReport
    entities: list[Entity]
    mentions: list[EntityMention]
    events: list[Event]
    retrieval_labels: list[dict]


def _dump(obj: dict, path: Path) -> None:
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _dump_jsonl(rows: list[dict], path: Path) -> None:
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")


def _write_raw(bundle: CorpusBundle, raw_dir: Path) -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    by_type: dict[str, int] = {}
    for index, (document, draft) in enumerate(bundle.documents):
        by_type[document.doc_type.value] = by_type.get(document.doc_type.value, 0) + 1
        record = {"document": document.model_dump(mode="json"), "body": draft.body}
        _dump(record, raw_dir / f"{index:03d}_{document.doc_type.value}.json")
    manifest = {
        "seed": bundle.seed,
        "generator_version": GENERATOR_VERSION,
        "documents": len(bundle.documents),
        "documents_by_type": by_type,
        "queries": len(bundle.queries),
        "note": "Entirely synthetic corpus; all names, companies, and events are fictional.",
    }
    _dump(manifest, raw_dir / "manifest.json")


def _chunk_covering(chunks: list[Chunk], document_id: str, offset: int) -> Chunk:
    for chunk in chunks:
        if chunk.document_id != document_id:
            continue
        if int(chunk.metadata["start_char"]) <= offset < int(chunk.metadata["end_char"]):
            return chunk
    raise ValueError(f"no chunk covers offset {offset} of document {document_id}")


def _resolve_labels(
    bundle: CorpusBundle, chunks: list[Chunk]
) -> tuple[list[Entity], list[EntityMention], list[Event], list[dict]]:
    entities: dict[str, Entity] = {}
    mentions: list[EntityMention] = []
    events: list[Event] = []

    for document, draft in bundle.documents:
        for span in draft.mentions:
            entities[span.entity.entity_id] = span.entity
            chunk = _chunk_covering(chunks, document.document_id, span.start)
            mentions.append(
                EntityMention(
                    entity_id=span.entity.entity_id,
                    chunk_id=chunk.chunk_id,
                    document_id=document.document_id,
                    surface_text=span.surface,
                    start_char=span.start,
                    end_char=span.end,
                )
            )
        for event_index, draft_event in enumerate(draft.events):
            events.append(
                Event(
                    event_id=stable_id("event", document.document_id, event_index),
                    document_id=document.document_id,
                    occurred_at=draft_event.occurred_at,
                    description=draft_event.description,
                    entity_ids=[entity.entity_id for entity in draft_event.entities],
                )
            )

    doc_ids = {id(draft): document.document_id for document, draft in bundle.documents}
    retrieval_labels: list[dict] = []
    for query_index, query in enumerate(bundle.queries):
        relevant_chunks: list[str] = []
        relevant_docs: list[str] = []
        snippets: list[str] = []
        for draft, snippet in query.evidence:
            document_id = doc_ids[id(draft)]
            matches = [
                chunk.chunk_id
                for chunk in chunks
                if chunk.document_id == document_id and snippet in chunk.text
            ]
            if not matches:
                raise ValueError(f"evidence snippet not found in any chunk: {snippet!r}")
            relevant_docs.append(document_id)
            relevant_chunks.extend(matches)
            snippets.append(snippet)
        retrieval_labels.append(
            {
                "query_id": stable_id("query", bundle.seed, query_index),
                "question": query.question,
                "category": query.category,
                "is_answerable": bool(relevant_chunks),
                "relevant_document_ids": sorted(set(relevant_docs)),
                "relevant_chunk_ids": sorted(set(relevant_chunks)),
                "evidence_snippets": snippets,
            }
        )

    entity_list = sorted(entities.values(), key=lambda entity: entity.entity_id)
    return entity_list, mentions, events, retrieval_labels


def _write_labels(
    labels_dir: Path,
    entities: list[Entity],
    mentions: list[EntityMention],
    events: list[Event],
    retrieval_labels: list[dict],
) -> None:
    labels_dir.mkdir(parents=True, exist_ok=True)
    _dump(
        {"entities": [entity.model_dump(mode="json") for entity in entities]},
        labels_dir / "entities.json",
    )
    _dump_jsonl([m.model_dump(mode="json") for m in mentions], labels_dir / "mentions.jsonl")
    _dump_jsonl([e.model_dump(mode="json") for e in events], labels_dir / "events.jsonl")
    _dump_jsonl(retrieval_labels, labels_dir / "retrieval.jsonl")


def _write_privilege_labels(labels_dir: Path, bundle: CorpusBundle) -> None:
    """Gold privilege/PII flags for every document (mostly negatives)."""
    _dump(
        {
            "counsel_domains": list(COUNSEL_DOMAINS),
            "documents": {
                document.document_id: {
                    "privileged": draft.privileged,
                    "pii_types": sorted(draft.pii_types),
                }
                for document, draft in bundle.documents
            },
        },
        labels_dir / "privilege_pii.json",
    )


def run_bootstrap(seed: int, data_dir: Path) -> BootstrapResult:
    """Generate the corpus and all derived outputs under `data_dir`."""
    raw_dir = data_dir / "raw"
    processed_dir = data_dir / "processed"
    labels_dir = data_dir / "labels"
    failed_dir = data_dir / "failed"

    # A smaller regeneration must not leave stale files from a previous run:
    # leftover raw records share deterministic document_ids with new ones and
    # silently corrupt extraction/retrieval evaluation.
    for directory in (raw_dir, processed_dir, labels_dir, failed_dir):
        if directory.is_dir():
            for stale in directory.glob("*.json*"):
                stale.unlink()

    bundle = generate_corpus(seed)
    _write_raw(bundle, raw_dir)
    ingestion = process_raw_dir(raw_dir, processed_dir, failed_dir)
    if ingestion.failed_documents:
        raise RuntimeError(
            f"{ingestion.failed_documents} generated document(s) failed ingestion; see {failed_dir}"
        )
    entities, mentions, events, retrieval_labels = _resolve_labels(bundle, ingestion.chunks)
    _write_labels(labels_dir, entities, mentions, events, retrieval_labels)
    _write_privilege_labels(labels_dir, bundle)
    return BootstrapResult(
        bundle=bundle,
        ingestion=ingestion,
        entities=entities,
        mentions=mentions,
        events=events,
        retrieval_labels=retrieval_labels,
    )
