"""Flask investigation web app — the product UI (ADR: Flask over Streamlit).

The app is presentation-only: all data access goes through
:mod:`legal_discovery_graph.ui.backend`, shaping stays in
:mod:`legal_discovery_graph.ui.presenters`, and figures in
:mod:`legal_discovery_graph.ui.figures`. Templates and the hand-written CSS
design system live inside this package (``templates/``, ``static/``).

Run locally with::

    uv run flask --app legal_discovery_graph.webapp run
"""

import os

from flask import Flask

from legal_discovery_graph.webapp.routes import bp


def create_app() -> Flask:
    """Application factory: build the Flask app with the webapp blueprint."""
    app = Flask(__name__)
    app.register_blueprint(bp)

    @app.get("/healthz")
    def healthz() -> dict[str, str | None]:
        return {
            "status": "ok",
            "service": "legal-discovery-intelligence-graph",
            "source_sha": os.getenv("RENDER_GIT_COMMIT"),
        }

    return app
