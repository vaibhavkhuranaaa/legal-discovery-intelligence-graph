"""Streamlit investigation dashboard (Milestone 5).

Four panels over the hybrid Graph RAG pipeline: cited evidence for an
investigative question, the entity graph behind that evidence, the extracted
event timeline, and reproducible evaluation metrics. The app displays
retrieved, cited evidence only — there is no LLM answer generation, so no
prose is ever shown that a document does not back.

All data access goes through :mod:`legal_discovery_graph.ui.backend`
(no database drivers here); shaping and figures are pure functions in
:mod:`presenters` / :mod:`figures`. Degraded states are explicit per
``docs/architecture.md``: a vector failure is an error, a graph failure
keeps vector evidence and says so, missing artifacts show the command that
produces them.
"""

import streamlit as st

from legal_discovery_graph.retrieval import HybridResult, HybridRetriever
from legal_discovery_graph.ui import backend
from legal_discovery_graph.ui.figures import entity_graph_figure, timeline_figure
from legal_discovery_graph.ui.presenters import (
    evidence_rows,
    extraction_table,
    graph_elements,
    retrieval_table,
    timeline_frame,
)

_SOURCE_BADGES = {"vector": "🔎 vector", "graph": "🕸️ graph"}
_LAST_RESULT_KEY = "last_hybrid_result"


@st.cache_resource(show_spinner="Loading retriever (embedding model + connections)…")
def _retriever() -> HybridRetriever:
    return backend.build_retriever()


@st.cache_data(show_spinner="Searching evidence…")
def _search(question: str, limit: int) -> backend.InvestigationOutcome:
    return backend.run_investigation(_retriever(), question, limit=limit)


@st.cache_data(ttl=60, show_spinner="Loading timeline from the graph…")
def _timeline() -> backend.TimelineOutcome:
    return backend.fetch_timeline()


def _metrics(path_name: str) -> dict | None:
    path = {
        "extraction": backend.EXTRACTION_METRICS_PATH,
        "retrieval": backend.RETRIEVAL_METRICS_PATH,
    }[path_name]
    return backend.load_metrics_artifact(path)


def _render_sidebar(status: backend.BackendStatus) -> None:
    with st.sidebar:
        st.header("Backend status")
        st.markdown(
            f"{'✅' if status.database_configured else '⚠️'} PostgreSQL + pgvector "
            f"{'configured' if status.database_configured else 'not configured'}\n\n"
            f"{'✅' if status.graph_configured else '⚠️'} Neo4j graph "
            f"{'configured' if status.graph_configured else 'not configured'}"
        )
        st.caption(f"Embedding model: `{status.embedding_model}`")
        st.caption(
            "This app shows retrieved, cited evidence from a synthetic corpus — "
            "it does not generate answers."
        )


def _render_graph_notice(result: HybridResult) -> None:
    if not result.graph_available:
        st.warning(
            "Graph expansion is unavailable — showing vector evidence only. "
            f"Reason: {result.graph_error or 'unknown'}"
        )


def _render_evidence(result: HybridResult) -> None:
    _render_graph_notice(result)
    rows = evidence_rows(result)
    if not rows:
        st.info(
            "No evidence was retrieved for this question. The corpus may not be "
            "indexed yet — run `uv run python scripts/index_pgvector.py`."
        )
        return
    st.caption(
        f"{len(rows)} evidence chunks · "
        f"{sum(1 for r in rows if 'graph' in r.sources)} contributed by graph expansion"
    )
    for row in rows:
        badges = " · ".join(_SOURCE_BADGES[source] for source in row.sources)
        similarity = f" · cosine {row.similarity:.3f}" if row.similarity is not None else ""
        with st.container(border=True):
            st.markdown(f"**#{row.rank} — {row.title}** ({row.doc_type})")
            st.caption(f"{badges}{similarity} · fused rank score {row.fused_score:.3f}")
            st.text(row.text)
            st.caption(f"document `{row.document_id}` · chunk `{row.chunk_id}`")
            if row.evidence:
                with st.expander(f"Graph evidence trail ({len(row.evidence)} relations)"):
                    for item in row.evidence:
                        st.markdown(
                            f"- **{item.entity_name}** — `{item.relation}` — this document "
                            f"(relation source chunk `{item.source_chunk_id[:12]}…`, "
                            f"evidence chunk `{item.chunk_id[:12]}…`)"
                        )


def _render_investigate_tab(status: backend.BackendStatus) -> None:
    st.subheader("Ask an investigative question")
    if not status.database_configured:
        st.error(
            "Semantic search requires PostgreSQL + pgvector. Set `DATABASE_URL` "
            "(see `.env.example`) and restart — searching is disabled until then."
        )
        return
    with st.form("investigation"):
        question = st.text_input(
            "Question",
            placeholder="e.g. Who approved the payments to Northgate Supply Group?",
        )
        limit = st.slider("Evidence chunks to retrieve", min_value=5, max_value=20, value=10)
        submitted = st.form_submit_button("Retrieve evidence")
    if submitted and question.strip():
        outcome = _search(question.strip(), limit)
        if outcome.error is not None:
            st.error(
                "Investigation search failed — no evidence could be retrieved. "
                f"Details: {outcome.error}"
            )
            st.session_state.pop(_LAST_RESULT_KEY, None)
            return
        st.session_state[_LAST_RESULT_KEY] = outcome.result
    result = st.session_state.get(_LAST_RESULT_KEY)
    if result is not None:
        _render_evidence(result)


def _render_graph_tab() -> None:
    st.subheader("Entity graph for the current question")
    result: HybridResult | None = st.session_state.get(_LAST_RESULT_KEY)
    if result is None:
        st.info("Run an investigation first — the graph shows the evidence behind its results.")
        return
    _render_graph_notice(result)
    figure = entity_graph_figure(graph_elements(result))
    if figure is None:
        st.info(
            "No graph relationships were found for this question's evidence — "
            "nothing is drawn that the graph does not back."
        )
        return
    st.caption(
        "Entities (left) connect to documents (right) only where a stored, "
        "evidence-backed relation exists; hover an edge midpoint for its provenance."
    )
    st.plotly_chart(figure, width="stretch")


def _render_timeline_tab() -> None:
    st.subheader("Extracted event timeline")
    outcome = _timeline()
    if outcome.error is not None:
        st.warning(
            "The timeline reads extracted events from the Neo4j graph, which is "
            f"unavailable: {outcome.error}"
        )
        return
    if not outcome.events:
        st.info(
            "No events are loaded in the graph — run "
            "`uv run python scripts/load_neo4j.py` to extract and load the corpus."
        )
        return
    figure = timeline_figure(outcome.events)
    if figure is not None:
        st.plotly_chart(figure, width="stretch")
    st.caption("Table view — every event cites its evidencing document and chunk.")
    st.dataframe(timeline_frame(outcome.events), width="stretch", hide_index=True)


def _render_evaluation_tab() -> None:
    st.subheader("Reproducible evaluation")
    extraction = _metrics("extraction")
    retrieval = _metrics("retrieval")

    st.markdown("**Entity & event extraction** (vs gold labels)")
    if extraction is None:
        st.info(
            "No extraction metrics artifact found. Generate it with:\n\n"
            "`uv run python scripts/bootstrap_data.py && "
            "uv run python scripts/evaluate_extraction.py`"
        )
    else:
        corpus = extraction.get("corpus", {})
        st.caption(
            f"seed {corpus.get('seed', '?')} · {corpus.get('documents', '?')} documents · "
            f"{corpus.get('gold_mentions', '?')} gold mentions · "
            f"NER model {extraction.get('ner_model', '?')}"
        )
        strict_col, relaxed_col = st.columns(2)
        with strict_col:
            st.markdown("Strict span matching")
            st.dataframe(extraction_table(extraction, "strict"), hide_index=True)
        with relaxed_col:
            st.markdown("Relaxed (overlap) matching")
            st.dataframe(extraction_table(extraction, "relaxed"), hide_index=True)
        events = extraction.get("events")
        if events:
            st.caption(
                f"Events (document+date): P {events['precision']:.3f} · "
                f"R {events['recall']:.3f} · F1 {events['f1']:.3f}"
            )

    st.markdown("**Retrieval** (32 gold queries, macro-averaged)")
    if retrieval is None:
        st.info(
            "No retrieval metrics artifact found. Generate it against the live "
            "backends with:\n\n`uv run python scripts/evaluate_retrieval.py`"
        )
        return
    st.caption(
        f"embedding model {retrieval.get('embedding_model', '?')} · "
        f"fusion: {retrieval.get('fusion', '?')}"
    )
    vector_col, hybrid_col = st.columns(2)
    with vector_col:
        st.markdown("Vector-only")
        st.dataframe(retrieval_table(retrieval, "vector_only"), hide_index=True, height=420)
    with hybrid_col:
        st.markdown("Graph-expanded (hybrid)")
        st.dataframe(retrieval_table(retrieval, "graph_expanded"), hide_index=True, height=420)
    note = retrieval.get("note")
    if note:
        st.caption(note)


def main() -> None:
    st.set_page_config(
        page_title="Legal Discovery Intelligence Graph", page_icon="🕸️", layout="wide"
    )
    st.title("Legal Discovery Intelligence Graph")
    st.caption(
        "Graph RAG eDiscovery investigation over a synthetic corpus — "
        "cited evidence, entity relationships, timeline, and reproducible metrics."
    )
    status = backend.backend_status()
    _render_sidebar(status)
    investigate, graph, timeline, evaluation = st.tabs(
        ["🔎 Investigate", "🕸️ Entity graph", "📅 Timeline", "📊 Evaluation"]
    )
    with investigate:
        _render_investigate_tab(status)
    with graph:
        _render_graph_tab()
    with timeline:
        _render_timeline_tab()
    with evaluation:
        _render_evaluation_tab()


if __name__ == "__main__":
    main()
