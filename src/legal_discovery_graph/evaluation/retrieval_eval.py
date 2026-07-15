"""Retrieval evaluation: ranked search results vs gold query labels.

Answerable queries are scored with macro-averaged precision@k, recall@k, and
hit-rate@k against ``relevant_chunk_ids``, overall and per query category.

The 4 negative queries have empty relevant sets by construction: every chunk
retrieved for them is off-topic. They are excluded from precision/recall
(undefined without relevant items) and instead measure refusal feasibility:
we report each negative query's top-1 similarity next to the answerable
top-1 distribution. Clean separation means a score threshold can drive
"no supporting evidence" refusals in the dashboard milestone; the threshold
itself is deliberately not tuned here — 32 queries offer no held-out set.
"""

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

DEFAULT_KS: tuple[int, ...] = (1, 3, 5, 10)


@dataclass(frozen=True)
class GoldQuery:
    """One gold retrieval query from ``data/labels/retrieval.jsonl``."""

    query_id: str
    category: str
    question: str
    relevant_chunk_ids: frozenset[str]
    is_answerable: bool


@dataclass(frozen=True)
class RankedHit:
    """One retrieved chunk for a query, in rank order."""

    chunk_id: str
    score: float


def load_gold_queries(labels_dir: Path) -> list[GoldQuery]:
    queries: list[GoldQuery] = []
    for line in (labels_dir / "retrieval.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        queries.append(
            GoldQuery(
                query_id=row["query_id"],
                category=row["category"],
                question=row["question"],
                relevant_chunk_ids=frozenset(row["relevant_chunk_ids"]),
                is_answerable=row["is_answerable"],
            )
        )
    return queries


def precision_at_k(retrieved: Sequence[str], relevant: frozenset[str], k: int) -> float:
    top = retrieved[:k]
    return sum(1 for chunk_id in top if chunk_id in relevant) / k if top else 0.0


def recall_at_k(retrieved: Sequence[str], relevant: frozenset[str], k: int) -> float:
    if not relevant:
        return 0.0
    return sum(1 for chunk_id in retrieved[:k] if chunk_id in relevant) / len(relevant)


def hit_at_k(retrieved: Sequence[str], relevant: frozenset[str], k: int) -> float:
    return 1.0 if any(chunk_id in relevant for chunk_id in retrieved[:k]) else 0.0


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _macro_scores(
    queries: Sequence[GoldQuery],
    results: Mapping[str, Sequence[RankedHit]],
    ks: Sequence[int],
) -> dict[str, dict[str, float]]:
    scores: dict[str, dict[str, float]] = {}
    for k in ks:
        precisions, recalls, hits = [], [], []
        for query in queries:
            retrieved = [hit.chunk_id for hit in results[query.query_id]]
            precisions.append(precision_at_k(retrieved, query.relevant_chunk_ids, k))
            recalls.append(recall_at_k(retrieved, query.relevant_chunk_ids, k))
            hits.append(hit_at_k(retrieved, query.relevant_chunk_ids, k))
        scores[f"@{k}"] = {
            "precision": round(_mean(precisions), 4),
            "recall": round(_mean(recalls), 4),
            "hit_rate": round(_mean(hits), 4),
        }
    return scores


def calibrate_refusal_threshold(
    queries: Sequence[GoldQuery],
    results: Mapping[str, Sequence[RankedHit]],
) -> dict | None:
    """Pick the max-accuracy refusal threshold over top-1 scores.

    The rule under evaluation is "refuse when the top-1 score is below the
    threshold". Candidates are midpoints between adjacent distinct top-1
    scores (plus one below the minimum and one above the maximum); the
    candidate with the highest classification accuracy wins, ties broken by
    the larger margin to the nearest observed score. Only meaningful for the
    vector leg, whose scores are cosine similarities. Returns ``None`` when
    either class is empty.
    """
    labeled = [
        (results[query.query_id][0].score, query.is_answerable)
        for query in queries
        if results[query.query_id]
    ]
    answerable_scores = sorted(score for score, ok in labeled if ok)
    negative_scores = sorted(score for score, ok in labeled if not ok)
    if not answerable_scores or not negative_scores:
        return None

    distinct = sorted({score for score, _ in labeled})
    candidates = (
        [distinct[0] - 0.01]
        + [(low + high) / 2 for low, high in zip(distinct, distinct[1:], strict=False)]
        + [distinct[-1] + 0.01]
    )

    def outcome(threshold: float) -> tuple[int, float]:
        correct = sum(1 for score, ok in labeled if (score >= threshold) == ok)
        margin = min(abs(score - threshold) for score, _ in labeled)
        return correct, margin

    best = max(candidates, key=lambda t: (*outcome(t), -t))
    correct, _ = outcome(best)
    refused_negatives = sum(1 for score in negative_scores if score < best)
    false_refusals = sum(1 for score in answerable_scores if score < best)
    return {
        "rule": "refuse when top-1 cosine similarity < threshold",
        "threshold": round(best, 4),
        "accuracy": round(correct / len(labeled), 4),
        "negatives_refused": refused_negatives,
        "negatives_total": len(negative_scores),
        "false_refusals": false_refusals,
        "answerable_total": len(answerable_scores),
        "answerable_top1_min": round(answerable_scores[0], 4),
        "negative_top1_max": round(negative_scores[-1], 4),
    }


def score_retrieval(
    queries: Sequence[GoldQuery],
    results: Mapping[str, Sequence[RankedHit]],
    ks: Sequence[int] = DEFAULT_KS,
) -> dict:
    """Score ranked results (query_id → hits, best first) against gold queries."""
    missing = [query.query_id for query in queries if query.query_id not in results]
    if missing:
        raise ValueError(f"results missing for {len(missing)} queries, e.g. {missing[0]}")

    answerable = [query for query in queries if query.is_answerable]
    negative = [query for query in queries if not query.is_answerable]

    per_category = {
        category: _macro_scores(
            [query for query in answerable if query.category == category], results, ks
        )
        for category in sorted({query.category for query in answerable})
    }

    answerable_top1 = [
        results[query.query_id][0].score for query in answerable if results[query.query_id]
    ]
    negative_top1 = [
        results[query.query_id][0].score for query in negative if results[query.query_id]
    ]
    separation = {
        "answerable_top1_min": round(min(answerable_top1), 4) if answerable_top1 else None,
        "answerable_top1_mean": round(_mean(answerable_top1), 4) if answerable_top1 else None,
        "negative_top1_max": round(max(negative_top1), 4) if negative_top1 else None,
        "negative_top1_mean": round(_mean(negative_top1), 4) if negative_top1 else None,
        "separable": (
            bool(answerable_top1 and negative_top1 and max(negative_top1) < min(answerable_top1))
        ),
    }

    return {
        "answerable_queries": len(answerable),
        "negative_queries": len(negative),
        "overall": _macro_scores(answerable, results, ks),
        "per_category": per_category,
        "refusal": {
            "note": (
                "Negative queries have empty relevant sets; scores below measure whether "
                "a similarity threshold can separate them from answerable queries."
            ),
            "negative_top1_scores": {
                query.query_id: round(results[query.query_id][0].score, 4)
                for query in negative
                if results[query.query_id]
            },
            "separation": separation,
        },
    }
