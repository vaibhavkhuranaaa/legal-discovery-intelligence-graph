"""Retrieval unit tests: metric math, gold-query loading, store helpers.

No database or embedding model is touched here — cloud round-trips are
verified by running scripts/index_pgvector.py and evaluate_retrieval.py.
"""

import json
from pathlib import Path

import pytest

from legal_discovery_graph.evaluation.retrieval_eval import (
    GoldQuery,
    RankedHit,
    hit_at_k,
    load_gold_queries,
    precision_at_k,
    recall_at_k,
    score_retrieval,
)
from legal_discovery_graph.retrieval.store import to_sqlalchemy_url, vector_literal


def _query(query_id: str, relevant: set[str], category: str = "entity") -> GoldQuery:
    return GoldQuery(
        query_id=query_id,
        category=category,
        question=f"question {query_id}",
        relevant_chunk_ids=frozenset(relevant),
        is_answerable=bool(relevant),
    )


class TestMetricMath:
    def test_precision_at_k(self):
        assert precision_at_k(["a", "b", "c"], frozenset({"a", "c"}), 1) == 1.0
        assert precision_at_k(["a", "b", "c"], frozenset({"a", "c"}), 2) == 0.5
        assert precision_at_k(["b"], frozenset({"a"}), 3) == 0.0
        assert precision_at_k([], frozenset({"a"}), 5) == 0.0

    def test_recall_at_k(self):
        assert recall_at_k(["a", "b"], frozenset({"a", "c"}), 1) == 0.5
        assert recall_at_k(["a", "c"], frozenset({"a", "c"}), 2) == 1.0
        assert recall_at_k(["a"], frozenset(), 1) == 0.0  # negative query: undefined -> 0

    def test_hit_at_k(self):
        assert hit_at_k(["b", "a"], frozenset({"a"}), 1) == 0.0
        assert hit_at_k(["b", "a"], frozenset({"a"}), 2) == 1.0
        assert hit_at_k([], frozenset({"a"}), 3) == 0.0

    def test_precision_uses_k_not_retrieved_count(self):
        # 1 relevant hit in a k=5 window is precision 0.2 even if only 1 chunk came back.
        assert precision_at_k(["a"], frozenset({"a"}), 5) == pytest.approx(0.2)


class TestScoreRetrieval:
    def test_aggregates_answerable_and_negative_queries(self):
        queries = [
            _query("q1", {"c1"}),
            _query("q2", {"c2", "c3"}, category="event"),
            _query("qn", set(), category="negative"),
        ]
        results = {
            "q1": [RankedHit("c1", 0.9), RankedHit("x", 0.5)],
            "q2": [RankedHit("x", 0.8), RankedHit("c2", 0.7)],
            "qn": [RankedHit("x", 0.2)],
        }
        metrics = score_retrieval(queries, results, ks=(1, 2))

        assert metrics["answerable_queries"] == 2
        assert metrics["negative_queries"] == 1
        # q1 hits at 1, q2 misses at 1 -> macro hit@1 = 0.5; both hit by k=2.
        assert metrics["overall"]["@1"]["hit_rate"] == 0.5
        assert metrics["overall"]["@2"]["hit_rate"] == 1.0
        # q2 recall@2 = 1/2, q1 recall@2 = 1 -> macro 0.75.
        assert metrics["overall"]["@2"]["recall"] == 0.75
        assert metrics["per_category"]["event"]["@1"]["hit_rate"] == 0.0
        separation = metrics["refusal"]["separation"]
        assert separation["negative_top1_max"] == 0.2
        assert separation["answerable_top1_min"] == 0.8
        assert separation["separable"] is True

    def test_not_separable_when_scores_overlap(self):
        queries = [_query("q1", {"c1"}), _query("qn", set(), category="negative")]
        results = {
            "q1": [RankedHit("c1", 0.5)],
            "qn": [RankedHit("x", 0.6)],
        }
        metrics = score_retrieval(queries, results, ks=(1,))
        assert metrics["refusal"]["separation"]["separable"] is False

    def test_missing_results_raise(self):
        with pytest.raises(ValueError, match="missing"):
            score_retrieval([_query("q1", {"c1"})], {}, ks=(1,))


class TestGoldQueryLoading:
    def test_loads_generated_labels(self, tmp_path: Path):
        rows = [
            {
                "query_id": "q1",
                "category": "entity",
                "question": "Who?",
                "relevant_chunk_ids": ["c1", "c2"],
                "relevant_document_ids": ["d1"],
                "evidence_snippets": ["snippet"],
                "is_answerable": True,
            },
            {
                "query_id": "q2",
                "category": "negative",
                "question": "Anything?",
                "relevant_chunk_ids": [],
                "relevant_document_ids": [],
                "evidence_snippets": [],
                "is_answerable": False,
            },
        ]
        (tmp_path / "retrieval.jsonl").write_text(
            "\n".join(json.dumps(row) for row in rows) + "\n"
        )
        queries = load_gold_queries(tmp_path)
        assert [query.query_id for query in queries] == ["q1", "q2"]
        assert queries[0].relevant_chunk_ids == frozenset({"c1", "c2"})
        assert queries[1].is_answerable is False


class TestStoreHelpers:
    def test_vector_literal_round_trips_floats(self):
        assert vector_literal([0.5, -1.0]) == "[0.5,-1.0]"
        literal = vector_literal([0.1234567891234, 2.0])
        assert literal.startswith("[") and literal.endswith("]")
        assert [float(v) for v in literal[1:-1].split(",")] == [0.1234567891234, 2.0]

    def test_to_sqlalchemy_url_pins_psycopg_driver(self):
        assert to_sqlalchemy_url("postgresql://u:p@h:5432/db").startswith(
            "postgresql+psycopg://"
        )
        already = "postgresql+psycopg://u:p@h/db"
        assert to_sqlalchemy_url(already) == already
