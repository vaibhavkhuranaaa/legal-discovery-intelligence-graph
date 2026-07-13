# Data & Evaluation

Data generation is implemented (Milestone 1); evaluation scoring is not. **No quality metrics
are reported yet** — extraction and retrieval metrics appear only after the extraction and
retrieval milestones run, and every reported number must be reproducible from a committed
command.

## Synthetic Corpus (implemented)

`uv run python scripts/bootstrap_data.py [--seed N] [--data-dir PATH]` produces a deterministic
corpus (byte-identical per seed, regression-tested):

- The fictional **"Project Falcon" procurement-fraud scenario**: a procurement director steers
  an avionics contract to a shell vendor in exchange for kickbacks routed through a holding
  company, until an internal audit unravels it (`datagen/scenario.py`) — 21 planted evidence
  documents plus ~90 routine noise documents (facilities notices, unrelated invoices, routine
  memos) so retrieval is non-trivial.
- At the default seed 42: **111 documents** (63 emails, 21 invoices, 17 memos, 9 meeting notes,
  1 contract), 112 chunks, 147 entities, 573 gold mentions, 12 events, **32 gold queries**.
- All names, organizations, amounts, and events are fictional; email domains use `.example`
  (see `product.md`, synthetic-data policy).
- Mechanics of determinism and label exactness (uuid5 IDs, composer offset tracking): ADR-0008.

## Gold Labels (`data/labels/`) (implemented)

Emitted at generation time, because the generator knows exactly what it planted:

1. **`entities.json`** — canonical entity catalog (id, type, name, aliases).
2. **`mentions.jsonl`** — every entity mention: entity ID, document ID, covering chunk ID,
   surface text, and document-level character offsets (`body[start:end] == surface`,
   regression-tested).
3. **`events.jsonl`** — dated events with involved entity IDs and the evidencing document.
4. **`retrieval.jsonl`** — 32 investigative questions, each with a `category` (5 entity-lookup,
   6 relationship, 7 event/timeline, 5 document-evidence, 5 financial/invoice, 4 negative), an
   `is_answerable` flag, and the relevant document IDs, chunk IDs, and planted evidence
   snippets those chunks contain. The 4 **negative queries** have empty relevant sets by
   design — they score refusal/no-evidence behavior in later milestones.

**Label completeness is regression-tested:** every occurrence of a canonical entity name or
alias in any document body must be covered by a gold mention span of that same entity with
exact character offsets (`tests/test_datagen.py::test_gold_mentions_are_complete_for_catalog_surfaces`).

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
- **Negative queries** (empty gold relevant set) are scored separately for no-evidence
  behavior: the system should refuse or return an explicit no-evidence state rather than
  presenting irrelevant chunks as support.

### Reporting rules

- Metrics are produced by `uv run` commands in `src/legal_discovery_graph/evaluation/`, written
  to `artifacts/`, and summarized here and in the UI metrics page with the corpus seed, model
  name, and date.
- No cherry-picking: the full query set is always scored; failures are part of the report.
- Any metric quoted in `README.md` must link to the reproduction command.
