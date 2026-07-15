"""Score vector-only and graph-expanded retrieval against the gold query set.

Runs every gold query in data/labels/retrieval.jsonl through the live hybrid
retriever (requires DATABASE_URL + NEO4J_* with indexed corpus and loaded
graph — run index_pgvector.py and load_neo4j.py first). Both legs are scored
from the same pass: the raw pgvector ranking (vector_only) and the rank-interleaved
vector+graph ranking (graph_expanded). Writes artifacts/retrieval_metrics.json
and per-query results to artifacts/retrieval_results.jsonl. Every retrieval
number reported in the docs comes from this command.

Usage:
    uv run python scripts/evaluate_retrieval.py [--data-dir PATH] [--artifacts-dir PATH] [--k K]
"""

import argparse
import json
import sys
from pathlib import Path

from legal_discovery_graph.config import get_settings
from legal_discovery_graph.evaluation.retrieval_eval import (
    DEFAULT_KS,
    RankedHit,
    calibrate_refusal_threshold,
    load_gold_queries,
    score_retrieval,
)
from legal_discovery_graph.retrieval import HybridRetriever


def _print_table(name: str, metrics: dict) -> None:
    print(f"-- {name} --")
    header = f"{'scope':<16}" + "".join(
        f"{'P@' + str(k):>8}{'R@' + str(k):>8}{'hit@' + str(k):>8}" for k in DEFAULT_KS
    )
    print(header)
    scopes = [("overall", metrics["overall"]), *sorted(metrics["per_category"].items())]
    for scope, scores in scopes:
        cells = "".join(
            f"{scores[f'@{k}']['precision']:>8.3f}{scores[f'@{k}']['recall']:>8.3f}"
            f"{scores[f'@{k}']['hit_rate']:>8.3f}"
            for k in DEFAULT_KS
        )
        print(f"{scope:<16}{cells}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--artifacts-dir", type=Path, default=Path("artifacts"))
    parser.add_argument("--k", type=int, default=10, help="chunks retrieved per query")
    args = parser.parse_args()
    if args.k < max(DEFAULT_KS):
        parser.error(f"--k must be at least {max(DEFAULT_KS)} to score all configured cutoffs")

    labels_dir = args.data_dir / "labels"
    if not labels_dir.is_dir():
        print("labels not found — run `uv run python scripts/bootstrap_data.py` first")
        return 1

    queries = load_gold_queries(labels_dir)
    retriever = HybridRetriever.from_settings()

    vector_results: dict[str, list[RankedHit]] = {}
    hybrid_results: dict[str, list[RankedHit]] = {}
    rows = []
    for query in queries:
        result = retriever.search(query.question, limit=args.k)
        if not result.graph_available:
            print(f"graph unavailable — cannot evaluate graph expansion: {result.graph_error}")
            return 1
        vector_results[query.query_id] = [
            RankedHit(hit.chunk_id, hit.score) for hit in result.vector_hits
        ]
        hybrid_results[query.query_id] = [
            RankedHit(ranked.chunk.chunk_id, ranked.fused_score) for ranked in result.ranked
        ]
        rows.append(
            {
                "query_id": query.query_id,
                "category": query.category,
                "question": query.question,
                "relevant_chunk_ids": sorted(query.relevant_chunk_ids),
                "vector": [
                    {"chunk_id": hit.chunk_id, "score": round(hit.score, 4)}
                    for hit in result.vector_hits
                ],
                "graph_expanded": [
                    {
                        "chunk_id": ranked.chunk.chunk_id,
                        "fused_score": ranked.fused_score,
                        "sources": list(ranked.sources),
                        "evidence": [
                            {
                                "entity": evidence.entity_name,
                                "relation": evidence.relation,
                                "document_id": evidence.document_id,
                                "source_chunk_id": evidence.source_chunk_id,
                            }
                            for evidence in ranked.evidence
                        ],
                    }
                    for ranked in result.ranked
                ],
            }
        )

    vector_metrics = score_retrieval(queries, vector_results)
    hybrid_metrics = score_retrieval(queries, hybrid_results)
    relationship_hit5 = {
        "vector_only": vector_metrics["per_category"]["relationship"]["@5"]["hit_rate"],
        "graph_expanded": hybrid_metrics["per_category"]["relationship"]["@5"]["hit_rate"],
    }
    metrics = {
        "embedding_model": get_settings().embedding_model_name,
        "retrieved_per_query": args.k,
        "fusion": (
            "rank interleaving (best per-leg rank, vector wins ties); "
            "top-5 vector hits seed the graph (ADR-0011)"
        ),
        "vector_only": vector_metrics,
        "graph_expanded": hybrid_metrics,
        "relationship_hit_at_5": relationship_hit5,
        "refusal_calibration": calibrate_refusal_threshold(queries, vector_results),
        "note": (
            "Synthetic templated corpus: scores overstate real-world performance "
            "(see docs/DATA_AND_EVALUATION.md and ADR-0005). Refusal/separation analysis "
            "is meaningful for the vector leg's cosine scores only; fused rank scores are "
            "ranking artifacts."
        ),
    }

    args.artifacts_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = args.artifacts_dir / "retrieval_metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n")
    with (args.artifacts_dir / "retrieval_results.jsonl").open("w") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")

    print(
        f"queries: {len(queries)} ({vector_metrics['answerable_queries']} answerable, "
        f"{vector_metrics['negative_queries']} negative)"
    )
    _print_table("vector_only", vector_metrics)
    _print_table("graph_expanded", hybrid_metrics)
    print(
        f"relationship hit@5: vector-only {relationship_hit5['vector_only']:.3f} -> "
        f"graph-expanded {relationship_hit5['graph_expanded']:.3f}"
    )
    calibration = metrics["refusal_calibration"]
    if calibration is not None:
        print(
            f"refusal threshold {calibration['threshold']:.4f}: "
            f"{calibration['negatives_refused']}/{calibration['negatives_total']} negatives "
            f"refused, {calibration['false_refusals']}/{calibration['answerable_total']} "
            f"false refusals (accuracy {calibration['accuracy']:.3f})"
        )
    print(f"metrics written to {metrics_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
