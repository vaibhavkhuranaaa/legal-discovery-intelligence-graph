"""Route tests for the Flask investigation web app.

Everything runs without live Supabase/AuraDB or model downloads: searches are
exercised by monkeypatching the routes' cached search hook with fabricated
``HybridResult`` values, mirroring the approach in ``test_ui.py``.
"""

from datetime import UTC, datetime

import pytest
from flask.testing import FlaskClient

from legal_discovery_graph.graph import GraphEvidence, TimelineEvent
from legal_discovery_graph.retrieval import HybridResult, RankedChunk
from legal_discovery_graph.retrieval.store import RetrievedChunk
from legal_discovery_graph.ui import backend
from legal_discovery_graph.webapp import create_app, routes


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> FlaskClient:
    # The timeline page fetches from Neo4j on GET; default to "unavailable"
    # so no test ever attempts a live connection unless it overrides this.
    monkeypatch.setattr(
        routes,
        "_timeline_cached",
        lambda bucket: backend.TimelineOutcome(events=(), error="Neo4j unreachable (stub)"),
    )
    # Fabricated results carry empty vector_hits (top similarity 0.0), which the
    # calibrated default threshold would refuse; disable refusal unless a test
    # opts in via _stub_settings.
    _stub_settings(monkeypatch, refusal_threshold=0.0)
    # Audit I/O never touches a live database in tests.
    monkeypatch.setattr(backend, "record_search_audit", lambda **kwargs: None)
    monkeypatch.setattr(
        backend,
        "fetch_search_audit",
        lambda limit=50: backend.AuditOutcome(rows=(), error=None),
    )
    app = create_app()
    app.config.update(TESTING=True)
    return app.test_client()


@pytest.fixture
def configured_db(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        backend,
        "backend_status",
        lambda: backend.BackendStatus(
            database_configured=True, graph_configured=True, embedding_model="test-model"
        ),
    )


def _chunk(chunk_id: str, score: float = 0.0) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id=f"doc-{chunk_id}",
        sequence=0,
        text=f"body of {chunk_id}",
        metadata={"title": "Falcon memo", "doc_type": "memo"},
        score=score,
    )


def _evidence(chunk_id: str) -> GraphEvidence:
    return GraphEvidence(
        entity_id="id-omar",
        entity_name="Omar Tran",
        relation="co_mentioned",
        document_id=f"doc-{chunk_id}",
        source_chunk_id="seed-chunk-0000",
        chunk_id=chunk_id,
    )


def _result(
    ranked: tuple[RankedChunk, ...],
    graph_available: bool = True,
    vector_hits: tuple[RetrievedChunk, ...] = (),
) -> HybridResult:
    return HybridResult(
        question="who paid?",
        ranked=ranked,
        vector_hits=vector_hits,
        graph_hits=(),
        graph_available=graph_available,
        graph_error=None if graph_available else "Neo4j unreachable",
    )


def _stub_settings(monkeypatch: pytest.MonkeyPatch, refusal_threshold: float) -> None:
    from types import SimpleNamespace

    monkeypatch.setattr(
        routes,
        "get_settings",
        lambda: SimpleNamespace(
            refusal_threshold=refusal_threshold, counsel_domains="hartwellpace.example"
        ),
    )


def _stub_search(monkeypatch: pytest.MonkeyPatch, outcome: backend.InvestigationOutcome) -> None:
    monkeypatch.setattr(routes, "_search", lambda question, limit: outcome)


def _event(day: int, description: str) -> TimelineEvent:
    return TimelineEvent(
        event_id=f"ev-{day}",
        occurred_at=datetime(2024, 3, day, tzinfo=UTC),
        description=description,
        document_id="doc-1",
        document_title="Audit memo",
        chunk_id="chunk-1",
        entity_names=("Omar Tran",),
    )


@pytest.mark.parametrize(
    ("path", "heading"),
    [
        ("/", "The Project Falcon matter"),
        ("/investigate", "Investigate"),
        ("/graph", "Entity graph"),
        ("/timeline", "Timeline"),
        ("/audit", "Audit trail"),
        ("/evaluation", "Evaluation"),
    ],
)
def test_page_renders_with_heading(client: FlaskClient, path: str, heading: str) -> None:
    response = client.get(path)
    assert response.status_code == 200
    assert f"<h1>{heading}</h1>" in response.text


def test_layout_has_nav_and_status_pills(client: FlaskClient) -> None:
    response = client.get("/")
    assert response.status_code == 200
    for href in ("/investigate", "/graph", "/timeline", "/evaluation"):
        assert f'href="{href}"' in response.text
    # Status pills render regardless of configuration and never leak secrets.
    assert "pgvector" in response.text
    assert "Neo4j" in response.text


def test_stylesheet_is_served(client: FlaskClient) -> None:
    response = client.get("/static/css/theme.css")
    assert response.status_code == 200
    assert "--paper" in response.text


def test_unknown_route_is_404(client: FlaskClient) -> None:
    assert client.get("/nope").status_code == 404


class TestInvestigateSearch:
    def test_unconfigured_database_disables_search(
        self, client: FlaskClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            backend,
            "backend_status",
            lambda: backend.BackendStatus(
                database_configured=False, graph_configured=False, embedding_model="test-model"
            ),
        )
        response = client.get("/investigate?q=who+paid")
        assert response.status_code == 200
        assert "DATABASE_URL" in response.text
        assert "evidence-card" not in response.text

    def test_results_render_cards_with_provenance(
        self, client: FlaskClient, configured_db: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ranked = (
            RankedChunk(_chunk("v1", 0.91), fused_score=1.0, sources=("vector",), evidence=()),
            RankedChunk(
                _chunk("g1"), fused_score=0.8, sources=("graph",), evidence=(_evidence("g1"),)
            ),
        )
        _stub_search(monkeypatch, backend.InvestigationOutcome(result=_result(ranked), error=None))
        response = client.get("/investigate?q=who+paid&limit=5")
        assert response.status_code == 200
        assert response.text.count("evidence-card") == 2
        assert "cosine 0.910" in response.text  # vector hit shows similarity
        assert "Omar Tran" in response.text  # graph trail rendered
        # Citations are client-facing: title · doc type · passage — never hash IDs.
        assert "Falcon memo · memo · passage 1" in response.text
        # Each citation links to the full source document; the document ID
        # appears only inside those hrefs, never as visible text.
        assert 'href="/document/doc-v1"' in response.text
        assert response.text.count("doc-v1") == response.text.count("/document/doc-v1")
        assert "seed-chunk-0000" not in response.text
        assert "1 contributed by graph expansion" in response.text
        assert "How to read this evidence" in response.text  # collapsed glossary panel

    def test_graph_degradation_shows_warning_with_reason(
        self, client: FlaskClient, configured_db: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ranked = (
            RankedChunk(_chunk("v1", 0.5), fused_score=1.0, sources=("vector",), evidence=()),
        )
        _stub_search(
            monkeypatch,
            backend.InvestigationOutcome(
                result=_result(ranked, graph_available=False), error=None
            ),
        )
        response = client.get("/investigate?q=who+paid")
        assert "Graph expansion is unavailable" in response.text
        assert "Neo4j unreachable" in response.text
        assert response.text.count("evidence-card") == 1

    def test_search_failure_is_an_explicit_error(
        self, client: FlaskClient, configured_db: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub_search(
            monkeypatch,
            backend.InvestigationOutcome(result=None, error="OperationalError: db down"),
        )
        response = client.get("/investigate?q=who+paid")
        assert "Investigation search failed" in response.text
        assert "OperationalError: db down" in response.text

    def test_empty_results_point_to_indexing_command(
        self, client: FlaskClient, configured_db: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub_search(monkeypatch, backend.InvestigationOutcome(result=_result(()), error=None))
        response = client.get("/investigate?q=who+paid")
        assert "No evidence was retrieved" in response.text
        assert "index_pgvector.py" in response.text

    def test_below_threshold_search_is_refused_with_override_link(
        self, client: FlaskClient, configured_db: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ranked = (
            RankedChunk(_chunk("v1", 0.31), fused_score=1.0, sources=("vector",), evidence=()),
        )
        result = _result(ranked, vector_hits=(_chunk("v1", 0.31),))
        _stub_search(monkeypatch, backend.InvestigationOutcome(result=result, error=None))
        _stub_settings(monkeypatch, refusal_threshold=0.5)
        response = client.get("/investigate?q=unsupported+question")
        assert "No supporting evidence found" in response.text
        assert "evidence-card" not in response.text
        assert "all=1" in response.text  # override link offered

    def test_refusal_override_shows_matches_with_warning(
        self, client: FlaskClient, configured_db: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ranked = (
            RankedChunk(_chunk("v1", 0.31), fused_score=1.0, sources=("vector",), evidence=()),
        )
        result = _result(ranked, vector_hits=(_chunk("v1", 0.31),))
        _stub_search(monkeypatch, backend.InvestigationOutcome(result=result, error=None))
        _stub_settings(monkeypatch, refusal_threshold=0.5)
        response = client.get("/investigate?q=unsupported+question&all=1")
        assert response.text.count("evidence-card") == 1
        assert "below the calibrated evidence threshold" in response.text

    def test_above_threshold_search_is_not_refused(
        self, client: FlaskClient, configured_db: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ranked = (
            RankedChunk(_chunk("v1", 0.82), fused_score=1.0, sources=("vector",), evidence=()),
        )
        result = _result(ranked, vector_hits=(_chunk("v1", 0.82),))
        _stub_search(monkeypatch, backend.InvestigationOutcome(result=result, error=None))
        _stub_settings(monkeypatch, refusal_threshold=0.5)
        response = client.get("/investigate?q=who+paid")
        assert response.text.count("evidence-card") == 1
        assert "No supporting evidence found" not in response.text

    def test_privilege_and_pii_flags_render_badges(
        self, client: FlaskClient, configured_db: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        chunk = RetrievedChunk(
            chunk_id="p1",
            document_id="doc-p1",
            sequence=0,
            text=(
                "PRIVILEGED AND CONFIDENTIAL — remit to account number 0004482913 "
                "for the retainer."
            ),
            metadata={"title": "Counsel email", "doc_type": "email"},
            score=0.9,
        )
        ranked = (RankedChunk(chunk, fused_score=1.0, sources=("vector",), evidence=()),)
        _stub_search(monkeypatch, backend.InvestigationOutcome(result=_result(ranked), error=None))
        response = client.get("/investigate?q=who+paid")
        assert "potentially privileged" in response.text
        assert "PII: bank account" in response.text

    def test_invalid_limit_falls_back_to_default(
        self, client: FlaskClient, configured_db: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        seen: list[int] = []

        def capture(question: str, limit: int) -> backend.InvestigationOutcome:
            seen.append(limit)
            return backend.InvestigationOutcome(result=_result(()), error=None)

        monkeypatch.setattr(routes, "_search", capture)
        client.get("/investigate?q=x&limit=999")
        client.get("/investigate?q=x&limit=abc")
        assert seen == [10, 10]


class TestCasePage:
    def test_tour_links_prefill_investigate_searches(self, client: FlaskClient) -> None:
        response = client.get("/")
        assert response.status_code == 200
        # Every tour step is a prefilled search link against /investigate.
        assert response.text.count('class="tour-question"') == len(routes.TOUR_STEPS)
        assert "/investigate?q=" in response.text
        assert "Who+approved+the+award+of+the+Project+Falcon+contract" in response.text

    def test_brief_glossary_and_verify_sections_render(self, client: FlaskClient) -> None:
        response = client.get("/")
        assert "455 synthetic documents" in response.text
        assert "How to read the evidence" in response.text
        assert 'class="glossary"' in response.text  # shared include
        assert "How to verify the output" in response.text
        assert "bootstrap_data.py" in response.text
        assert "spoiler" in response.text  # full story stays collapsed in a details


class TestDocumentPage:
    def test_document_renders_metadata_flags_and_passages(
        self, client: FlaskClient, configured_db: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        document = {
            "document_id": "doc-p1",
            "doc_type": "email",
            "title": "Engagement of outside counsel",
            "custodian": "Marcus Webb",
            "sent_at": datetime(2023, 11, 9, tzinfo=UTC),
            "passages": [
                {"sequence": 0, "text": "PRIVILEGED AND CONFIDENTIAL — engagement letter."},
                {"sequence": 1, "text": "Scope of the review is attached."},
            ],
        }
        monkeypatch.setattr(
            backend,
            "fetch_document_view",
            lambda document_id: backend.DocumentOutcome(document=document, error=None),
        )
        response = client.get("/document/doc-p1")
        assert response.status_code == 200
        assert "<h1>Engagement of outside counsel</h1>" in response.text
        assert "Marcus Webb" in response.text
        assert "November 9, 2023" in response.text
        assert "potentially privileged" in response.text  # flags run over the full text
        assert response.text.count("evidence-card") == 2  # one card per passage
        assert "Passage 2" in response.text
        assert "synthetic" in response.text  # provenance disclaimer

    def test_unknown_document_is_an_explicit_not_found(
        self, client: FlaskClient, configured_db: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            backend,
            "fetch_document_view",
            lambda document_id: backend.DocumentOutcome(document=None, error=None),
        )
        response = client.get("/document/nope")
        assert response.status_code == 200
        assert "No document with this identifier" in response.text

    def test_store_failure_is_an_explicit_error(
        self, client: FlaskClient, configured_db: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            backend,
            "fetch_document_view",
            lambda document_id: backend.DocumentOutcome(
                document=None, error="OperationalError: db down"
            ),
        )
        response = client.get("/document/doc-1")
        assert "could not be loaded" in response.text
        assert "OperationalError: db down" in response.text

    def test_unconfigured_database_shows_reason(
        self, client: FlaskClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            backend,
            "backend_status",
            lambda: backend.BackendStatus(
                database_configured=False, graph_configured=False, embedding_model="test-model"
            ),
        )
        response = client.get("/document/doc-1")
        assert "DATABASE_URL is not configured" in response.text


class TestGraphPage:
    def test_without_question_prompts_for_investigation(
        self, client: FlaskClient, configured_db: None
    ) -> None:
        response = client.get("/graph")
        assert response.status_code == 200
        assert "Enter an investigative question" in response.text

    def test_graph_evidence_renders_cytoscape_canvas(
        self, client: FlaskClient, configured_db: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ranked = (
            RankedChunk(
                _chunk("g1"), fused_score=0.8, sources=("graph",), evidence=(_evidence("g1"),)
            ),
        )
        _stub_search(monkeypatch, backend.InvestigationOutcome(result=_result(ranked), error=None))
        response = client.get("/graph?q=who+paid")
        assert 'id="cy"' in response.text
        assert "cytoscape-3.30.4.min.js" in response.text
        assert "Omar Tran" in response.text  # element JSON carries real node labels
        assert "co-mentioned with" in response.text  # relation label with provenance

    def test_no_relationships_draws_nothing(
        self, client: FlaskClient, configured_db: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ranked = (
            RankedChunk(_chunk("v1", 0.9), fused_score=1.0, sources=("vector",), evidence=()),
        )
        _stub_search(monkeypatch, backend.InvestigationOutcome(result=_result(ranked), error=None))
        response = client.get("/graph?q=who+paid")
        assert "No graph relationships were found" in response.text
        assert 'id="cy"' not in response.text

    def test_vendored_cytoscape_is_served(self, client: FlaskClient) -> None:
        response = client.get("/static/js/cytoscape-3.30.4.min.js")
        assert response.status_code == 200
        assert len(response.data) > 300_000


class TestTimelinePage:
    def test_graph_unavailable_shows_reason(self, client: FlaskClient) -> None:
        response = client.get("/timeline")
        assert "Neo4j unreachable (stub)" in response.text

    def test_events_render_rail_and_citation_table(
        self, client: FlaskClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        events = (_event(3, "Wire transfer approved"), _event(5, "Audit opened"))
        monkeypatch.setattr(
            routes,
            "_timeline_cached",
            lambda bucket: backend.TimelineOutcome(events=events, error=None),
        )
        response = client.get("/timeline")
        assert response.text.count("rail-event") == 2  # one card per event
        assert "March 2024" in response.text  # month bucket label
        assert "Wire transfer approved" in response.text
        assert "Omar Tran" in response.text  # entity chip
        assert "Audit memo" in response.text
        assert 'href="/document/doc-1"' in response.text  # citation links to the source
        assert "chunk-1" not in response.text  # internal IDs never render
        assert response.text.count("<tr>") == 3  # table fallback: header + 2 events

    def test_no_events_points_to_load_command(
        self, client: FlaskClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            routes,
            "_timeline_cached",
            lambda bucket: backend.TimelineOutcome(events=(), error=None),
        )
        response = client.get("/timeline")
        assert "load_neo4j.py" in response.text


class TestAuditPage:
    def test_search_is_recorded_with_refusal_outcome(
        self, client: FlaskClient, configured_db: None, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        recorded: list[dict] = []
        monkeypatch.setattr(
            backend, "record_search_audit", lambda **kwargs: recorded.append(kwargs)
        )
        ranked = (
            RankedChunk(_chunk("v1", 0.31), fused_score=1.0, sources=("vector",), evidence=()),
        )
        result = _result(ranked, vector_hits=(_chunk("v1", 0.31),))
        _stub_search(monkeypatch, backend.InvestigationOutcome(result=result, error=None))
        _stub_settings(monkeypatch, refusal_threshold=0.5)
        client.get("/investigate?q=unsupported+question")
        assert len(recorded) == 1
        assert recorded[0]["question"] == "unsupported question"
        assert recorded[0]["refused"] is True
        assert recorded[0]["result_count"] == 1

    def test_rows_render_in_table(
        self,
        client: FlaskClient,
        configured_db: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        rows = (
            {
                "searched_at": datetime(2026, 7, 15, 9, 30, 12, tzinfo=UTC),
                "question": "Who approved the payments?",
                "result_limit": 10,
                "result_count": 10,
                "refused": False,
                "graph_available": True,
                "duration_ms": 412,
            },
            {
                "searched_at": datetime(2026, 7, 15, 9, 31, 40, tzinfo=UTC),
                "question": "Were there whistleblower complaints?",
                "result_limit": 10,
                "result_count": 10,
                "refused": True,
                "graph_available": True,
                "duration_ms": 96,
            },
        )
        monkeypatch.setattr(
            backend,
            "fetch_search_audit",
            lambda limit=50: backend.AuditOutcome(rows=rows, error=None),
        )
        response = client.get("/audit")
        assert "Who approved the payments?" in response.text
        assert "refused (below threshold)" in response.text
        assert "evidence shown" in response.text
        assert "412 ms" in response.text

    def test_unavailable_store_shows_reason(
        self,
        client: FlaskClient,
        configured_db: None,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(
            backend,
            "fetch_search_audit",
            lambda limit=50: backend.AuditOutcome(rows=(), error="OperationalError: db down"),
        )
        response = client.get("/audit")
        assert "could not be read" in response.text
        assert "OperationalError: db down" in response.text

    def test_unconfigured_store_is_explicit(
        self, client: FlaskClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            backend,
            "backend_status",
            lambda: backend.BackendStatus(
                database_configured=False,
                graph_configured=False,
                embedding_model="test-model",
            ),
        )
        response = client.get("/audit")
        assert response.status_code == 200
        assert "could not be read" in response.text
        assert "DATABASE_URL is not configured" in response.text


class TestEvaluationPage:
    def test_committed_artifacts_render_score_chart_and_details(
        self, client: FlaskClient
    ) -> None:
        # Uses the real committed artifacts in artifacts/ — no fabrication.
        import json
        from pathlib import Path

        response = client.get("/evaluation")
        assert response.status_code == 200
        assert "Total model score" in response.text
        # The hero number must equal the hand-computed mean of the artifacts.
        extraction = json.loads(Path("artifacts/extraction_metrics.json").read_text())
        retrieval = json.loads(Path("artifacts/retrieval_metrics.json").read_text())
        overall = retrieval["graph_expanded"]["overall"]["@10"]
        expected = (
            extraction["mentions_strict"]["micro"]["f1"]
            + extraction["events"]["f1"]
            + overall["recall"]
            + overall["hit_rate"]
        ) / 4
        assert f'<span class="score-value">{expected:.3f}</span>' in response.text
        assert response.text.count('class="stat"') == 4  # the four components
        assert 'id="retrieval-comparison"' in response.text
        assert "Per-type detail" in response.text
        assert "Graph-expanded (hybrid)" in response.text

    def test_missing_artifacts_show_generation_commands(
        self, client: FlaskClient, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(backend, "load_metrics_artifact", lambda path: None)
        response = client.get("/evaluation")
        assert "evaluate_extraction.py" in response.text
        assert "evaluate_retrieval.py" in response.text
        assert "Total model score" not in response.text  # never invented
        assert 'id="retrieval-comparison"' not in response.text


class TestTotalScore:
    def test_mean_of_four_components(self) -> None:
        from legal_discovery_graph.webapp.scores import total_model_score

        extraction = {
            "mentions_strict": {"micro": {"f1": 0.8}},
            "events": {"f1": 1.0},
        }
        retrieval = {"graph_expanded": {"overall": {"@10": {"recall": 0.9, "hit_rate": 0.7}}}}
        score = total_model_score(extraction, retrieval)
        assert score is not None
        assert score.total == pytest.approx((0.8 + 1.0 + 0.9 + 0.7) / 4)

    def test_missing_artifact_or_key_yields_none(self) -> None:
        from legal_discovery_graph.webapp.scores import total_model_score

        assert total_model_score(None, {}) is None
        assert total_model_score({}, None) is None
        assert total_model_score({"mentions_strict": {}}, {"graph_expanded": {}}) is None


def test_plotly_bundle_is_served_locally(client: FlaskClient) -> None:
    response = client.get("/vendor/plotly.js")
    assert response.status_code == 200
    assert response.mimetype == "application/javascript"
    assert len(response.data) > 1_000_000  # the real bundle, not an error page
