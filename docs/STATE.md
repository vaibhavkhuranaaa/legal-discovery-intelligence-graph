# State

- Lifecycle: `maintained`
- Deployment: `live`
- Exposure: `anonymous`
- Production claim: `false`
- Publication: approved exact v2 source commit `c893da65f17121cf8616f1865f946efec2cf935d`
- Evidence: extraction, retrieval, flags, synthetic disclosure, and a 2026-07-23 root reachability check

The Render root returned HTTP 200 at `2026-07-23T20:52:19Z`. This is reachability evidence only. The corpus is entirely generated and fictional; the public app is not a real-client security or legal-decision system.

Workspace revalidation on 2026-07-23 returned HTTP 200 for both the live provider URL and the unauthenticated GitHub exact-commit page. This preserves the approved source and deployment claims without implying a production SLO.

Migration verification: Ruff passed; `.venv/bin/python -m pytest -q` passed 175 tests with two embedding-parity skips caused by unavailable model clients. The `uv run pytest` launcher has a stale pre-move shebang pointing at the former `Development/Projects` path; recreate the ignored virtual environment separately rather than treating that generated-path issue as a product failure.
