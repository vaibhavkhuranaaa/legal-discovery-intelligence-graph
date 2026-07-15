"""Score rule-based privilege/PII flags against the gold labels.

Runs :func:`legal_discovery_graph.review.flags.flag_text` over every raw
document body and compares document-level predictions with
``data/labels/privilege_pii.json`` (written by bootstrap_data.py). Fully
offline and deterministic — no backends required. Writes
``artifacts/flags_metrics.json``; every flags number reported in the docs
comes from this command.

Usage:
    uv run python scripts/evaluate_flags.py [--data-dir PATH] [--artifacts-dir PATH]
"""

import argparse
import json
import sys
from pathlib import Path

from legal_discovery_graph.review import flag_text

PII_TYPES = ("ssn", "bank_account", "routing_number")


def _prf(tp: int, fp: int, fn: int) -> dict:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "tp": tp,
        "fp": fp,
        "fn": fn,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument("--artifacts-dir", type=Path, default=Path("artifacts"))
    args = parser.parse_args()

    gold_path = args.data_dir / "labels" / "privilege_pii.json"
    raw_dir = args.data_dir / "raw"
    if not gold_path.is_file() or not raw_dir.is_dir():
        print("labels not found — run `uv run python scripts/bootstrap_data.py` first")
        return 1

    gold = json.loads(gold_path.read_text(encoding="utf-8"))
    counsel_domains = tuple(gold["counsel_domains"])

    predictions: dict[str, tuple[bool, tuple[str, ...]]] = {}
    for record_path in sorted(raw_dir.glob("*.json")):
        if record_path.name == "manifest.json":
            continue
        record = json.loads(record_path.read_text(encoding="utf-8"))
        flags = flag_text(record["body"], counsel_domains)
        predictions[record["document"]["document_id"]] = (flags.privileged, flags.pii_types)

    missing = set(gold["documents"]) - set(predictions)
    if missing:
        print(f"raw records missing for {len(missing)} labeled documents — regenerate the corpus")
        return 1

    priv_tp = priv_fp = priv_fn = 0
    pii_counts = {pii: [0, 0, 0] for pii in PII_TYPES}  # tp, fp, fn
    for document_id, label in gold["documents"].items():
        predicted_priv, predicted_pii = predictions[document_id]
        if predicted_priv and label["privileged"]:
            priv_tp += 1
        elif predicted_priv:
            priv_fp += 1
        elif label["privileged"]:
            priv_fn += 1
        gold_pii = set(label["pii_types"])
        for pii in PII_TYPES:
            got, want = pii in predicted_pii, pii in gold_pii
            if got and want:
                pii_counts[pii][0] += 1
            elif got:
                pii_counts[pii][1] += 1
            elif want:
                pii_counts[pii][2] += 1

    pii_micro = [sum(counts[i] for counts in pii_counts.values()) for i in range(3)]
    metrics = {
        "documents": len(gold["documents"]),
        "counsel_domains": list(counsel_domains),
        "privileged": _prf(priv_tp, priv_fp, priv_fn),
        "pii": {pii: _prf(*counts) for pii, counts in pii_counts.items()},
        "pii_micro": _prf(*pii_micro),
        "note": (
            "Document-level rule-based flags on the synthetic corpus; real discovery "
            "text (scans, forwarded chains, OCR noise) would score materially lower."
        ),
    }

    args.artifacts_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = args.artifacts_dir / "flags_metrics.json"
    metrics_path.write_text(json.dumps(metrics, indent=2, sort_keys=True) + "\n")

    print(f"documents: {metrics['documents']}")
    print(f"privileged: {metrics['privileged']}")
    for pii in PII_TYPES:
        print(f"pii/{pii}: {metrics['pii'][pii]}")
    print(f"pii micro: {metrics['pii_micro']}")
    print(f"metrics written to {metrics_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
