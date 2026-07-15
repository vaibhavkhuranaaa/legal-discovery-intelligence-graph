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

from legal_discovery_graph.config import get_settings
from legal_discovery_graph.review import flag_text
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


def _counsel_domains() -> tuple[str, ...]:
    """Outside-counsel domains for privilege flagging, from settings."""
    raw = get_settings().counsel_domains
    return tuple(domain.strip() for domain in raw.split(",") if domain.strip())


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


# The guided tour on the case page. Questions are verbatim gold queries from
# the generated corpus (datagen/scenario.py), so each step's behavior — badges,
# graph contribution, refusal — is known and reproducible.
TOUR_STEPS: tuple[dict, ...] = (
    {
        "question": "Who approved the award of the Project Falcon contract?",
        "note": (
            "Start where the money went. The award determination surfaces as a "
            "direct match, and each passage shows a vector badge with its "
            "cosine similarity score."
        ),
    },
    {
        "question": "What is the relationship between Daniel Reyes and Crestline Holdings?",
        "note": (
            "A relationship question. Passages with a graph badge were reached "
            "by following entity relationships in the graph. Open a card's "
            "evidence trail to see the stored relations that connected it."
        ),
    },
    {
        "question": "What payments did Northgate make to Crestline Holdings?",
        "note": (
            "Follow the money: the quarterly transfers routed through Crestline "
            "Holdings, corroborated across emails and the audit memo."
        ),
    },
    {
        "question": "When did the internal audit of Project Falcon procurement begin?",
        "note": (
            "The unraveling. Audit and outside-counsel material carries a "
            "\"potentially privileged\" badge: rule-based markers, flagged for "
            "review, never withheld."
        ),
    },
    {
        "question": "What happened to Daniel Reyes after the audit findings?",
        "note": (
            "The consequences. The HR personnel record contains a synthetic "
            "Social Security number, so its passage carries a PII badge."
        ),
    },
    {
        "question": "What criminal charges were filed against Daniel Reyes?",
        "note": (
            "A trick question: the corpus contains no charging documents. "
            "Instead of presenting weak matches as support, the app answers "
            "that no supporting evidence was found."
        ),
    },
)


@bp.get("/")
def case() -> str:
    """Case-study landing page: the matter, the guided tour, how to verify."""
    return render_template("case.html", active="case", tour=TOUR_STEPS)


@bp.get("/document/<document_id>")
def document(document_id: str) -> str:
    """Full source document view — the verification target for every citation."""
    context: dict = {
        "active": "investigate",
        "doc": None,
        "flags": None,
        "document_error": None,
        "not_found": False,
    }
    if not backend.backend_status().database_configured:
        context["document_error"] = "DATABASE_URL is not configured"
    else:
        outcome = backend.fetch_document_view(document_id)
        if outcome.error is not None:
            context["document_error"] = outcome.error
        elif outcome.document is None:
            context["not_found"] = True
        else:
            context["doc"] = outcome.document
            full_text = "\n\n".join(p["text"] for p in outcome.document["passages"])
            context["flags"] = flag_text(full_text, _counsel_domains())
    return render_template("document.html", **context)


@bp.get("/investigate")
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
        "refused": None,
        "below_threshold": False,
    }
    if question and backend.backend_status().database_configured:
        context["searched"] = True
        started = time.perf_counter()
        outcome = _search(question, limit)
        duration_ms = int((time.perf_counter() - started) * 1000)
        if outcome.error is not None or outcome.result is None:
            context["search_error"] = outcome.error or "no result returned"
        else:
            result = outcome.result
            threshold = get_settings().refusal_threshold
            top_similarity = result.vector_hits[0].score if result.vector_hits else 0.0
            show_anyway = request.args.get("all") == "1"
            refused = bool(result.ranked and threshold > 0 and top_similarity < threshold)
            backend.record_search_audit(
                question=question,
                result_limit=limit,
                result_count=len(result.ranked),
                refused=refused,
                graph_available=result.graph_available,
                duration_ms=duration_ms,
            )
            if refused:
                # Calibrated no-evidence state (ADR-0019): refuse rather than
                # present best-effort matches as if they were support.
                if not show_anyway:
                    context["refused"] = {"top": top_similarity, "threshold": threshold}
                    return render_template("investigate.html", **context)
                context["below_threshold"] = True
            rows: list[EvidenceRow] = evidence_rows(result)
            domains = _counsel_domains()
            context["rows"] = [(row, flag_text(row.text, domains)) for row in rows]
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


@bp.get("/audit")
def audit() -> str:
    outcome = (
        backend.fetch_search_audit()
        if backend.backend_status().database_configured
        else backend.AuditOutcome(rows=(), error="DATABASE_URL is not configured")
    )
    return render_template(
        "audit.html",
        active="audit",
        audit_error=outcome.error,
        rows=outcome.rows,
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
    flags = backend.load_metrics_artifact(backend.FLAGS_METRICS_PATH)
    context: dict = {
        "active": "evaluation",
        "extraction": extraction,
        "retrieval": retrieval,
        "flags": flags,
        "refusal": (retrieval or {}).get("refusal_calibration"),
        "figure_json": None,
        "score": total_model_score(extraction, retrieval),
    }
    if flags is not None:
        context["flags_rows"] = [
            {"label": "privileged", **flags["privileged"]},
            *(
                {"label": f"pii · {name}", **scores}
                for name, scores in sorted(flags["pii"].items())
            ),
            {"label": "pii · micro", **flags["pii_micro"]},
        ]
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
