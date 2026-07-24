"""Dashboard tests: presenters, figures, backend outcomes, and app rendering.

Everything runs without live Supabase/AuraDB or model downloads: presenter and
figure tests use fabricated retrieval results, backend tests use stubs, and
the Streamlit app is exercised headless via ``streamlit.testing.v1.AppTest``
with the backend monkeypatched to unconfigured/degraded states.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.exc import OperationalError
from streamlit.testing.v1 import AppTest

from legal_discovery_graph.graph import GraphEvidence, TimelineEvent, timeline_event_from_record
from legal_discovery_graph.retrieval import HybridResult, RankedChunk
from legal_discovery_graph.retrieval.store import RetrievedChunk
from legal_discovery_graph.ui import backend
from legal_discovery_graph.ui.figures import entity_graph_figure, timeline_figure
from legal_discovery_graph.ui.presenters import (
    evidence_rows,
    extraction_table,
    graph_elements,
    retrieval_table,
    timeline_frame,
)

_APP_PATH = str(
    Path(__file__).parent.parent / "src" / "legal_discovery_graph" / "ui" / "streamlit_app.py"
)


def _chunk(chunk_id: str, score: float = 0.0, title: str = "Falcon memo") -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id=f"doc-{chunk_id}",
        sequence=0,
        text=f"body of {chunk_id}",
        metadata={"title": title, "doc_type": "memo"},
        score=score,
    )


def _evidence(chunk_id: str, entity: str = "Omar Tran", relation: str = "co_mentioned"):
    return GraphEvidence(
        entity_id=f"id-{entity}",
        entity_name=entity,
        relation=relation,
        document_id=f"doc-{chunk_id}",
        source_chunk_id="seed-chunk",
        chunk_id=chunk_id,
    )


def _result(ranked: tuple[RankedChunk, ...], graph_available: bool = True) -> HybridResult:
    return HybridResult(
        question="who paid?",
        ranked=ranked,
        vector_hits=(),
        graph_hits=(),
        graph_available=graph_available,
        graph_error=None if graph_available else "Neo4j unreachable",
    )


def _event(day: int, description: str, entities: tuple[str, ...] = ("Omar Tran",)):
    return TimelineEvent(
        event_id=f"ev-{day}",
        occurred_at=datetime(2024, 3, day, tzinfo=UTC),
        description=description,
        document_id="doc-1",
        document_title="Audit memo",
        chunk_id="chunk-1",
        entity_names=entities,
    )


class TestEvidenceRows:
    def test_vector_hit_shows_similarity_and_graph_only_does_not(self):
        ranked = (
            RankedChunk(_chunk("v", 0.91), fused_score=1.0, sources=("vector",), evidence=()),
            RankedChunk(
                _chunk("g", 0.0), fused_score=1.0, sources=("graph",), evidence=(_evidence("g"),)
            ),
        )
        rows = evidence_rows(_result(ranked))
        assert [row.rank for row in rows] == [1, 2]
        assert rows[0].similarity == 0.91
        assert rows[1].similarity is None  # hydrated chunk: no similarity was computed
        assert rows[0].title == "Falcon memo"
        assert rows[1].evidence[0].entity_name == "Omar Tran"

    def test_missing_metadata_falls_back_to_document_id(self):
        chunk = RetrievedChunk("c1", "doc-x", 0, "text", {}, 0.5)
        ranked = (RankedChunk(chunk, 1.0, ("vector",), ()),)
        row = evidence_rows(_result(ranked))[0]
        assert row.title == "doc-x"
        assert row.doc_type == "unknown"


class TestGraphElements:
    def test_nodes_and_edges_come_only_from_evidence(self):
        ranked = (
            RankedChunk(_chunk("v", 0.9), 1.0, ("vector",), ()),  # no evidence → no edges
            RankedChunk(
                _chunk("g", title="Invoice 7"),
                0.5,
                ("graph",),
                (_evidence("g"), _evidence("g", "Northgate", "sent")),
            ),
        )
        elements = graph_elements(_result(ranked))
        entity_ids = {n.node_id for n in elements.nodes if n.kind == "entity"}
        document_ids = {n.node_id for n in elements.nodes if n.kind == "document"}
        assert entity_ids == {"id-Omar Tran", "id-Northgate"}
        assert document_ids == {"doc-g"}  # the vector-only chunk's document is not invented in
        assert {(e.entity_id, e.relation) for e in elements.edges} == {
            ("id-Omar Tran", "co_mentioned"),
            ("id-Northgate", "sent"),
        }
        assert all(e.chunk_id == "g" for e in elements.edges)

    def test_duplicate_evidence_rows_deduplicate(self):
        ranked = (RankedChunk(_chunk("g"), 1.0, ("graph",), (_evidence("g"), _evidence("g"))),)
        elements = graph_elements(_result(ranked))
        assert len(elements.edges) == 1

    def test_no_evidence_yields_empty_elements(self):
        ranked = (RankedChunk(_chunk("v", 0.9), 1.0, ("vector",), ()),)
        elements = graph_elements(_result(ranked))
        assert elements.nodes == () and elements.edges == ()


class TestFigures:
    def test_entity_graph_figure_matches_evidence_counts(self):
        ranked = (
            RankedChunk(
                _chunk("g"),
                1.0,
                ("graph",),
                (_evidence("g"), _evidence("g", "Northgate", "sent")),
            ),
        )
        figure = entity_graph_figure(graph_elements(_result(ranked)))
        assert figure is not None
        entity_trace = next(t for t in figure.data if t.name == "Entity")
        document_trace = next(t for t in figure.data if t.name == "Document")
        assert len(entity_trace.x) == 2
        assert len(document_trace.x) == 1
        edge_trace = figure.data[0]  # 2 edges × (x0, x1, None separator)
        assert len(edge_trace.x) == 6

    def test_empty_elements_yield_no_figure(self):
        ranked = (RankedChunk(_chunk("v", 0.9), 1.0, ("vector",), ()),)
        assert entity_graph_figure(graph_elements(_result(ranked))) is None

    def test_timeline_figure_is_chronological(self):
        figure = timeline_figure([_event(20, "audit opened"), _event(5, "invoice paid")])
        assert figure is not None
        assert list(figure.data[0].text) == ["invoice paid", "audit opened"]

    def test_empty_timeline_yields_no_figure(self):
        assert timeline_figure([]) is None


class TestTimelinePresentation:
    def test_frame_is_chronological_with_citations(self):
        frame = timeline_frame([_event(20, "audit opened"), _event(5, "invoice paid")])
        assert list(frame["description"]) == ["invoice paid", "audit opened"]
        assert list(frame["date"]) == ["2024-03-05", "2024-03-20"]
        assert frame.iloc[0]["document"] == "Audit memo"
        assert frame.iloc[0]["chunk_id"] == "chunk-1"

    def test_record_conversion_handles_neo4j_datetime(self):
        class FakeNeo4jDateTime:
            def to_native(self):
                return datetime(2024, 3, 5, tzinfo=UTC)

        event = timeline_event_from_record(
            {
                "event_id": "ev-1",
                "occurred_at": FakeNeo4jDateTime(),
                "description": "invoice paid",
                "document_id": "doc-1",
                "document_title": "Audit memo",
                "chunk_id": "chunk-1",
                "entity_names": ["Zoe", "Alan"],
            }
        )
        assert event.occurred_at == datetime(2024, 3, 5, tzinfo=UTC)
        assert event.entity_names == ("Alan", "Zoe")  # deterministic ordering


class TestMetricsPresentation:
    _EXTRACTION = {
        "mentions_strict": {
            "person": {"precision": 0.9, "recall": 0.8, "f1": 0.85, "gold": 10, "predicted": 9},
            "micro": {"precision": 0.9, "recall": 0.8, "f1": 0.85, "gold": 10, "predicted": 9},
        },
        "mentions_relaxed": {
            "micro": {"precision": 0.95, "recall": 0.9, "f1": 0.92, "gold": 10, "predicted": 9},
        },
    }
    _RETRIEVAL = {
        "vector_only": {
            "overall": {"@1": {"precision": 0.6, "recall": 0.5, "hit_rate": 0.6}},
            "per_category": {
                "relationship": {"@5": {"precision": 0.2, "recall": 0.4, "hit_rate": 0.5}},
            },
        },
        "graph_expanded": {
            "overall": {"@1": {"precision": 0.6, "recall": 0.5, "hit_rate": 0.6}},
            "per_category": {
                "relationship": {"@5": {"precision": 0.3, "recall": 0.7, "hit_rate": 0.8}},
            },
        },
    }

    def test_extraction_table_orders_types_and_keeps_micro(self):
        table = extraction_table(self._EXTRACTION, "strict")
        assert list(table["type"]) == ["person", "micro"]
        assert table.iloc[0]["f1"] == 0.85

    def test_retrieval_modes_stay_separate(self):
        vector = retrieval_table(self._RETRIEVAL, "vector_only")
        hybrid = retrieval_table(self._RETRIEVAL, "graph_expanded")
        assert vector.iloc[0]["scope"] == "overall"  # overall listed first
        vector_rel = vector[vector["scope"] == "relationship"].iloc[0]
        hybrid_rel = hybrid[hybrid["scope"] == "relationship"].iloc[0]
        assert vector_rel["hit_rate"] == 0.5
        assert hybrid_rel["hit_rate"] == 0.8

    def test_missing_artifact_returns_none(self, tmp_path):
        assert backend.load_metrics_artifact(tmp_path / "absent.json") is None

    def test_present_artifact_loads(self, tmp_path):
        path = tmp_path / "metrics.json"
        path.write_text(json.dumps(self._RETRIEVAL), encoding="utf-8")
        assert backend.load_metrics_artifact(path) == self._RETRIEVAL


class TestBackendOutcomes:
    def test_vector_failure_becomes_explicit_error(self):
        class BrokenRetriever:
            def search(self, question, limit=10):
                raise OperationalError("SELECT 1", {}, Exception("connection refused"))

        outcome = backend.run_investigation(BrokenRetriever(), "who paid?")
        assert outcome.result is None
        assert "OperationalError" in outcome.error

    def test_successful_search_carries_result(self):
        result = _result(())

        class WorkingRetriever:
            def search(self, question, limit=10):
                return result

        outcome = backend.run_investigation(WorkingRetriever(), "who paid?")
        assert outcome.error is None
        assert outcome.result is result

    def test_unconfigured_graph_yields_timeline_error(self, monkeypatch):
        from legal_discovery_graph.config import Settings

        monkeypatch.setattr(backend, "get_settings", lambda: Settings(_env_file=None))
        outcome = backend.fetch_timeline()
        assert outcome.events == ()
        assert "not configured" in outcome.error


class TestAppRendering:
    """Headless app runs with the backend stubbed to no-credentials states."""

    @staticmethod
    def _run_app(monkeypatch, tmp_path) -> AppTest:
        monkeypatch.setattr(
            backend,
            "backend_status",
            lambda: backend.BackendStatus(
                database_configured=False, graph_configured=False, embedding_model="test-model"
            ),
        )
        monkeypatch.setattr(
            backend,
            "fetch_timeline",
            lambda: backend.TimelineOutcome(events=(), error="Neo4j is not configured"),
        )
        monkeypatch.setattr(backend, "EXTRACTION_METRICS_PATH", tmp_path / "absent.json")
        monkeypatch.setattr(backend, "RETRIEVAL_METRICS_PATH", tmp_path / "absent.json")
        app = AppTest.from_file(_APP_PATH, default_timeout=30)
        app.run()
        return app

    def test_renders_without_credentials(self, monkeypatch, tmp_path):
        app = self._run_app(monkeypatch, tmp_path)
        assert not app.exception
        assert "Legal Discovery Intelligence Graph" in app.title[0].value

    def test_search_is_disabled_with_clear_error_when_unconfigured(self, monkeypatch, tmp_path):
        app = self._run_app(monkeypatch, tmp_path)
        assert any("DATABASE_URL" in err.value for err in app.error)

    def test_timeline_degrades_visibly(self, monkeypatch, tmp_path):
        app = self._run_app(monkeypatch, tmp_path)
        assert any("Neo4j is not configured" in w.value for w in app.warning)

    def test_missing_artifacts_show_reproduction_commands(self, monkeypatch, tmp_path):
        app = self._run_app(monkeypatch, tmp_path)
        infos = " ".join(info.value for info in app.info)
        assert "evaluate_extraction.py" in infos
        assert "evaluate_retrieval.py" in infos


def test_app_module_imports_without_side_effects():
    """Plain import must not execute the app (module body is guarded by main())."""
    import legal_discovery_graph.ui.streamlit_app as app_module

    assert callable(app_module.main)
