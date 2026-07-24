# Legal Discovery Intelligence Graph

[![CI](https://github.com/vaibhavkhuranaaa/legal-discovery-intelligence-graph/actions/workflows/ci.yml/badge.svg)](https://github.com/vaibhavkhuranaaa/legal-discovery-intelligence-graph/actions/workflows/ci.yml) ![Publication](https://img.shields.io/badge/publication-review_required-5b6470) ![Production claim](https://img.shields.io/badge/production_claim-no-18794e)

> A deployed Graph RAG investigation workspace with cited evidence, entity graphs, and reproducible evaluation.

## Executive overview

| Question | Reviewed fact |
| --- | --- |
| Problem | How can an investigator move from a large discovery record to evidence they can inspect and trace? |
| Intended user | A legal-technology reviewer or discovery analyst evaluating evidence retrieval and relationship navigation. |
| Decision supported | Whether a relationship or event is supported by cited evidence in the fictional matter. |
| Outcome | A public synthetic-matter investigation workflow combines vector and graph retrieval, cited evidence, timelines, privilege/PII flags, calibrated refusal, and an auditable case brief. |
| Try it | [Open the reviewed demo](https://legal-discovery-intelligence-graph.onrender.com) |
| Important boundary | All documents, people, companies, amounts, identifiers, and events are synthetic and fictional. Metrics are reproducible results on templated synthetic text and are not claims about real legal matters, privilege determinations, or production discovery performance. |

## What the system does

- Deterministic synthetic corpus and gold-label generation
- Real-file ingestion for PDF, DOCX, and EML
- Entity, event, privilege, and synthetic-PII extraction
- PostgreSQL pgvector indexing and Neo4j graph loading
- Hybrid retrieval with calibrated refusal and cited evidence
- Flask investigation UI with graph, timeline, evaluation, and case brief

## Visual architecture

![System architecture showing a reviewer, synthetic discovery inputs, validation and extraction, vector and graph stores, hybrid retrieval, security boundary, observability, Render deployment, cited outputs, and the evaluation loop.](portfolio/assets/system.svg)

Canonical editable source: [`architecture/system.mmd`](architecture/system.mmd). The SVG and PNG are deterministic generated assets; `system.freshness.json` records their source hash and renderer.

## End-to-end workflow

- Open the fictional matter and choose a guided investigation question
- Review hybrid search results and the calibrated evidence/refusal state
- Traverse related entities and events in the graph and timeline
- Open cited synthetic documents and compare the result with committed evaluation

## Technology stack

| Technology | Role | Asset provenance |
| --- | --- | --- |
| <img src="portfolio/assets/technology/python.svg" width="20" height="20" alt="" /> Python | Application, extraction, and evaluation language | Simple Icons 16.27.0 (CC0-1.0) |
| <img src="portfolio/assets/technology/flask.svg" width="20" height="20" alt="" /> Flask | Read-only investigation interface | Simple Icons 16.27.0 (CC0-1.0) |
| <img src="portfolio/assets/technology/langchain.svg" width="20" height="20" alt="" /> LangChain | Hybrid retrieval orchestration | Simple Icons 16.27.0 (CC0-1.0) |
| <img src="portfolio/assets/technology/sentence-transformers.svg" width="20" height="20" alt="" /> sentence-transformers | Embedding model | Simple Icons 16.27.0 (CC0-1.0) |
| <img src="portfolio/assets/technology/onnx-runtime.svg" width="20" height="20" alt="" /> ONNX Runtime | Memory-bounded deployed inference | Simple Icons 16.27.0 (CC0-1.0) |
| <img src="portfolio/assets/technology/postgresql-plus-pgvector.svg" width="20" height="20" alt="" /> PostgreSQL + pgvector | Vector retrieval store | Simple Icons 16.27.0 (CC0-1.0) |
| <img src="portfolio/assets/technology/neo4j-auradb.svg" width="20" height="20" alt="" /> Neo4j AuraDB | Relationship graph | Simple Icons 16.27.0 (CC0-1.0) |
| <img src="portfolio/assets/technology/supabase.svg" width="20" height="20" alt="" /> Supabase | Hosted PostgreSQL provider | Simple Icons 16.27.0 (CC0-1.0) |
| <img src="portfolio/assets/technology/plotly.svg" width="20" height="20" alt="" /> Plotly | Timeline and analytical visuals | Simple Icons 16.27.0 (CC0-1.0) |

## Quick start

### Install and verify

```bash
uv sync --frozen
uv run ruff check .
uv run pytest -q
```

### Generate the synthetic corpus and evaluation

```bash
uv run python scripts/bootstrap_data.py
uv run python scripts/evaluate_extraction.py
uv run python scripts/evaluate_flags.py
```

### Run the local product

```bash
uv run flask --app legal_discovery_graph.webapp run
```

## Demonstration workflow

**Investigate a relationship while retaining citations**

- Open the fictional matter and choose a guided investigation question
- Review hybrid search results and the calibrated evidence/refusal state
- Traverse related entities and events in the graph and timeline
- Open cited synthetic documents and compare the result with committed evaluation

## Evaluation

| Measure | Dataset / scope | Method | Evidence | Limitation |
| --- | --- | --- | --- | --- |
| strict entity F1: 0.887 | 2,223 entity mentions in a deterministic 455-document synthetic corpus, seed 42 | One-to-one strict span matching against generator-emitted gold labels | [evaluation.entity-extraction](artifacts/extraction_metrics.json) | Clean templated text materially overstates expected performance on real discovery documents. |
| relationship hit@5: 0.833 | 38 categorized retrieval queries over the 455-document synthetic corpus | Versioned labeled-query evaluation comparing vector-only and graph-expanded retrieval | [evaluation.hybrid-retrieval](artifacts/retrieval_metrics.json) | Graph expansion improves relationship queries but can dilute dense-corpus ranking at larger k. |

Evaluation mode: **deterministic local evaluation on a synthetic corpus plus a live reachability observation**. These results are project evidence, not a production SLO.

## Data disclosure

| Classification | Source | Permitted use | Excluded data |
| --- | --- | --- | --- |
| synthetic | Repository-generated Project Falcon synthetic legal-discovery corpus, seed 42 | Portfolio demonstration, deterministic evaluation, and engineering research | Real client, employee, custodian, matter, communication, and personal data; Production legal advice, privilege determinations, and discovery decisions |

License / provenance: Repository project license; no third-party client or matter data

## Security and privacy boundaries

| Control | Implementation | Evidence | Known limitation |
| --- | --- | --- | --- |
| Synthetic-only public corpus | The generator creates fictional documents, people, organizations, events, identifiers, and gold labels. | [disclosure.synthetic-corpus](docs/DATA_AND_EVALUATION.md) | Synthetic templated text is cleaner than real discovery material. |
| Evidence threshold and explicit refusal | The retriever returns an explicit unsupported state when the calibrated evidence threshold is not met. | [evaluation.hybrid-retrieval](artifacts/retrieval_metrics.json) | A calibrated threshold on this corpus is not a legal-correctness guarantee. |
| Read-only public presentation | The public application exposes the fictional matter and aggregate evidence without a real-client upload path. | [deployment.render-root](evidence/deployment/live-check.json), [disclosure.synthetic-corpus](docs/DATA_AND_EVALUATION.md) | The demo has no authenticated matter isolation or production confidentiality posture. |

## Deployment state

| Provider | Runtime | State | Exposure | Verified | Production claim |
| --- | --- | --- | --- | --- | --- |
| Render | Flask + gunicorn with an ONNX embedding backend | live | anonymous | 2026-07-23T20:52:19Z | No |

## Technology decisions and trade-offs

| Decision | Why | Alternative | Trade-off |
| --- | --- | --- | --- |
| PostgreSQL pgvector plus Neo4j | Vector similarity and explicit relationship traversal serve complementary discovery questions. | Vector search alone | Two stores add operational complexity, and graph expansion requires category-level regression measurement. |
| ONNX Runtime on Render | Fits the embedding model inside the free-tier memory envelope while preserving measured vector parity. | PyTorch sentence-transformers runtime | Requires an exported model and parity testing but avoids the deployed worker's torch memory failure. |

## Cost boundaries

| Component | Boundary | Implication |
| --- | --- | --- |
| Render web service | Free-tier, memory-constrained, sleep-prone deployment using ONNX instead of PyTorch. | Cold starts and availability variation are expected; no SLO is claimed. |
| Supabase and Neo4j AuraDB | Portfolio-scale hosted data services for a synthetic corpus. | A real matter would require an owner-approved capacity, retention, and security budget. |

## Known limitations

- Synthetic templated text is materially cleaner than real discovery data.
- The public demo has no real-client security or matter-isolation posture.
- Free-tier services can sleep or pause and do not establish an availability SLO.
- Privilege/PII flags are research aids, not legal or privacy determinations.

## Scalability roadmap

- Add authenticated matter isolation, role-based access, audit retention, and encrypted document storage
- Introduce OCR and robust parsing for scans, forwarded chains, and production document variance
- Move ingestion and indexing to background workers with versioned index promotion
- Add real-world benchmark sets under appropriate legal/data agreements and revalidate thresholds
- Retire free-tier keep-alive behavior under an owner-approved paid reliability envelope

## Repository structure

| Path | Purpose |
| --- | --- |
| `src/legal_discovery_graph/` | Application, extraction, retrieval, graph, and interface code. |
| `scripts/` | Deterministic corpus, indexing, evaluation, ingestion, and presentation commands. |
| `artifacts/` | Committed aggregate evaluation evidence. |
| `architecture/system.mmd` | Canonical editable architecture source. |
| `portfolio/` | Public evidence manifest and generated presentation assets. |
| `docs/` | State, handoff, data, deployment, scaling, and decision records. |

## Reproduction and verification

| Check | Command | Evidence |
| --- | --- | --- |
| Lint | `.venv/bin/python -m ruff check .` | Command output |
| Tests | `.venv/bin/python -m pytest -q` | Command output |
| Manifest JSON | `.venv/bin/python -m json.tool portfolio/project.json >/dev/null` | Command output |

## Evidence index

| ID | Kind | Claim | Method | Result |
| --- | --- | --- | --- | --- |
| [`evaluation.entity-extraction`](artifacts/extraction_metrics.json) | evaluation | Entity-mention extraction achieved micro F1 0.887 strict on the committed synthetic corpus. | One-to-one strict span matching against generator-emitted gold labels | 0.887 |
| [`evaluation.hybrid-retrieval`](artifacts/retrieval_metrics.json) | evaluation | Hybrid retrieval achieved R@10 0.857 and graph expansion improved relationship hit@5 to 0.833. | Versioned labeled-query evaluation comparing vector-only and graph-expanded retrieval | R@10 0.857 / relationship hit@5 0.833 |
| [`evaluation.privilege-pii-flags`](artifacts/flags_metrics.json) | evaluation | Privilege and synthetic-PII rules achieved F1 1.0 on clean templated text. | Document-level rule evaluation against synthetic gold labels | 1 |
| [`deployment.render-root`](evidence/deployment/live-check.json) | deployment | The current Render application root returned HTTP 200. | Read-only HTTP request with redirects followed; no user data submitted | true |
| [`disclosure.synthetic-corpus`](docs/DATA_AND_EVALUATION.md) | disclosure | The corpus, gold labels, people, organizations, identifiers, and events are generated and fictional. | Versioned generator and data/evaluation documentation review | synthetic |

## License and attribution

Source code is MIT licensed. The committed corpus is repository-generated and fictional.

Technology marks are local copies generated from the pinned Simple Icons package where a canonical mark is available; every mark has a visible text label. Mermaid-generated architecture assets are derived from the canonical source in this repository.
