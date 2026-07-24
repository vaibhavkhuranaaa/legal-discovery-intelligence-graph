# Handoff

## Minimal resume

Read `AGENTS.md`, `docs/STATE.md`, this file, and only the paths named by the task. Public release uses `portfolio/release.json` and `.github/workflows/deploy.yml`; it verifies the exact Render Git commit before requesting portfolio admission.

Read `AGENTS.md`, `README.md`, `docs/STATE.md`, the v2 manifest, and fresh Graphify output.

Approved public source: `c893da65f17121cf8616f1865f946efec2cf935d`. Rollback baseline is that exact approved commit; do not move the registry pin as part of documentation maintenance. Next action: recreate the ignored virtual environment to remove its stale pre-move script shebang, then re-run repository checks before proposing any new exact-SHA review.

Do not promote root HTTP reachability into an availability, confidentiality, or production-readiness claim.

## Checkpoint 2026-07-24T05:30:31.099Z

Presentation handoff completed for legal-discovery-intelligence-graph.

- `sh -lc .venv/bin/python -m ruff check .` passed in 91 ms.
- `sh -lc .venv/bin/python -m pytest -q` passed in 17047 ms.
- `sh -lc .venv/bin/python -m json.tool portfolio/project.json >/dev/null` passed in 23 ms.
- `node scripts/project-presentation.mjs validate --check` passed in 41 ms.
- `sh -lc ! rg -n '(AKIA[0-9A-Z]{16}|sk-[A-Za-z0-9]{20,}|-----BEGIN (RSA|OPENSSH|EC) PRIVATE KEY-----)' --glob '!uv.lock' --glob '!package-lock.json' .` passed in 14 ms.
- `git diff --check` passed in 9 ms.

Public membership and exact-SHA approval were not changed.
