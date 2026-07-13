# Legal Discovery Intelligence Graph

**GitHub:** [vaibhavkhuranaaa/legal-discovery-intelligence-graph](https://github.com/vaibhavkhuranaaa/legal-discovery-intelligence-graph)

> **Status: in development — Milestones 0–5 of 6 complete.** Foundation, the synthetic corpus
> generator (deterministic corpus + gold labels), entity/event extraction, pgvector retrieval,
> the Neo4j relationship graph with hybrid vector+graph retrieval, and the Streamlit
> investigation dashboard are done — all with reproducible evaluation; public deployment
> remains (see [docs/roadmap.md](docs/roadmap.md)). No live URL exists yet — none is claimed.
>
> **Measured results** (synthetic corpus, seed 42):
> entity-mention extraction micro **F1 0.889 strict / 0.903 relaxed**; event extraction
> **F1 1.000**; vector-only retrieval **R@5 0.857 / hit@5 0.893**; graph-expanded retrieval
> **R@5 0.929 / hit@5 0.964**, lifting relationship-query **hit@5 from 0.500 to 0.833** with
> no category degraded. Reproduce with `bootstrap_data.py`, `evaluate_extraction.py`,
> `index_pgvector.py`, `load_neo4j.py`, and `evaluate_retrieval.py`; scores are inflated by
> clean templated text — see [docs/DATA_AND_EVALUATION.md](docs/DATA_AND_EVALUATION.md).

A **Graph RAG eDiscovery investigation platform**. Given a corpus of discovery documents
(emails, contracts, memos, invoices, meeting notes), it extracts entities and events, indexes
document chunks for semantic retrieval in **PostgreSQL + pgvector**, models
entity/document/event relationships in **Neo4j AuraDB**, and serves an investigator-facing
**Streamlit dashboard** that answers questions with cited evidence, an interactive entity graph,
and a case timeline — backed by a reproducible precision/recall/F1 evaluation harness.

## Capabilities

- **Entity extraction** — spaCy NER plus deterministic regex extraction (amounts, dates,
  invoice/account identifiers) with entity resolution across documents.
- **Semantic retrieval (implemented)** — Hugging Face sentence-transformer embeddings over
  document chunks, stored and queried in Supabase pgvector.
- **Graph investigation (implemented)** — Neo4j relationship model (people ↔ organizations ↔
  documents ↔ events, every edge carrying chunk-level provenance) enabling "who communicated
  with whom about what, when" expansion around retrieved evidence.
- **Hybrid Graph RAG orchestration (implemented)** — deterministic LangChain pipeline: vector
  hits seed graph expansion, results interleave with full evidence trails, and the vector leg
  keeps working (with an explicit notice) if Neo4j is unavailable.
- **Investigation dashboard (implemented)** — Streamlit UI with cited evidence (vector/graph
  source badges, cosine scores, graph evidence trails), an interactive Plotly entity graph,
  an extracted-event timeline, an evaluation metrics panel, and explicit degraded states when
  a backend is down. No LLM answer generation — evidence only.
- **Reproducible evaluation** — gold-labeled synthetic corpus scored for extraction and
  retrieval precision/recall/F1 (see [docs/DATA_AND_EVALUATION.md](docs/DATA_AND_EVALUATION.md)).

## Technology Stack

| Layer | Technology |
|---|---|
| Language / tooling | Python 3.12, [uv](https://docs.astral.sh/uv/), Ruff, pytest, Hatchling (src layout) |
| UI | Streamlit, Plotly |
| Orchestration | LangChain |
| Embeddings | Hugging Face sentence-transformers |
| Vector store | PostgreSQL + pgvector (hosted on Supabase) |
| Graph store | Neo4j AuraDB (official Neo4j Python driver) |
| Extraction | spaCy + deterministic regex |
| Data contracts | Pydantic / Pydantic Settings, SQLAlchemy + psycopg |
| Hosting | Streamlit Community Cloud, GitHub |

Architecture details: [docs/architecture.md](docs/architecture.md) · Data model:
[docs/DATA_MODEL.md](docs/DATA_MODEL.md) · Decisions (ADRs): [docs/decisions.md](docs/decisions.md)

## Local Setup

Requires [uv](https://docs.astral.sh/uv/getting-started/installation/) (no pip, no system
Python installs).

```bash
git clone https://github.com/vaibhavkhuranaaa/legal-discovery-intelligence-graph.git
cd legal-discovery-intelligence-graph
uv sync                    # create .venv and install locked dependencies
cp .env.example .env       # fill in backend credentials when cloud milestones begin

uv run pytest              # tests
uv run ruff check .        # lint
uv run python scripts/bootstrap_data.py    # generate the synthetic corpus + gold labels
uv run python scripts/evaluate_extraction.py   # extraction P/R/F1 -> artifacts/
uv run python scripts/index_pgvector.py        # embed + index Supabase (needs DATABASE_URL)
uv run python scripts/load_neo4j.py            # extract + load AuraDB graph (needs NEO4J_*)
uv run python scripts/evaluate_retrieval.py    # vector vs graph-expanded P/R/hit@k -> artifacts/
uv run streamlit run src/legal_discovery_graph/ui/streamlit_app.py   # investigation dashboard
```

`bootstrap_data.py` deterministically generates the fictional "Project Falcon" investigation
corpus (111 documents at the default seed) with exact gold labels — 583 entity mentions,
12 events, and 32 categorized retrieval queries (including 4 negative queries for refusal
evaluation) — see
[docs/DATA_AND_EVALUATION.md](docs/DATA_AND_EVALUATION.md). The dashboard shows retrieved,
cited evidence with per-chunk graph evidence trails, an entity graph, the extracted event
timeline, and the evaluation metrics — it does not generate LLM answers. Without configured
backends it renders explicit degraded states (search disabled, timeline notice, "run the
evaluation command" empty states) rather than empty results.

## Planned Deployment

The application will be deployed publicly: **Streamlit Community Cloud** (app), **Supabase**
(PostgreSQL + pgvector), and **Neo4j AuraDB** (graph), with secrets managed via Streamlit
secrets. Procedure and smoke-test checklist: [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).
`requirements.txt` is generated from `uv.lock` (`uv export`) solely for Streamlit Community
Cloud; `pyproject.toml` + `uv.lock` remain the dependency source of truth.

## Security & Data Disclaimer

All documents, people, companies, amounts, and events in this project are **synthetic and
fictional**, generated by `scripts/bootstrap_data.py`. No real, confidential, or client data is
used anywhere. No credentials are committed; `.env.example` and
`.streamlit/secrets.toml.example` contain blank placeholders only.

## License

[MIT](LICENSE)
