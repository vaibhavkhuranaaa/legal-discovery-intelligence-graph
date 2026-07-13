# Data & Evaluation

Data generation (Milestone 1), extraction evaluation (Milestone 2), vector-only retrieval
evaluation (Milestone 3), and graph-expanded retrieval evaluation (Milestone 4) are
implemented. Every number below is reproducible from a
committed command and regenerated artifacts — nothing is hand-entered from memory.

## Synthetic Corpus (implemented)

`uv run python scripts/bootstrap_data.py [--seed N] [--data-dir PATH]` produces a deterministic
corpus (byte-identical per seed, regression-tested):

- The fictional **"Project Falcon" procurement-fraud scenario**: a procurement director steers
  an avionics contract to a shell vendor in exchange for kickbacks routed through a holding
  company, until an internal audit unravels it (`datagen/scenario.py`) — 21 planted evidence
  documents plus ~90 routine noise documents (facilities notices, unrelated invoices, routine
  memos) so retrieval is non-trivial.
- At the default seed 42: **111 documents** (63 emails, 21 invoices, 17 memos, 9 meeting notes,
  1 contract), 112 chunks, 149 entities, 583 gold mentions, 12 events, **32 gold queries**
  (generator v2: informal name references like "Daniel," / "Mr. Reyes" and incidental
  locations are gold-labeled too, so NER is not penalized for finding them).
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

Both strict (exact span) and relaxed (overlap) matching are reported; matching is one-to-one
greedy within each (document, entity type) group.

**Measured results (Milestone 2)** — reproduce with
`uv run python scripts/bootstrap_data.py && uv run python scripts/evaluate_extraction.py`
(seed 42, spaCy `en_core_web_sm` 3.8.0 pinned; full breakdown in
`artifacts/extraction_metrics.json`):

| Type | P (strict) | R (strict) | F1 (strict) | P (relaxed) | R (relaxed) | F1 (relaxed) |
|---|---|---|---|---|---|---|
| person | 0.996 | 0.838 | 0.910 | 0.996 | 0.838 | 0.910 |
| organization | 0.635 | 0.742 | 0.684 | 0.712 | 0.831 | 0.767 |
| money | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| date | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| project | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| location | 0.652 | 1.000 | 0.789 | 0.652 | 1.000 | 0.789 |
| **micro** | **0.903** | **0.877** | **0.889** | **0.917** | **0.890** | **0.903** |
| events (doc+date) | 1.000 | 1.000 | 1.000 | | | |

**Honest reading of these numbers** (extraction design: ADR-0009):

- Regex-owned types (money, date, project) are perfect *by construction* — the corpus generator
  and the extractor independently implement the same textual conventions. On real documents
  with messy formats these would drop.
- The small NER model's real error profile is visible in organization/location: it misses some
  vendor names ("Lakeshore Catering", "Ironwood Legal LLP"), over-predicts department-like
  phrases ("Finance", "Audit Committee", "Internal Audit") and the venue "Hillside Grill" as
  organizations, and misses bare first names in email signatures — deliberately not patched
  with corpus-specific rules.
- Event scores reflect a trigger lexicon designed for this procurement/audit domain plus a
  participants-required rule; recall is bounded by lexicon coverage.
- Above all: this is templated synthetic text (ADR-0005). These scores overstate real-world
  performance and are presented as evidence the *pipeline and evaluation harness work*, not as
  NER benchmarks.

Regression floors (relaxed micro F1 ≥ 0.85, strict ≥ 0.75, events ≥ 0.90) run in CI via
`tests/test_evaluation.py`.

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

#### Measured — Milestone 3, vector-only (seed 42, run 2026-07-13)

`sentence-transformers/all-MiniLM-L6-v2` (normalized, 384-dim) over Supabase pgvector with an
HNSW cosine index; 28 answerable + 4 negative queries, top-10 retrieved per query,
macro-averaged. Reproduce with `uv run python scripts/evaluate_retrieval.py` (full numbers in
`artifacts/retrieval_metrics.json`).

| scope | P@1 | R@1 | hit@1 | R@5 | hit@5 | R@10 | hit@10 |
|---|---|---|---|---|---|---|---|
| overall | 0.607 | 0.554 | 0.607 | 0.857 | 0.893 | 0.929 | 0.964 |
| document | 0.400 | 0.400 | 0.400 | 1.000 | 1.000 | 1.000 | 1.000 |
| entity | 0.400 | 0.300 | 0.400 | 0.900 | 1.000 | 0.900 | 1.000 |
| event | 0.857 | 0.857 | 0.857 | 1.000 | 1.000 | 1.000 | 1.000 |
| financial | 1.000 | 0.900 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| relationship | 0.333 | 0.250 | 0.333 | 0.417 | 0.500 | 0.750 | 0.833 |

Honest findings, kept as-is rather than tuned away:

- **Relationship queries are the weakest lane** (hit@5 0.500 vs ≥ 1.000 for every other
  category). Multi-hop questions ("who connects X to Y?") are exactly what pure vector
  similarity cannot answer — this gap is the measured baseline the Milestone 4 graph expansion
  must improve on.
- **Top-1 similarity alone cannot drive refusal.** The best-scoring chunk for the four negative
  queries reaches cosine similarity 0.492, while some answerable queries' top hits score as low
  as 0.379 — the distributions overlap, so a plain score threshold would either miss refusals
  or refuse answerable queries. Refusal handling in the dashboard milestone must therefore use
  more than the raw top-1 score (per-query score margins and/or graph corroboration). No
  threshold was tuned on these 32 queries.

#### Measured — Milestone 4, graph-expanded (seed 42, run 2026-07-13)

Same pass and query set as above; the hybrid ranking interleaves the pgvector leg with
evidence-backed Neo4j expansion (top-5 vector hits seed co-mention / correspondence / event
traversal; constant-free rank interleaving, vector wins ties — ADR-0011). Both legs are scored
by `uv run python scripts/evaluate_retrieval.py`; per-query evidence trails are written to
`artifacts/retrieval_results.jsonl`.

| scope | P@1 | R@1 | hit@1 | R@5 | hit@5 | R@10 | hit@10 |
|---|---|---|---|---|---|---|---|
| overall | 0.607 | 0.554 | 0.607 | 0.929 | 0.964 | 0.946 | 0.964 |
| document | 0.400 | 0.400 | 0.400 | 1.000 | 1.000 | 1.000 | 1.000 |
| entity | 0.400 | 0.300 | 0.400 | 1.000 | 1.000 | 1.000 | 1.000 |
| event | 0.857 | 0.857 | 0.857 | 1.000 | 1.000 | 1.000 | 1.000 |
| financial | 1.000 | 0.900 | 1.000 | 1.000 | 1.000 | 1.000 | 1.000 |
| relationship | 0.333 | 0.250 | 0.333 | 0.667 | 0.833 | 0.750 | 0.833 |

The graph's contribution, measured not asserted:

- **Relationship hit@5 0.500 → 0.833** (R@5 0.417 → 0.667) — the multi-hop gap vector
  similarity could not close is exactly where evidence-backed expansion helps; overall hit@5
  rises 0.893 → 0.964 and no category degrades at any k. Top-1 metrics are structurally
  unchanged: interleaving never displaces the vector leg's first hit.
- **Summed RRF was measured and rejected** (ADR-0011): its intersection boost let
  graph-connected hub chunks displace correct vector top-1 hits (overall hit@1 0.607 → 0.143
  in that configuration). The failed measurement is recorded because it motivated the fusion
  design; only the interleaved configuration ships.
- Relationship R@10 stays 0.750 in both modes — evidence more than one hop from every seed
  entity is still out of reach, a known limitation for the dashboard milestone to surface
  honestly rather than hide.

### Reporting rules

- Metrics are produced by `uv run` commands in `src/legal_discovery_graph/evaluation/`, written
  to `artifacts/`, and summarized here and in the UI metrics page with the corpus seed, model
  name, and date.
- No cherry-picking: the full query set is always scored; failures are part of the report.
- Any metric quoted in `README.md` must link to the reproduction command.
