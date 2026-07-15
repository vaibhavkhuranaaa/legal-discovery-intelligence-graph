"""Webapp-only figure builders (the shared ones live in ``ui.figures``).

Pure functions from loaded metrics artifacts to Plotly figures — no I/O.
Series colors are the CVD-validated pair used across the app: vector blue
``#2a78d6`` and hybrid brass ``#a8762a`` (both carry a legend and direct
hover labels, so identity never rides on color alone).
"""

import plotly.graph_objects as go

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
