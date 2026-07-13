"""Run entity/event extraction over the generated corpus and score it.

Reads data/raw/ and data/labels/ (regenerate first with bootstrap_data.py),
writes predictions and metrics to artifacts/, and prints a summary table.
Every number reported in the docs comes from this command.

Usage:
    uv run python scripts/evaluate_extraction.py [--data-dir PATH] [--artifacts-dir PATH]
"""

import argparse
import json
import sys
from pathlib import Path

from legal_discovery_graph.evaluation.extraction_eval import (
    load_gold_event_keys,
    load_gold_mentions,
    score_events,
    score_mentions,
)
from legal_discovery_graph.extraction.extractor import extract_corpus
from legal_discovery_graph.ingestion.pipeline import load_raw_record
from legal_discovery_graph.models import EntityType


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--artifacts-dir", type=Path, default=Path("artifacts"))
    args = parser.parse_args()

    raw_dir = args.data_dir / "raw"
    labels_dir = args.data_dir / "labels"
    if not raw_dir.is_dir() or not labels_dir.is_dir():
        print("corpus not found — run `uv run python scripts/bootstrap_data.py` first")
        return 1

    records = [
        load_raw_record(path)
        for path in sorted(raw_dir.glob("*.json"))
        if path.name != "manifest.json"
    ]
    result = extract_corpus(records)
    gold_mentions = load_gold_mentions(labels_dir)
    gold_event_keys = load_gold_event_keys(labels_dir)

    strict = score_mentions(result.mentions, gold_mentions, strict=True)
    relaxed = score_mentions(result.mentions, gold_mentions, strict=False)
    events = score_events(result.events, gold_event_keys)

    manifest = json.loads((raw_dir / "manifest.json").read_text(encoding="utf-8"))
    metrics = {
        "corpus": {
            "seed": manifest["seed"],
            "documents": manifest["documents"],
            "gold_mentions": len(gold_mentions),
            "predicted_mentions": len(result.mentions),
            "resolved_entities": len(result.entities),
        },
        "ner_model": "en_core_web_sm-3.8.0 (pinned in pyproject.toml)",
        "mentions_strict": {k: s.as_dict() for k, s in strict.items()},
        "mentions_relaxed": {k: s.as_dict() for k, s in relaxed.items()},
        "events": events.as_dict(),
        "note": (
            "Synthetic templated corpus: scores overstate real-world performance "
            "(see docs/DATA_AND_EVALUATION.md and ADR-0005)."
        ),
    }

    args.artifacts_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = args.artifacts_dir / "extraction_metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n")
    with (args.artifacts_dir / "predicted_mentions.jsonl").open("w") as handle:
        for m in result.mentions:
            handle.write(
                json.dumps(
                    {
                        "document_id": m.document_id,
                        "entity_type": m.entity_type.value,
                        "surface": m.surface,
                        "start": m.start,
                        "end": m.end,
                        "entity_id": m.entity_id,
                        "canonical_name": m.canonical_name,
                    },
                    sort_keys=True,
                )
                + "\n"
            )

    print(
        f"documents: {manifest['documents']}   gold mentions: {len(gold_mentions)}   "
        f"predicted: {len(result.mentions)}   resolved entities: {len(result.entities)}"
    )
    header = (
        f"{'type':<14}{'P(strict)':>10}{'R(strict)':>10}{'F1(strict)':>11}"
        f"{'P(relax)':>10}{'R(relax)':>10}{'F1(relax)':>11}"
    )
    print(header)
    for key in [*[entity_type.value for entity_type in EntityType], "micro"]:
        s, r = strict[key], relaxed[key]
        print(
            f"{key:<14}{s.precision:>10.3f}{s.recall:>10.3f}{s.f1:>11.3f}"
            f"{r.precision:>10.3f}{r.recall:>10.3f}{r.f1:>11.3f}"
        )
    print(f"{'events':<14}{events.precision:>10.3f}{events.recall:>10.3f}{events.f1:>11.3f}")
    print(f"metrics written to {metrics_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
