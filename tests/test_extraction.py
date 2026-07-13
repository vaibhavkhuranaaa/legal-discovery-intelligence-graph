"""Extraction-lane, resolution, and event tests (Milestone 2)."""

from datetime import UTC, datetime
from pathlib import Path

from legal_discovery_graph.extraction.events import extract_events
from legal_discovery_graph.extraction.extractor import extract_document_spans
from legal_discovery_graph.extraction.patterns import extract_pattern_spans
from legal_discovery_graph.extraction.resolution import resolve_mentions
from legal_discovery_graph.models import EntityType

EXTRACTION_SRC = Path(__file__).parent.parent / "src" / "legal_discovery_graph" / "extraction"


def test_no_gold_leakage_in_extraction_sources() -> None:
    """The extractor must never consult the generator or the gold labels.

    Using the generated catalog as a gazetteer would fake the metrics; this
    guard fails if extraction code imports datagen or opens gold-label paths.
    """
    import ast

    for path in EXTRACTION_SRC.glob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                assert "data/labels" not in node.value, f"{path.name} references gold labels"
                continue
            else:
                continue
            for name in names:
                assert "datagen" not in name, f"{path.name} imports {name}"


def test_pattern_spans_offsets_and_types() -> None:
    text = "Northgate wired $45,000 on June 18, 2023 for Project Falcon."
    spans = extract_pattern_spans(text)
    found = {(s.entity_type, s.surface) for s in spans}
    assert (EntityType.MONEY, "$45,000") in found
    assert (EntityType.DATE, "June 18, 2023") in found
    assert (EntityType.PROJECT, "Project Falcon") in found
    for span in spans:
        assert text[span.start : span.end] == span.surface


def test_regex_lane_wins_on_overlap() -> None:
    text = "The award for Project Falcon totals $2,400,000, payable to Olivia Tran."
    spans = extract_document_spans(text)
    projects = [s for s in spans if text[s.start : s.end] == "Project Falcon"]
    assert len(projects) == 1
    assert projects[0].entity_type is EntityType.PROJECT  # regex type, not a NER guess
    # No two spans overlap after the merge for the regex-owned region.
    money = [s for s in spans if s.entity_type is EntityType.MONEY]
    assert [m.surface for m in money] == ["$2,400,000"]


def test_person_resolution_folds_short_forms() -> None:
    from legal_discovery_graph.extraction.patterns import RawSpan

    def person(surface: str, start: int) -> tuple[str, RawSpan]:
        return (
            "d1",
            RawSpan(
                entity_type=EntityType.PERSON,
                surface=surface,
                start=start,
                end=start + len(surface),
            ),
        )

    entities, mentions = resolve_mentions(
        [
            person("Olivia Tran", 0),
            person("O. Tran", 50),
            person("Olivia", 100),
            person("Reyes", 150),
            person("Daniel Reyes", 200),
        ]
    )
    by_name = {e.name: e for e in entities}
    assert set(by_name) == {"Olivia Tran", "Daniel Reyes"}
    tran_id = by_name["Olivia Tran"].entity_id
    tran_surfaces = {m.surface for m in mentions if m.entity_id == tran_id}
    assert tran_surfaces == {"Olivia Tran", "O. Tran", "Olivia"}
    assert by_name["Olivia Tran"].aliases == ["O. Tran", "Olivia"]
    reyes_id = by_name["Daniel Reyes"].entity_id
    assert {m.surface for m in mentions if m.entity_id == reyes_id} == {"Reyes", "Daniel Reyes"}


def test_org_resolution_unique_prefix_fold_only() -> None:
    from legal_discovery_graph.extraction.patterns import RawSpan

    def org(surface: str, start: int) -> tuple[str, RawSpan]:
        return (
            "d1",
            RawSpan(
                entity_type=EntityType.ORGANIZATION,
                surface=surface,
                start=start,
                end=start + len(surface),
            ),
        )

    entities, mentions = resolve_mentions(
        [
            org("Northgate Supply Solutions", 0),
            org("Northgate", 100),
            org("Apex Components Inc.", 200),
            org("Apex Ridge Partners", 300),  # makes "Apex" ambiguous
            org("Apex", 400),
        ]
    )
    by_name = {e.name for e in entities}
    assert "Northgate Supply Solutions" in by_name
    assert "Northgate" not in by_name  # folded into the full name
    assert "Apex" in by_name  # ambiguous prefix stays its own entity


def test_money_and_date_canonicalization() -> None:
    spans = [
        (doc, span)
        for doc in ("d1", "d2")
        for span in extract_pattern_spans("Paid $45,000 on June 18, 2023.")
    ]
    entities, _ = resolve_mentions(spans)
    names = sorted(e.name for e in entities)
    assert names == ["$45,000", "2023-06-18"]  # one entity each across documents


def test_event_extraction_trigger_and_header_exclusion() -> None:
    body = (
        "From: A Person <a@x.example>\nTo: B Person <b@x.example>\n"
        "Date: June 18, 2023\nSubject: transfers\n\n"
        "Funds of $45,000 were wired to the account as agreed."
    )
    spans = extract_document_spans(body)
    _, mentions = resolve_mentions([("d9", s) for s in spans])
    events = extract_events("d9", body, [m for m in mentions if m.document_id == "d9"])
    assert len(events) == 1
    event = events[0]
    assert event.trigger == "wired"
    assert event.occurred_at == datetime(2023, 6, 18, tzinfo=UTC)
    assert "wired" in event.description


def test_no_event_without_trigger_or_date() -> None:
    body = "Date: June 18, 2023\n\nA routine note about the holiday calendar."
    spans = extract_document_spans(body)
    _, mentions = resolve_mentions([("d9", s) for s in spans])
    assert extract_events("d9", body, mentions) == []

    body_no_date = "Funds were wired to the account as agreed."
    spans = extract_document_spans(body_no_date)
    _, mentions = resolve_mentions([("d8", s) for s in spans])
    assert extract_events("d8", body_no_date, mentions) == []
