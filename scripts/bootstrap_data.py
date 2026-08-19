"""Generate the synthetic discovery corpus and gold labels.

Deterministic for a given seed: identical seed → byte-identical output in
data/raw/, data/processed/, and data/labels/. All content is fictional.

Usage:
    uv run python scripts/bootstrap_data.py [--seed N] [--data-dir PATH]
"""

import argparse
import sys
from pathlib import Path

from legal_discovery_graph.datagen.bootstrap import run_bootstrap

DEFAULT_SEED = 42


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    args = parser.parse_args()

    result = run_bootstrap(seed=args.seed, data_dir=args.data_dir)
    by_type: dict[str, int] = {}
    for document, _ in result.bundle.documents:
        by_type[document.doc_type.value] = by_type.get(document.doc_type.value, 0) + 1

    print(f"seed:       {args.seed}")
    print(f"documents:  {len(result.bundle.documents)} {by_type}")
    print(f"chunks:     {len(result.ingestion.chunks)}")
    print(f"entities:   {len(result.entities)}")
    print(f"mentions:   {len(result.mentions)}")
    print(f"events:     {len(result.events)}")
    print(f"queries:    {len(result.retrieval_labels)}")
    print(f"output:     {args.data_dir}/raw, {args.data_dir}/processed, {args.data_dir}/labels")
    return 0


if __name__ == "__main__":
    sys.exit(main())
