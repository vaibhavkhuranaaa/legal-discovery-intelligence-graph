# Legal Discovery Intelligence Graph

**GitHub:** [vaibhavkhuranaaa/legal-discovery-intelligence-graph](https://github.com/vaibhavkhuranaaa/legal-discovery-intelligence-graph)

> **Status: in development — Milestones 0–3 of 6 complete.** Foundation, the synthetic corpus
> generator (deterministic corpus + gold labels), entity/event extraction, and vector-only
> pgvector retrieval with reproducible evaluation are done; graph expansion, dashboard, and
> public deployment remain (see [docs/roadmap.md](docs/roadmap.md)).
> No live URL exists yet — none is claimed.
>
> **Measured results** (synthetic corpus, seed 42):
> entity-mention extraction micro **F1 0.889 strict / 0.903 relaxed**; event extraction
> **F1 1.000**; vector-only retrieval **R@5 0.857 / hit@5 0.893** and **R@10 0.929 / hit@10
> 0.964**. Reproduce with `bootstrap_data.py`, `evaluate_extraction.py`, `index_pgvector.py`,
> and `evaluate_retrieval.py`; scores are inflated by clean templated text — see
> [docs/DATA_AND_EVALUATION.md](docs/DATA_AND_EVALUATION.md).

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
- **Graph investigation** — Neo4j relationship model (people ↔ organizations ↔ documents ↔
  events) enabling "who communicated with whom about what, when" expansion around retrieved
  evidence.
- **Hybrid Graph RAG orchestration** — LangChain pipeline combining vector retrieval with graph
  expansion so answers carry both semantic evidence and relationship context.
- **Timeline analysis** — dated events plotted with Plotly for case chronology.
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
uv run python scripts/evaluate_retrieval.py    # retrieval P/R/hit@k -> artifacts/
uv run streamlit run src/legal_discovery_graph/ui/streamlit_app.py   # health-check app
```

`bootstrap_data.py` deterministically generates the fictional "Project Falcon" investigation
corpus (111 documents at the default seed) with exact gold labels — 583 entity mentions,
12 events, and 32 categorized retrieval queries (including 4 negative queries for refusal
evaluation) — see
[docs/DATA_AND_EVALUATION.md](docs/DATA_AND_EVALUATION.md). The health-check app currently
renders "Legal Discovery Intelligence Graph — Foundation Ready"; investigation features land in
later milestones.

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
