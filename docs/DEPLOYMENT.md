# Deployment

Planned deployment procedure. **Nothing is deployed yet** — no cloud accounts, services, or
secrets exist for this project. This document becomes the runbook at the deployment milestone
and is updated with verified steps as they are executed.

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

## Planned Procedure

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
   `src/legal_discovery_graph/ui/streamlit_app.py`, paste secrets, deploy.
7. **Run the smoke-test checklist** below, then record the verified URL in `README.md`.

## Smoke-Test Checklist (post-deploy)

`scripts/verify_deployment.py` will automate these; each must pass before the deployment is
claimed anywhere:

- [ ] App URL loads without error in a fresh browser session.
- [ ] Startup health check reports Postgres and Neo4j both reachable.
- [ ] A known gold query returns cited chunks (pgvector round-trip).
- [ ] Entity graph panel renders a subgraph for a known entity (Neo4j round-trip).
- [ ] Timeline renders events for the demo scenario.
- [ ] Evaluation page shows the committed metrics run.
- [ ] No secret values appear in logs, page source, or error states.
- [ ] Cold-start behavior acceptable (embedding model load surfaced gracefully).

## Rollback

Community Cloud redeploys from a chosen branch/commit — rollback is reverting the commit and
rebooting the app. Database schema changes must be additive during this project's lifetime so an
older app version remains compatible.
