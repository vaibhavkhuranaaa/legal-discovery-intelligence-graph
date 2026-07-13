"""Streamlit health-check application for the foundation milestone.

This is intentionally minimal: it verifies that the package installs, imports,
and serves under Streamlit before any product features exist. The full
investigation dashboard (semantic search, entity graph, timeline, evaluation
metrics) is built in later phases — see docs/roadmap.md.
"""

import streamlit as st

from legal_discovery_graph import __version__

st.set_page_config(page_title="Legal Discovery Intelligence Graph", page_icon="🕸️")

st.title("Legal Discovery Intelligence Graph — Foundation Ready")

st.markdown(
    f"""
    **Status:** foundation milestone — package version `{__version__}`.

    This health check confirms the application scaffold runs. Investigation
    features (semantic retrieval, entity graph, timeline, evaluation) arrive
    in subsequent milestones per `docs/roadmap.md`.
    """
)
