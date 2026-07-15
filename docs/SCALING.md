# Scaling & Tier Limitations

This project runs entirely on free tiers by design (portfolio project, $0/month). This
document states exactly what those tiers constrain, what breaks at real eDiscovery scale, and
the paid path — so no claim anywhere in the repo exceeds what the deployment actually delivers.

## Current free-tier limits (measured/observed, July 2026)

| Service | Tier limit | Observed effect here |
|---|---|---|
| Render (Flask UI) | 512 MB RAM, sleeps after ~15 min idle, 750 instance-hrs/mo, no persistent disk, no workers | torch OOM'd (ADR-0015 → ONNX, 362 MB RSS); cold start re-downloads the embedding model (~1 min first search); all ingestion/indexing must run offline |
| Supabase (PostgreSQL + pgvector) | 500 MB database, pauses after ~7 days inactivity, no PITR backups | caps the corpus at roughly low-tens-of-thousands of chunks; a paused project breaks live search until manually resumed; no point-in-time recovery for the audit trail |
| Neo4j AuraDB | 200k nodes / 400k relationships, pauses after ~3 days inactivity, no backups/export | fine at current scale (614 nodes / 1,956 relationships); pausing is the most fragile piece of the live demo |
| Streamlit Community Cloud (legacy UI) | aggressive sleep, public apps only | first load is slow; acceptable for the legacy dashboard |

The `keep-alive.yml` GitHub Actions workflow pings the app every 10 minutes (Render) and runs
one daily request against `/audit` (PostgreSQL query) and `/timeline` (Neo4j query) so neither
database pauses. This is a workaround, not reliability engineering: Actions cron runs are
best-effort and can be delayed or skipped.

## What breaks at real eDiscovery scale

A real matter runs 100k–millions of documents with OCR, deduplication, privilege review, and
defensibility requirements. On these tiers:

- **Corpus size** — 500 MB Supabase caps document count at "demo matter" scale (~a few
  thousand documents with 384-dim vectors). HNSW index build time and memory also grow.
- **Ingestion throughput** — no background workers on Render free; `ingest_files.py`,
  `index_pgvector.py`, and `load_neo4j.py` must run from an operator machine.
- **Durability/chain of custody** — no database backups on either free tier. The append-only
  `audit_log` table and the ingestion manifest exist, but a lost database loses both.
- **Latency** — cold starts (~1 min) are unacceptable for an investigator mid-review.
- **Security** — no authentication in the app (documented limitation; `actor` column reserved
  in `audit_log`), and free tiers offer no compliance posture (SOC 2 reports exist for the
  vendors, but access controls here are nonexistent by design — synthetic data only).

## Paid path (if this were productized)

| Upgrade | Cost (July 2026) | What it buys |
|---|---|---|
| Render Starter | $7/mo | no sleep — kills cold starts; the single most valuable upgrade |
| Render Standard | $25/mo | 2 GB RAM — torch serving and small in-app ingestion become possible |
| Supabase Pro | $25/mo | 8 GB database, 7-day PITR backups — real corpus sizes, durable audit trail |
| Neo4j AuraDB Professional | from ~$65/mo | no pausing, backups, larger graphs |

Order of value: Render Starter → Supabase Pro → AuraDB Professional. None are needed for the
portfolio deployment; the app is architected (offline processing, read-only serving, explicit
degraded states) so that upgrading tiers requires no code changes.
