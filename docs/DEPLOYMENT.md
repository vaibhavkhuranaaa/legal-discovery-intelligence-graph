# Deployment

Verified deployment runbook. The public app is live at
`https://legal-discovery-intelligence-graph-ma2dfvnresf84ytk4nzelm.streamlit.app/`.

## Target Topology

| Service | Role | Tier |
|---|---|---|
| Streamlit Community Cloud | Hosts the Streamlit app from the GitHub repo | Free |
| Supabase | Managed PostgreSQL with pgvector extension | Free |
| Neo4j AuraDB | Managed graph database | Free |
| GitHub | Source of truth; Community Cloud deploys from it | Free |

The deployed app is **read-only** against both stores; indexing runs from the developer machine
(`scripts/index_pgvector.py`, `scripts/load_neo4j.py`).

## Required Secrets

Configured in Streamlit Community Cloud → App settings → Secrets (never committed; template in
`.streamlit/secrets.toml.example`):

| Key | Purpose |
|---|---|
| `DATABASE_URL` | Supabase Postgres connection string (pooler URL, `postgresql+psycopg://…`) |
| `NEO4J_URI` | AuraDB connection URI (`neo4j+s://…`) |
| `NEO4J_USERNAME` / `NEO4J_PASSWORD` | AuraDB credentials |
| `EMBEDDING_MODEL_NAME` | Optional override of the default sentence-transformer |
| `APP_ENV` / `LOG_LEVEL` | Optional runtime behavior |

Locally the same keys live in `.env` (template: `.env.example`).

## Verified Procedure

1. **Provision Supabase** — create project, enable the `vector` extension, apply the schema from
   `DATA_MODEL.md`, note the pooled connection string.
2. **Provision Neo4j AuraDB Free** — create instance, save generated credentials, apply
   uniqueness constraints via `scripts/load_neo4j.py`.
3. **Index data from the dev machine** — `uv run python scripts/bootstrap_data.py`, then
   `scripts/index_pgvector.py` and `scripts/load_neo4j.py` against the cloud backends.
4. **Publish GitHub repository** — confirm no secrets tracked (`git log`/`gitleaks`-style
   review), push.
5. **Export requirements** — `uv export --format requirements-txt --no-dev --no-hashes
   -o requirements.txt` (generated artifact; never hand-edited).
6. **Create the Community Cloud app** — point at the repo, main file
   `src/legal_discovery_graph/ui/streamlit_app.py`, explicitly select Python 3.12, paste
   secrets, and deploy. Python 3.14 could not install the pinned spaCy wheel.
7. **Run the smoke-test checklist** below, then record the verified URL in `README.md`.

## Smoke-Test Checklist (post-deploy)

Each item below was checked in a live browser session before the deployment was claimed:

- [x] App URL loads without error.
- [x] Startup health check reports Postgres and Neo4j configured.
- [x] A known relationship query returns cited hybrid evidence.
- [x] Entity graph panel renders a question-scoped subgraph.
- [x] Timeline renders from Neo4j.
- [x] Evaluation page renders committed artifacts.
- [x] Cold-start behavior is surfaced as an in-progress search while the embedding model warms.

## Rollback

Community Cloud redeploys from a chosen branch/commit — rollback is reverting the commit and
rebooting the app. Database schema changes must be additive during this project's lifetime so an
older app version remains compatible.
