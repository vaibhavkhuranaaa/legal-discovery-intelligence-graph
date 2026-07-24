# Legal Discovery Intelligence Graph agent contract

## Authority

- Current implementation and release state: `docs/STATE.md`.
- Continuation instructions: `docs/HANDOFF.md`.
- Architecture, decisions, product scope, and deployment: `docs/PROJECT_CONTEXT.md`, `docs/roadmap.md`, `docs/architecture.md`, `docs/decisions.md`, `docs/product.md`, and deployment records.
- Public facts, evidence, disclosure, deployment classification, and résumé candidates: `portfolio/project.json`.
- Engineering, Python, AI, Git, portfolio, debugging, and deployment rules: the numbered files in `docs/standards/`.

## Working rules

- Query fresh `graphify-out/` context first when it covers the relevant files; otherwise inspect source directly.
- Use only synthetic, public-safe corpus data. Never introduce real discovery, client, confidential, privileged, or personal matter data.
- Do not promote extraction/retrieval metrics or root reachability into legal accuracy, availability, confidentiality, security, or production-readiness claims.
- Preserve unrelated dirty work. Use Python 3.12+, `uv`, `pyproject.toml`, the `src/` layout, Pydantic contracts, and deterministic tests.
- `requirements.txt` is a generated hosting artifact; never hand-edit it.
- Use purpose branches, conventional commits, and the configured human identity only; never add AI/model author or co-author attribution.
- Merging a completed release to `main` authorizes Render deployment after checks pass, live-SHA verification, and portfolio synchronization. New paid capacity and backend changes remain owner-gated.
- Delegation is optional and must be bounded.

Run Ruff and the repository tests before handoff. Update state, handoff, architecture/ADR documentation, deployment evidence, and the manifest whenever their owning facts change.
