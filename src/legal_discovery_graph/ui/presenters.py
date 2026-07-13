"""Pure presentation shaping for the investigation dashboard.

Converts retrieval/graph/evaluation outputs into display-ready structures.
No Streamlit, no I/O, no drivers — everything here is unit-testable with
fabricated inputs. Nothing is invented at this layer: every graph node and
edge comes from a :class:`GraphEvidence` row, every timeline entry from an
extracted :class:`TimelineEvent`, every metric from a loaded artifact.
"""

from collections.abc import Sequence
from dataclasses import dataclass

import pandas as pd

from legal_discovery_graph.graph import GraphEvidence, TimelineEvent
from legal_discovery_graph.retrieval import HybridResult


@dataclass(frozen=True)
class EvidenceRow:
    """One ranked, cited chunk ready for display."""

    rank: int
    chunk_id: str
    document_id: str
    title: str
    doc_type: str
    text: str
    similarity: float | None  # cosine similarity when the vector leg scored it
    fused_score: float
    sources: tuple[str, ...]  # ⊆ {"vector", "graph"}
    evidence: tuple[GraphEvidence, ...]


def evidence_rows(result: HybridResult) -> list[EvidenceRow]:
    """Shape the fused ranking for display, preserving order and provenance."""
    rows: list[EvidenceRow] = []
    for rank, ranked in enumerate(result.ranked, start=1):
        chunk = ranked.chunk
        rows.append(
            EvidenceRow(
                rank=rank,
                chunk_id=chunk.chunk_id,
                document_id=chunk.document_id,
                title=chunk.metadata.get("title", chunk.document_id),
                doc_type=chunk.metadata.get("doc_type", "unknown"),
                text=chunk.text,
                # fetch_chunks() hydrates graph-only chunks with score 0.0 —
                # no similarity was computed, so none is shown.
                similarity=chunk.score if "vector" in ranked.sources else None,
                fused_score=ranked.fused_score,
                sources=ranked.sources,
                evidence=ranked.evidence,
            )
        )
    return rows


@dataclass(frozen=True)
class GraphNode:
    """A node in the evidence graph: an entity or a document."""

    node_id: str
    label: str
    kind: str  # "entity" | "document"


@dataclass(frozen=True)
class GraphEdge:
    """An entity→document edge, traceable to one GraphEvidence row."""

    entity_id: str
    document_id: str
    relation: str  # co_mentioned | sent | received | event
    chunk_id: str
    source_chunk_id: str


@dataclass(frozen=True)
class GraphElements:
    """Deduplicated nodes and edges derived only from graph evidence."""

    nodes: tuple[GraphNode, ...]
    edges: tuple[GraphEdge, ...]


def graph_elements(result: HybridResult) -> GraphElements:
    """Build graph nodes/edges strictly from the result's evidence trails."""
    document_titles: dict[str, str] = {}
    for ranked in result.ranked:
        title = ranked.chunk.metadata.get("title")
        if title:
            document_titles[ranked.chunk.document_id] = title

    entities: dict[str, str] = {}
    documents: set[str] = set()
    edges: dict[tuple[str, str, str], GraphEdge] = {}
    for ranked in result.ranked:
        for item in ranked.evidence:
            entities[item.entity_id] = item.entity_name
            documents.add(item.document_id)
            key = (item.entity_id, item.document_id, item.relation)
            edges.setdefault(
                key,
                GraphEdge(
                    entity_id=item.entity_id,
                    document_id=item.document_id,
                    relation=item.relation,
                    chunk_id=item.chunk_id,
                    source_chunk_id=item.source_chunk_id,
                ),
            )

    nodes = [
        GraphNode(node_id=entity_id, label=name, kind="entity")
        for entity_id, name in sorted(entities.items(), key=lambda kv: kv[1])
    ] + [
        GraphNode(node_id=doc_id, label=document_titles.get(doc_id, doc_id[:8]), kind="document")
        for doc_id in sorted(documents)
    ]
    return GraphElements(
        nodes=tuple(nodes),
        edges=tuple(edges[key] for key in sorted(edges)),
    )


def timeline_frame(events: Sequence[TimelineEvent]) -> pd.DataFrame:
    """Chronological event table with entities and document citations."""
    ordered = sorted(events, key=lambda ev: (ev.occurred_at, ev.event_id))
    return pd.DataFrame(
        {
            "date": [ev.occurred_at.date().isoformat() for ev in ordered],
            "description": [ev.description for ev in ordered],
            "entities": [", ".join(ev.entity_names) for ev in ordered],
            "document": [ev.document_title for ev in ordered],
            "document_id": [ev.document_id for ev in ordered],
            "chunk_id": [ev.chunk_id for ev in ordered],
        }
    )


_EXTRACTION_TYPE_ORDER = ("person", "organization", "money", "date", "project", "location", "micro")


def extraction_table(metrics: dict, matching: str) -> pd.DataFrame:
    """Per-type P/R/F1 table from ``extraction_metrics.json`` (strict or relaxed)."""
    section: dict = metrics[f"mentions_{matching}"]
    rows = [name for name in _EXTRACTION_TYPE_ORDER if name in section]
    return pd.DataFrame(
        {
            "type": rows,
            "precision": [section[name]["precision"] for name in rows],
            "recall": [section[name]["recall"] for name in rows],
            "f1": [section[name]["f1"] for name in rows],
            "gold": [section[name]["gold"] for name in rows],
            "predicted": [section[name]["predicted"] for name in rows],
        }
    )


def retrieval_table(metrics: dict, mode: str) -> pd.DataFrame:
    """Overall + per-category metrics for one mode of ``retrieval_metrics.json``.

    ``mode`` is ``"vector_only"`` or ``"graph_expanded"`` — kept separate so the
    graph's contribution is visible, never blended.
    """
    section: dict = metrics[mode]
    scopes: dict[str, dict] = {"overall": section["overall"], **section["per_category"]}
    records = []
    for scope, by_k in sorted(scopes.items(), key=lambda kv: kv[0] != "overall"):
        for k in sorted(by_k, key=lambda label: int(label.lstrip("@"))):
            records.append(
                {
                    "scope": scope,
                    "k": k,
                    "precision": by_k[k]["precision"],
                    "recall": by_k[k]["recall"],
                    "hit_rate": by_k[k]["hit_rate"],
                }
            )
    return pd.DataFrame.from_records(records)
