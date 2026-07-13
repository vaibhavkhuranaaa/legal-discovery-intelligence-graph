"""Score pgvector semantic retrieval against the gold query set.

Runs every gold query in data/labels/retrieval.jsonl through the live
retriever (requires DATABASE_URL and an indexed corpus — run
index_pgvector.py first), then writes artifacts/retrieval_metrics.json and
per-query results to artifacts/retrieval_results.jsonl. Every retrieval
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
    load_gold_queries,
    score_retrieval,
)
from legal_discovery_graph.retrieval import SemanticRetriever


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
    retriever = SemanticRetriever.from_settings()

    results: dict[str, list[RankedHit]] = {}
    rows = []
    for query in queries:
        hits = retriever.search(query.question, limit=args.k)
        results[query.query_id] = [RankedHit(hit.chunk_id, hit.score) for hit in hits]
        rows.append(
            {
                "query_id": query.query_id,
                "category": query.category,
                "question": query.question,
                "relevant_chunk_ids": sorted(query.relevant_chunk_ids),
                "retrieved": [
                    {"chunk_id": hit.chunk_id, "score": round(hit.score, 4)} for hit in hits
                ],
            }
        )

    metrics = {
        "embedding_model": get_settings().embedding_model_name,
        "retrieved_per_query": args.k,
        **score_retrieval(queries, results),
        "note": (
            "Synthetic templated corpus: scores overstate real-world performance "
            "(see docs/DATA_AND_EVALUATION.md and ADR-0005)."
        ),
    }

    args.artifacts_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = args.artifacts_dir / "retrieval_metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n")
    with (args.artifacts_dir / "retrieval_results.jsonl").open("w") as handle:
        for row in rows:
            handle.write(json.dumps(row, sort_keys=True) + "\n")

    print(f"queries: {len(queries)} ({metrics['answerable_queries']} answerable, "
          f"{metrics['negative_queries']} negative)")
    header = f"{'scope':<16}" + "".join(f"{'P@' + str(k):>8}{'R@' + str(k):>8}{'hit@' + str(k):>8}"
                                        for k in (1, 3, 5, 10))
    print(header)
    scopes = [("overall", metrics["overall"]), *sorted(metrics["per_category"].items())]
    for name, scores in scopes:
        cells = "".join(
            f"{scores[f'@{k}']['precision']:>8.3f}{scores[f'@{k}']['recall']:>8.3f}"
            f"{scores[f'@{k}']['hit_rate']:>8.3f}"
            for k in (1, 3, 5, 10)
        )
        print(f"{name:<16}{cells}")
    separation = metrics["refusal"]["separation"]
    print(
        f"refusal: negative top-1 max {separation['negative_top1_max']} vs "
        f"answerable top-1 min {separation['answerable_top1_min']} "
        f"(separable: {separation['separable']})"
    )
    print(f"metrics written to {metrics_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
