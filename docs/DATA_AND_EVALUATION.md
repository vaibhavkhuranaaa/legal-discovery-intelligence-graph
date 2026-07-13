# Data & Evaluation

Planned data-generation and evaluation methodology. **No metrics are reported yet** — nothing
has been generated or scored. Numbers appear here only after the evaluation milestone runs, and
every reported number must be reproducible from a committed command.

## Synthetic Corpus

`scripts/bootstrap_data.py` (data-generation milestone) will produce a seedable, deterministic
corpus in `data/raw/`:

- ~100–200 documents across five types: emails, contracts, memos, invoices, meeting notes.
- A coherent fictional investigation scenario (e.g. a procurement-fraud fact pattern) so graph
  queries and the timeline have meaningful structure — not random text.
- Fixed random seed → identical corpus, labels, and therefore metrics on every regeneration.
- All names, organizations, amounts, and events fictional (see `product.md`,
  synthetic-data policy).

## Gold Labels (`data/labels/`)

Emitted by the generator at creation time, because the generator knows exactly what it planted:

1. **Entity labels** — per document: every entity mention with type, canonical entity ID,
   surface text, and character offsets.
2. **Event labels** — per document: dated events with involved entity IDs.
3. **Retrieval labels** — a query set (~25–50 investigative questions) each mapped to the set
   of chunk IDs that constitute relevant evidence.

Labels are generated data (gitignored) but exactly reproducible from the committed generator +
seed.

## Metrics & Methodology

### Entity extraction

Predicted mentions vs gold mentions, matched on (document, entity type, character-offset
overlap):

- **Precision** = correct predicted mentions / all predicted mentions
- **Recall** = correct predicted mentions / all gold mentions
- **F1** = harmonic mean, reported per entity type and micro-averaged overall

Both strict (exact span) and relaxed (overlap) matching will be reported and labeled as such.

### Retrieval

For each gold query, retrieve top-k chunks from pgvector (and separately, the graph-expanded
evidence set):

- **Precision@k** and **Recall@k** (k = 5 and 10) against gold relevant-chunk sets
- **Hit rate** — fraction of queries with ≥1 relevant chunk in top-k
- Vector-only vs vector+graph-expansion reported separately, so the graph's contribution is
  measured, not asserted.

### Reporting rules

- Metrics are produced by `uv run` commands in `src/legal_discovery_graph/evaluation/`, written
  to `artifacts/`, and summarized here and in the UI metrics page with the corpus seed, model
  name, and date.
- No cherry-picking: the full query set is always scored; failures are part of the report.
- Any metric quoted in `README.md` must link to the reproduction command.
