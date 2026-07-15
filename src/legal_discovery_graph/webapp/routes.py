"""Routes for the investigation web app.

The Investigate page runs real hybrid searches (Phase 2); the Graph,
Timeline, and Evaluation page bodies are filled in by later phases. Routes
never touch database drivers — only :mod:`legal_discovery_graph.ui.backend`
— and searches use GET query parameters so investigations are shareable,
bookmarkable URLs.
"""

import time
from datetime import datetime
from functools import lru_cache

from flask import Blueprint, Response, render_template, request

from legal_discovery_graph.ui import backend
from legal_discovery_graph.ui.presenters import (
    EvidenceRow,
    evidence_rows,
    extraction_table,
    graph_elements,
    retrieval_table,
    timeline_frame,
)
from legal_discovery_graph.webapp.figures import cytoscape_elements, retrieval_comparison_figure
from legal_discovery_graph.webapp.scores import total_model_score

bp = Blueprint("webapp", __name__)

LIMIT_CHOICES = (5, 10, 15, 20)
_DEFAULT_LIMIT = 10


@lru_cache(maxsize=1)
def _retriever():
    """Process-wide retriever singleton (embedding model + connections)."""
    return backend.build_retriever()


@lru_cache(maxsize=128)
def _search(question: str, limit: int) -> backend.InvestigationOutcome:
    """Cache repeated searches for the process lifetime (mirrors st.cache_data)."""
    return backend.run_investigation(_retriever(), question, limit=limit)


def _requested_limit() -> int:
    """Parse the evidence limit from the query string, falling back to the default."""
    try:
        limit = int(request.args.get("limit", _DEFAULT_LIMIT))
    except ValueError:
        return _DEFAULT_LIMIT
    return limit if limit in LIMIT_CHOICES else _DEFAULT_LIMIT


@bp.app_context_processor
def _inject_status() -> dict:
    """Expose backend configuration status to every template (header pills)."""
    return {"status": backend.backend_status()}


@bp.get("/")
def investigate() -> str:
    question = request.args.get("q", "").strip()
    limit = _requested_limit()
    context: dict = {
        "active": "investigate",
        "question": question,
        "limit": limit,
        "limit_choices": LIMIT_CHOICES,
        "searched": False,
        "search_error": None,
        "graph_error": None,
        "rows": [],
        "graph_contributed": 0,
    }
    if question and backend.backend_status().database_configured:
        context["searched"] = True
        outcome = _search(question, limit)
        if outcome.error is not None or outcome.result is None:
            context["search_error"] = outcome.error or "no result returned"
        else:
            result = outcome.result
            rows: list[EvidenceRow] = evidence_rows(result)
            context["rows"] = rows
            context["graph_contributed"] = sum(1 for row in rows if "graph" in row.sources)
            if not result.graph_available:
                context["graph_error"] = result.graph_error or "unknown"
    return render_template("investigate.html", **context)


@bp.get("/graph")
def graph() -> str:
    question = request.args.get("q", "").strip()
    limit = _requested_limit()
    context: dict = {
        "active": "graph",
        "question": question,
        "limit": limit,
        "search_error": None,
        "graph_error": None,
        "elements": None,
        "searched": False,
    }
    if question and backend.backend_status().database_configured:
        context["searched"] = True
        outcome = _search(question, limit)
        if outcome.error is not None or outcome.result is None:
            context["search_error"] = outcome.error or "no result returned"
        else:
            result = outcome.result
            if not result.graph_available:
                context["graph_error"] = result.graph_error or "unknown"
            graph_data = graph_elements(result)
            if graph_data.edges:
                context["elements"] = cytoscape_elements(graph_data)
    return render_template("graph.html", **context)


_TIMELINE_TTL_SECONDS = 60


@lru_cache(maxsize=2)
def _timeline_cached(bucket: int) -> backend.TimelineOutcome:
    """Fetch the timeline at most once per TTL bucket (mirrors st.cache_data ttl=60)."""
    del bucket  # cache key only
    return backend.fetch_timeline()


def _timeline_months(records: list[dict]) -> list[dict]:
    """Group chronological event records into month buckets for the rail view."""
    months: list[dict] = []
    for record in records:
        label = datetime.strptime(record["date"], "%Y-%m-%d").strftime("%B %Y")
        if not months or months[-1]["label"] != label:
            months.append({"label": label, "events": []})
        months[-1]["events"].append(record)
    return months


@bp.get("/timeline")
def timeline() -> str:
    outcome = _timeline_cached(int(time.time() // _TIMELINE_TTL_SECONDS))
    records = timeline_frame(outcome.events).to_dict("records") if outcome.events else []
    return render_template(
        "timeline.html",
        active="timeline",
        timeline_error=outcome.error,
        months=_timeline_months(records),
        records=records,
    )


@lru_cache(maxsize=1)
def _plotlyjs() -> str:
    """The plotly.js bundle shipped inside the installed plotly package (no CDN)."""
    from plotly.offline import get_plotlyjs

    return get_plotlyjs()


@bp.get("/vendor/plotly.js")
def plotly_js() -> Response:
    return Response(
        _plotlyjs(),
        mimetype="application/javascript",
        headers={"Cache-Control": "public, max-age=86400"},
    )


@bp.get("/evaluation")
def evaluation() -> str:
    extraction = backend.load_metrics_artifact(backend.EXTRACTION_METRICS_PATH)
    retrieval = backend.load_metrics_artifact(backend.RETRIEVAL_METRICS_PATH)
    context: dict = {
        "active": "evaluation",
        "extraction": extraction,
        "retrieval": retrieval,
        "figure_json": None,
        "score": total_model_score(extraction, retrieval),
    }
    if extraction is not None:
        rows = extraction_table(extraction, "strict").to_dict("records")
        context["strict_rows"] = [{"label": row["type"], **row} for row in rows]
    if retrieval is not None:
        for key, mode in (("vector_rows", "vector_only"), ("hybrid_rows", "graph_expanded")):
            rows = retrieval_table(retrieval, mode).to_dict("records")
            context[key] = [
                {"label": f"{row['scope']} {row['k']}", **row}
                for row in rows
                if row["k"] in ("@5", "@10")
            ]
        figure = retrieval_comparison_figure(retrieval)
        if figure is not None:
            context["figure_json"] = figure.to_json()
    return render_template("evaluation.html", **context)
