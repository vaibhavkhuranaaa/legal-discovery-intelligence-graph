"""Plotly figure builders for the investigation dashboard.

Pure functions from presenter structures to figures — deterministic layout,
no I/O. The entity graph is a bipartite entity↔document layout: every edge
drawn corresponds to exactly one evidence-backed relation, never to visual
inference. Colors: two categorical slots (documents blue ``#2a78d6``,
entities aqua ``#1baf7a``), CVD-validated as a pair; both node kinds carry
direct text labels so identity never rides on color alone.
"""

from collections.abc import Sequence

import plotly.graph_objects as go

from legal_discovery_graph.graph import TimelineEvent
from legal_discovery_graph.ui.presenters import GraphElements

_DOCUMENT_COLOR = "#2a78d6"
_ENTITY_COLOR = "#1baf7a"
_EDGE_COLOR = "#b0afac"
_RELATION_LABELS = {
    "co_mentioned": "co-mentioned with",
    "sent": "sent",
    "received": "received",
    "event": "involved in event evidenced by",
}


def _column_positions(count: int) -> list[float]:
    """Evenly spread ``count`` nodes vertically, centered on 0."""
    if count == 1:
        return [0.0]
    return [index - (count - 1) / 2 for index in range(count)]


def entity_graph_figure(elements: GraphElements) -> go.Figure | None:
    """Bipartite evidence graph (entities left, documents right), or ``None`` if empty."""
    entities = [node for node in elements.nodes if node.kind == "entity"]
    documents = [node for node in elements.nodes if node.kind == "document"]
    if not elements.edges or not entities or not documents:
        return None

    positions: dict[str, tuple[float, float]] = {}
    for node, y in zip(entities, _column_positions(len(entities)), strict=True):
        positions[node.node_id] = (0.0, y)
    for node, y in zip(documents, _column_positions(len(documents)), strict=True):
        positions[node.node_id] = (1.0, y)
    labels = {node.node_id: node.label for node in elements.nodes}

    edge_x: list[float | None] = []
    edge_y: list[float | None] = []
    mid_x: list[float] = []
    mid_y: list[float] = []
    edge_hover: list[str] = []
    for edge in elements.edges:
        x0, y0 = positions[edge.entity_id]
        x1, y1 = positions[edge.document_id]
        edge_x += [x0, x1, None]
        edge_y += [y0, y1, None]
        mid_x.append((x0 + x1) / 2)
        mid_y.append((y0 + y1) / 2)
        relation = _RELATION_LABELS.get(edge.relation, edge.relation)
        edge_hover.append(
            f"{labels[edge.entity_id]} — {relation} — {labels[edge.document_id]}"
            f"<br>evidence chunk: {edge.chunk_id[:12]}…"
            f"<br>relation source chunk: {edge.source_chunk_id[:12]}…"
        )

    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=edge_x,
            y=edge_y,
            mode="lines",
            line={"color": _EDGE_COLOR, "width": 1},
            hoverinfo="skip",
            showlegend=False,
        )
    )
    figure.add_trace(
        go.Scatter(
            x=mid_x,
            y=mid_y,
            mode="markers",
            marker={"size": 10, "color": _EDGE_COLOR, "opacity": 0.01},
            hovertext=edge_hover,
            hoverinfo="text",
            showlegend=False,
        )
    )
    for nodes, color, name, anchor in (
        (entities, _ENTITY_COLOR, "Entity", "middle right"),
        (documents, _DOCUMENT_COLOR, "Document", "middle left"),
    ):
        figure.add_trace(
            go.Scatter(
                x=[positions[node.node_id][0] for node in nodes],
                y=[positions[node.node_id][1] for node in nodes],
                mode="markers+text",
                marker={"size": 14, "color": color},
                text=[node.label for node in nodes],
                textposition=anchor,
                hovertext=[f"{name}: {node.label}<br>id: {node.node_id}" for node in nodes],
                hoverinfo="text",
                name=name,
            )
        )
    figure.update_layout(
        xaxis={"visible": False, "range": [-0.6, 1.6]},
        yaxis={"visible": False},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02},
        margin={"l": 20, "r": 20, "t": 20, "b": 20},
        height=max(400, 34 * max(len(entities), len(documents))),
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return figure


def _short(description: str, limit: int = 72) -> str:
    """Truncate a direct label; the full text lives in the hover and table view."""
    return description if len(description) <= limit else description[: limit - 1] + "…"


def timeline_figure(events: Sequence[TimelineEvent]) -> go.Figure | None:
    """Chronological event scatter (earliest at top), or ``None`` if empty."""
    ordered = sorted(events, key=lambda ev: (ev.occurred_at, ev.event_id))
    if not ordered:
        return None
    hover = [
        f"{ev.occurred_at.date().isoformat()} — {ev.description}"
        f"<br>entities: {', '.join(ev.entity_names) or '—'}"
        f"<br>document: {ev.document_title}"
        for ev in ordered
    ]
    figure = go.Figure(
        go.Scatter(
            x=[ev.occurred_at for ev in ordered],
            y=list(range(len(ordered), 0, -1)),
            mode="markers+text",
            marker={"size": 12, "color": _DOCUMENT_COLOR},
            text=[_short(ev.description) for ev in ordered],
            textposition="middle right",
            hovertext=hover,
            hoverinfo="text",
            showlegend=False,
        )
    )
    # Pad the right edge so trailing direct labels stay inside the plot.
    span = ordered[-1].occurred_at - ordered[0].occurred_at
    padding = span / 10 if span else None
    figure.update_layout(
        xaxis={
            "title": "date",
            "showgrid": True,
            "gridcolor": "#e8e7e4",
            **(
                {"range": [ordered[0].occurred_at - padding, ordered[-1].occurred_at + 4 * padding]}
                if padding
                else {}
            ),
        },
        yaxis={"visible": False, "range": [0, len(ordered) + 1]},
        margin={"l": 20, "r": 20, "t": 20, "b": 40},
        height=max(400, 42 * len(ordered)),
        plot_bgcolor="rgba(0,0,0,0)",
    )
    return figure
