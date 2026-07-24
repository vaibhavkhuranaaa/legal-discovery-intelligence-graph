"""Composite model score for the evaluation page.

One transparent, documented number — the unweighted mean of the four
headline metrics, computed strictly from the loaded artifacts. If any
component is missing the composite is not computed: no value is ever
invented or defaulted.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class TotalScore:
    """The composite and its four components (all in [0, 1])."""

    total: float
    extraction_f1: float  # entity-mention micro F1, strict span matching
    event_f1: float  # event extraction F1 (document + date)
    hybrid_recall_at_10: float  # graph-expanded overall recall@10
    hybrid_hit_rate_at_10: float  # graph-expanded overall hit-rate@10

    FORMULA = (
        "mean of extraction micro-F1 (strict), event F1, hybrid recall@10, and hybrid hit-rate@10"
    )


def total_model_score(extraction: dict | None, retrieval: dict | None) -> TotalScore | None:
    """Compute the composite from both artifacts, or ``None`` if either is missing."""
    if extraction is None or retrieval is None:
        return None
    try:
        extraction_f1 = extraction["mentions_strict"]["micro"]["f1"]
        event_f1 = extraction["events"]["f1"]
        overall = retrieval["graph_expanded"]["overall"]["@10"]
        recall = overall["recall"]
        hit_rate = overall["hit_rate"]
    except (KeyError, TypeError):
        return None
    components = (extraction_f1, event_f1, recall, hit_rate)
    return TotalScore(
        total=sum(components) / len(components),
        extraction_f1=extraction_f1,
        event_f1=event_f1,
        hybrid_recall_at_10=recall,
        hybrid_hit_rate_at_10=hit_rate,
    )
