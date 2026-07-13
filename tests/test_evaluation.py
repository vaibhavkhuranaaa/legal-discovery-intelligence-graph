"""End-to-end extraction evaluation against the generated gold labels."""

import pytest

from legal_discovery_graph.datagen.bootstrap import run_bootstrap
from legal_discovery_graph.evaluation.extraction_eval import (
    load_gold_event_keys,
    load_gold_mentions,
    score_events,
    score_mentions,
)
from legal_discovery_graph.extraction.extractor import ExtractionResult, extract_corpus
from legal_discovery_graph.ingestion.pipeline import load_raw_record

SEED = 7

# Regression floors, set below the observed scores at the time of Milestone 2
# (see artifacts/extraction_metrics.json) so genuine regressions fail loudly
# while spaCy point-release drift does not.
RELAXED_MICRO_F1_FLOOR = 0.85
STRICT_MICRO_F1_FLOOR = 0.75
EVENT_F1_FLOOR = 0.90


@pytest.fixture(scope="module")
def evaluated(tmp_path_factory: pytest.TempPathFactory):
    data_dir = tmp_path_factory.mktemp("m2corpus")
    run_bootstrap(seed=SEED, data_dir=data_dir)
    records = [
        load_raw_record(path)
        for path in sorted((data_dir / "raw").glob("*.json"))
        if path.name != "manifest.json"
    ]
    result = extract_corpus(records)
    gold_mentions = load_gold_mentions(data_dir / "labels")
    gold_events = load_gold_event_keys(data_dir / "labels")
    return result, gold_mentions, gold_events


def test_extraction_is_deterministic(evaluated, tmp_path_factory) -> None:
    result: ExtractionResult = evaluated[0]
    data_dir = tmp_path_factory.mktemp("m2corpus_again")
    run_bootstrap(seed=SEED, data_dir=data_dir)
    records = [
        load_raw_record(path)
        for path in sorted((data_dir / "raw").glob("*.json"))
        if path.name != "manifest.json"
    ]
    again = extract_corpus(records)
    assert [e.entity_id for e in again.entities] == [e.entity_id for e in result.entities]
    assert again.mentions == result.mentions
    assert again.events == result.events


def test_mention_metrics_meet_floors(evaluated) -> None:
    result, gold_mentions, _ = evaluated
    relaxed = score_mentions(result.mentions, gold_mentions, strict=False)
    strict = score_mentions(result.mentions, gold_mentions, strict=True)
    assert relaxed["micro"].f1 >= RELAXED_MICRO_F1_FLOOR, relaxed["micro"].as_dict()
    assert strict["micro"].f1 >= STRICT_MICRO_F1_FLOOR, strict["micro"].as_dict()
    # Deterministic regex types must be near-perfect by construction.
    for type_name in ("money", "date", "project"):
        assert relaxed[type_name].f1 >= 0.99, (type_name, relaxed[type_name].as_dict())


def test_event_metrics_meet_floor(evaluated) -> None:
    result, _, gold_events = evaluated
    scores = score_events(result.events, gold_events)
    assert scores.f1 >= EVENT_F1_FLOOR, scores.as_dict()


def test_scoring_math_is_correct() -> None:
    from legal_discovery_graph.evaluation.extraction_eval import GoldMention, Scores
    from legal_discovery_graph.extraction.resolution import ResolvedMention
    from legal_discovery_graph.models import EntityType

    def pred(start: int, end: int) -> ResolvedMention:
        return ResolvedMention(
            document_id="d1",
            entity_type=EntityType.PERSON,
            surface="x",
            start=start,
            end=end,
            entity_id="e1",
            canonical_name="x",
        )

    gold = [
        GoldMention("d1", EntityType.PERSON, 0, 10),
        GoldMention("d1", EntityType.PERSON, 20, 30),
    ]
    # One exact hit, one overlap-only hit, one miss.
    predicted = [pred(0, 10), pred(25, 35), pred(50, 60)]
    strict = score_mentions(predicted, gold, strict=True)["micro"]
    relaxed = score_mentions(predicted, gold, strict=False)["micro"]
    assert (strict.true_positives, strict.predicted, strict.gold) == (1, 3, 2)
    assert (relaxed.true_positives, relaxed.predicted, relaxed.gold) == (2, 3, 2)
    assert Scores(2, 3, 2).f1 == pytest.approx(0.8)
