"""Milestone 1 exit-criteria tests: deterministic generation and exact gold labels."""

import json
from pathlib import Path

import pytest

from legal_discovery_graph.datagen.bootstrap import BootstrapResult, run_bootstrap
from legal_discovery_graph.models import DocumentType

SEED = 7


@pytest.fixture(scope="module")
def result(tmp_path_factory: pytest.TempPathFactory) -> tuple[BootstrapResult, Path]:
    data_dir = tmp_path_factory.mktemp("corpus")
    return run_bootstrap(seed=SEED, data_dir=data_dir), data_dir


def _snapshot(data_dir: Path) -> dict[str, bytes]:
    return {
        str(path.relative_to(data_dir)): path.read_bytes()
        for path in sorted(data_dir.rglob("*"))
        if path.is_file()
    }


def test_same_seed_is_byte_identical(tmp_path_factory: pytest.TempPathFactory) -> None:
    dir_a = tmp_path_factory.mktemp("run_a")
    dir_b = tmp_path_factory.mktemp("run_b")
    run_bootstrap(seed=SEED, data_dir=dir_a)
    run_bootstrap(seed=SEED, data_dir=dir_b)
    assert _snapshot(dir_a) == _snapshot(dir_b)


def test_different_seed_changes_output(
    result: tuple[BootstrapResult, Path], tmp_path_factory: pytest.TempPathFactory
) -> None:
    other_dir = tmp_path_factory.mktemp("run_other")
    run_bootstrap(seed=SEED + 1, data_dir=other_dir)
    _, data_dir = result
    assert _snapshot(data_dir) != _snapshot(other_dir)


def test_corpus_size_and_types(result: tuple[BootstrapResult, Path]) -> None:
    bootstrap, _ = result
    documents = [document for document, _ in bootstrap.bundle.documents]
    assert 400 <= len(documents) <= 550
    present_types = {document.doc_type for document in documents}
    # The synthetic generator produces exactly these types; DocumentType may
    # grow additional members for real-file ingestion (e.g. OTHER).
    assert present_types == {
        DocumentType.EMAIL,
        DocumentType.CONTRACT,
        DocumentType.MEMO,
        DocumentType.INVOICE,
        DocumentType.MEETING_NOTES,
    }


def test_privilege_pii_gold_covers_every_document(result: tuple[BootstrapResult, Path]) -> None:
    bootstrap, data_dir = result
    gold = json.loads((data_dir / "labels" / "privilege_pii.json").read_text(encoding="utf-8"))
    assert gold["counsel_domains"]  # detector configuration ships with the labels
    document_ids = {document.document_id for document, _ in bootstrap.bundle.documents}
    assert set(gold["documents"]) == document_ids  # a label (mostly negative) for every doc
    privileged = [d for d in gold["documents"].values() if d["privileged"]]
    with_pii = [d for d in gold["documents"].values() if d["pii_types"]]
    assert len(privileged) >= 3
    assert len(with_pii) >= 2


def test_mention_offsets_match_document_text(result: tuple[BootstrapResult, Path]) -> None:
    bootstrap, _ = result
    bodies = {document.document_id: draft.body for document, draft in bootstrap.bundle.documents}
    assert bootstrap.mentions
    for mention in bootstrap.mentions:
        body = bodies[mention.document_id]
        assert body[mention.start_char : mention.end_char] == mention.surface_text


def test_mentions_resolve_to_covering_chunk(result: tuple[BootstrapResult, Path]) -> None:
    bootstrap, _ = result
    chunks = {chunk.chunk_id: chunk for chunk in bootstrap.ingestion.chunks}
    for mention in bootstrap.mentions:
        chunk = chunks[mention.chunk_id]
        assert chunk.document_id == mention.document_id
        start = int(chunk.metadata["start_char"])
        end = int(chunk.metadata["end_char"])
        assert start <= mention.start_char < end
        assert mention.surface_text in chunk.text


def test_retrieval_labels_reference_real_chunks(result: tuple[BootstrapResult, Path]) -> None:
    bootstrap, _ = result
    chunk_ids = {chunk.chunk_id for chunk in bootstrap.ingestion.chunks}
    chunk_by_id = {chunk.chunk_id: chunk for chunk in bootstrap.ingestion.chunks}
    assert len(bootstrap.retrieval_labels) >= 30
    for label in bootstrap.retrieval_labels:
        assert label["question"].strip()
        if label["category"] == "negative":
            assert not label["is_answerable"]
            assert label["relevant_chunk_ids"] == []
            assert label["relevant_document_ids"] == []
            continue
        assert label["is_answerable"]
        assert label["relevant_chunk_ids"]
        assert set(label["relevant_chunk_ids"]) <= chunk_ids
        matched = [
            snippet
            for snippet in label["evidence_snippets"]
            if any(snippet in chunk_by_id[cid].text for cid in label["relevant_chunk_ids"])
        ]
        assert matched == label["evidence_snippets"]


def test_query_set_is_balanced_with_negatives(result: tuple[BootstrapResult, Path]) -> None:
    bootstrap, _ = result
    counts: dict[str, int] = {}
    for label in bootstrap.retrieval_labels:
        counts[label["category"]] = counts.get(label["category"], 0) + 1
    for category in ("entity", "relationship", "event", "document", "financial"):
        assert counts.get(category, 0) >= 5, f"category {category!r} underrepresented: {counts}"
    assert counts.get("negative", 0) >= 3


def test_gold_mentions_are_complete_for_catalog_surfaces(
    result: tuple[BootstrapResult, Path],
) -> None:
    """Every occurrence of a canonical entity name or alias in any document body
    must be covered by a gold mention span of that same entity (exact offsets,
    not substring presence)."""
    bootstrap, _ = result
    surface_owners: dict[str, set[str]] = {}
    for entity in bootstrap.entities:
        for surface in (entity.name, *entity.aliases):
            surface_owners.setdefault(surface, set()).add(entity.entity_id)

    spans_by_doc: dict[str, list[tuple[int, int, str]]] = {}
    for mention in bootstrap.mentions:
        spans_by_doc.setdefault(mention.document_id, []).append(
            (mention.start_char, mention.end_char, mention.entity_id)
        )

    checked = 0
    for document, draft in bootstrap.bundle.documents:
        spans = spans_by_doc.get(document.document_id, [])
        for surface, owners in surface_owners.items():
            start = draft.body.find(surface)
            while start != -1:
                end = start + len(surface)
                covered = any(
                    span_start <= start
                    and end <= span_end
                    and (
                        entity_id in owners
                        # A different entity's strictly larger span may contain
                        # this surface (e.g. "Nevada" inside "Reno, Nevada").
                        or (span_end - span_start) > (end - start)
                    )
                    for span_start, span_end, entity_id in spans
                )
                assert covered, (
                    f"unlabeled occurrence of {surface!r} at offset {start} "
                    f"in document {document.title!r}"
                )
                checked += 1
                start = draft.body.find(surface, start + 1)
    # Guard against a silently empty scan (e.g. a broken catalog): the corpus
    # has hundreds of canonical-surface occurrences.
    assert checked >= 400


def test_events_reference_known_documents_and_entities(
    result: tuple[BootstrapResult, Path],
) -> None:
    bootstrap, _ = result
    document_ids = {document.document_id for document, _ in bootstrap.bundle.documents}
    entity_ids = {entity.entity_id for entity in bootstrap.entities}
    assert len(bootstrap.events) >= 10
    for event in bootstrap.events:
        assert event.document_id in document_ids
        assert event.entity_ids
        assert set(event.entity_ids) <= entity_ids
        assert event.occurred_at.year == 2023


def test_written_files_are_complete(result: tuple[BootstrapResult, Path]) -> None:
    bootstrap, data_dir = result
    raw_files = [p for p in (data_dir / "raw").glob("*.json") if p.name != "manifest.json"]
    assert len(raw_files) == len(bootstrap.bundle.documents)

    manifest = json.loads((data_dir / "raw" / "manifest.json").read_text())
    assert manifest["seed"] == SEED
    assert manifest["documents"] == len(bootstrap.bundle.documents)

    chunk_lines = (data_dir / "processed" / "chunks.jsonl").read_text().splitlines()
    assert len(chunk_lines) == len(bootstrap.ingestion.chunks)

    for name in ("entities.json", "mentions.jsonl", "events.jsonl", "retrieval.jsonl"):
        assert (data_dir / "labels" / name).stat().st_size > 0
