"""Data access for the investigation dashboard.

This module is the UI's only boundary to retrieval, graph, and artifact data:
Streamlit code never touches database drivers or raw exceptions. Every
operation returns an explicit outcome object so the UI can render degraded
states honestly — a vector failure is an error, never an empty "success";
a graph failure keeps the vector evidence and carries the reason
(``docs/architecture.md``, Failure Boundaries).
"""

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from legal_discovery_graph.config import get_settings
from legal_discovery_graph.graph import GraphUnavailableError, Neo4jGraphStore, TimelineEvent
from legal_discovery_graph.retrieval import HybridResult, HybridRetriever

logger = logging.getLogger(__name__)

# Failures the vector leg can raise through HybridRetriever.search():
# missing/invalid configuration (ValueError), PostgreSQL/driver errors
# (SQLAlchemyError), and embedding-model load/download errors (OSError).
_VECTOR_FAILURES = (ValueError, SQLAlchemyError, OSError)

EXTRACTION_METRICS_PATH = Path("artifacts/extraction_metrics.json")
RETRIEVAL_METRICS_PATH = Path("artifacts/retrieval_metrics.json")


@dataclass(frozen=True)
class BackendStatus:
    """Configuration visibility for the sidebar health panel (no secrets)."""

    database_configured: bool
    graph_configured: bool
    embedding_model: str


@dataclass(frozen=True)
class InvestigationOutcome:
    """Result of one investigation search: a HybridResult or an explicit error."""

    result: HybridResult | None
    error: str | None


@dataclass(frozen=True)
class TimelineOutcome:
    """Timeline events from the graph, or the reason the graph is unavailable."""

    events: tuple[TimelineEvent, ...]
    error: str | None


def backend_status() -> BackendStatus:
    """Report which backends are configured, without connecting to anything."""
    settings = get_settings()
    return BackendStatus(
        database_configured=bool(settings.database_url),
        graph_configured=bool(
            settings.neo4j_uri and settings.neo4j_username and settings.neo4j_password
        ),
        embedding_model=settings.embedding_model_name,
    )


def build_retriever() -> HybridRetriever:
    """Construct the hybrid retriever from settings (graph degrades, never fails)."""
    return HybridRetriever.from_settings()


def run_investigation(
    retriever: HybridRetriever, question: str, limit: int = 10
) -> InvestigationOutcome:
    """Run one hybrid search, converting vector-leg failures to an explicit error."""
    try:
        return InvestigationOutcome(result=retriever.search(question, limit=limit), error=None)
    except _VECTOR_FAILURES as exc:
        logger.exception("investigation search failed")
        return InvestigationOutcome(result=None, error=f"{type(exc).__name__}: {exc}")


def fetch_timeline() -> TimelineOutcome:
    """Load all extracted events from the graph, or report why it is unavailable."""
    settings = get_settings()
    try:
        with Neo4jGraphStore(
            settings.neo4j_uri, settings.neo4j_username, settings.neo4j_password
        ) as store:
            return TimelineOutcome(events=tuple(store.timeline_events()), error=None)
    except GraphUnavailableError as exc:
        return TimelineOutcome(events=(), error=str(exc))


def load_metrics_artifact(path: Path) -> dict | None:
    """Load a committed evaluation artifact, or ``None`` when it does not exist."""
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))
