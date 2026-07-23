"""Webapp-only figure builders (the shared ones live in ``ui.figures``).

Pure functions from loaded metrics artifacts to Plotly figures — no I/O.
Series colors are the CVD-validated pair used across the app: vector blue
``#2a78d6`` and hybrid brass ``#a8762a`` (both carry a legend and direct
hover labels, so identity never rides on color alone).
"""

from collections import Counter

import plotly.graph_objects as go

from legal_discovery_graph.ui.presenters import GraphElements

_RELATION_LABELS = {
    "co_mentioned": "co-mentioned with",
    "sent": "sent",
    "received": "received",
    "event": "involved in event evidenced by",
}


def cytoscape_elements(elements: GraphElements) -> list[dict]:
    """GraphElements → cytoscape.js element dicts (nodes then edges).

    Nothing is invented here: every node and edge comes from an
    evidence-backed :class:`GraphEvidence` row. Internal chunk IDs stay in
    the data layer — edge detail shows the relation and document title only.
    """
    degree: Counter[str] = Counter()
    for edge in elements.edges:
        degree[edge.entity_id] += 1
        degree[edge.document_id] += 1
    nodes = [
        {
            "data": {
                "id": node.node_id,
                "label": node.label,
                "kind": node.kind,
                "degree": degree[node.node_id],
            }
        }
        for node in elements.nodes
    ]
    edges = [
        {
            "data": {
                "id": f"{edge.entity_id}->{edge.document_id}:{edge.relation}",
                "source": edge.entity_id,
                "target": edge.document_id,
                "relation": _RELATION_LABELS.get(edge.relation, edge.relation),
            }
        }
        for edge in elements.edges
    ]
    return nodes + edges


_VECTOR_COLOR = "#2a78d6"
_HYBRID_COLOR = "#a8762a"
_MODES = (
    ("vector_only", "Vector-only", _VECTOR_COLOR),
    ("graph_expanded", "Graph-expanded (hybrid)", _HYBRID_COLOR),
)


def retrieval_comparison_figure(metrics: dict) -> go.Figure | None:
    """Grouped bars of overall recall@k, vector-only vs graph-expanded.

    One measure, one axis: recall only. Precision and hit rate stay in the
    tables below the chart. Returns ``None`` if either mode is missing.
    """
    if any(mode not in metrics for mode, _, _ in _MODES):
        return None
    ks = sorted(metrics["vector_only"]["overall"], key=lambda label: int(label.lstrip("@")))
    figure = go.Figure()
    for mode, name, color in _MODES:
        overall = metrics[mode]["overall"]
        figure.add_trace(
            go.Bar(
                x=[f"recall {k}" for k in ks],
                y=[overall[k]["recall"] for k in ks],
                name=name,
                marker={"color": color},
                width=0.32,
                hovertemplate=name + ": %{y:.3f}<extra>%{x}</extra>",
            )
        )
    figure.update_layout(
        barmode="group",
        bargroupgap=0.08,
        yaxis={
            "range": [0, 1.05],
            "showgrid": True,
            "gridcolor": "#e8e7e4",
            "tickformat": ".2f",
        },
        xaxis={"showgrid": False},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02},
        margin={"l": 40, "r": 20, "t": 20, "b": 40},
        height=380,
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return figure
