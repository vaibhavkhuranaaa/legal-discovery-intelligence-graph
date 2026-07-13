"""Extraction evaluation: predicted mentions/events vs gold labels.

Mention matching is one-to-one greedy within (document, entity type):
- **strict** — identical character span;
- **relaxed** — any character overlap.

Both are reported per entity type and micro-averaged. Events match on
(document, calendar date). Reading the gold labels is this module's job —
the *extractor* must never see them (enforced by tests).
"""

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from legal_discovery_graph.extraction.events import ExtractedEvent
from legal_discovery_graph.extraction.resolution import ResolvedMention
from legal_discovery_graph.models import EntityType


@dataclass(frozen=True)
class GoldMention:
    document_id: str
    entity_type: EntityType
    start: int
    end: int


@dataclass(frozen=True)
class Scores:
    true_positives: int
    predicted: int
    gold: int

    @property
    def precision(self) -> float:
        return self.true_positives / self.predicted if self.predicted else 0.0

    @property
    def recall(self) -> float:
        return self.true_positives / self.gold if self.gold else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p + r else 0.0

    def as_dict(self) -> dict:
        return {
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
            "true_positives": self.true_positives,
            "predicted": self.predicted,
            "gold": self.gold,
        }


def load_gold_mentions(labels_dir: Path) -> list[GoldMention]:
    catalog = json.loads((labels_dir / "entities.json").read_text(encoding="utf-8"))
    type_by_id = {e["entity_id"]: EntityType(e["entity_type"]) for e in catalog["entities"]}
    gold: list[GoldMention] = []
    for line in (labels_dir / "mentions.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        gold.append(
            GoldMention(
                document_id=row["document_id"],
                entity_type=type_by_id[row["entity_id"]],
                start=row["start_char"],
                end=row["end_char"],
            )
        )
    return gold


def load_gold_event_keys(labels_dir: Path) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for line in (labels_dir / "events.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        occurred = datetime.fromisoformat(row["occurred_at"]).date().isoformat()
        keys.add((row["document_id"], occurred))
    return keys


def _match_group(predicted: list[ResolvedMention], gold: list[GoldMention], strict: bool) -> int:
    """One-to-one greedy matching within one (document, type) group."""
    matched_gold: set[int] = set()
    true_positives = 0
    for pred in sorted(predicted, key=lambda m: (m.start, m.end)):
        for index, g in enumerate(gold):
            if index in matched_gold:
                continue
            hit = (
                (pred.start == g.start and pred.end == g.end)
                if strict
                else (pred.start < g.end and g.start < pred.end)
            )
            if hit:
                matched_gold.add(index)
                true_positives += 1
                break
    return true_positives


def score_mentions(
    predicted: list[ResolvedMention], gold: list[GoldMention], strict: bool
) -> dict[str, Scores]:
    """Per-entity-type scores plus a 'micro' aggregate."""
    groups: dict[tuple[str, EntityType], tuple[list, list]] = {}
    for pred in predicted:
        groups.setdefault((pred.document_id, pred.entity_type), ([], []))[0].append(pred)
    for g in gold:
        groups.setdefault((g.document_id, g.entity_type), ([], []))[1].append(g)

    per_type_tp: dict[EntityType, int] = dict.fromkeys(EntityType, 0)
    for (_, entity_type), (preds, golds) in groups.items():
        per_type_tp[entity_type] += _match_group(preds, golds, strict)

    pred_counts: dict[EntityType, int] = dict.fromkeys(EntityType, 0)
    gold_counts: dict[EntityType, int] = dict.fromkeys(EntityType, 0)
    for pred in predicted:
        pred_counts[pred.entity_type] += 1
    for g in gold:
        gold_counts[g.entity_type] += 1

    scores = {
        entity_type.value: Scores(
            per_type_tp[entity_type], pred_counts[entity_type], gold_counts[entity_type]
        )
        for entity_type in EntityType
    }
    scores["micro"] = Scores(sum(per_type_tp.values()), len(predicted), len(gold))
    return scores


def score_events(predicted: list[ExtractedEvent], gold_keys: set[tuple[str, str]]) -> Scores:
    predicted_keys = {
        (event.document_id, event.occurred_at.date().isoformat()) for event in predicted
    }
    return Scores(
        true_positives=len(predicted_keys & gold_keys),
        predicted=len(predicted_keys),
        gold=len(gold_keys),
    )
