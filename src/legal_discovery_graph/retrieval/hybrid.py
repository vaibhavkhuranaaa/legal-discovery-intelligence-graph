"""Hybrid retrieval: vector search + evidence-backed Neo4j graph expansion.

Orchestrated as a deterministic LangChain runnable pipeline
(``vector leg | graph leg | merge`` — no LLM, no agents). The vector leg
seeds the graph leg; graph expansion contributes chunks reachable from the
seed chunks' entities via co-mention, correspondence, or event involvement,
each carrying its :class:`GraphEvidence` trail back to a MENTIONED_IN
provenance edge.

Fusion is constant-free rank interleaving: candidates are ordered by their
best per-leg rank, the vector leg winning ties, then lexicographic
``chunk_id`` — so the pattern is V1, G1, V2, G2, … and a correct vector
top-1 can never be displaced. Summed Reciprocal Rank Fusion was measured
first and rejected (ADR-0011): the graph leg ranks by connectedness to the
seed evidence, not by relevance to the question, so RRF's intersection
boost let hub chunks displace correct vector top-1 hits. The graph leg
ranks candidates by how many distinct seed entities connect to them.

Degraded mode: if Neo4j is unconfigured or unreachable
(:class:`GraphUnavailableError`), the result still carries the full vector
leg, with ``graph_available=False`` and the reason — never silent success.
"""

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from langchain_core.runnables import Runnable, RunnableLambda

from legal_discovery_graph.config import get_settings
from legal_discovery_graph.graph import GraphEvidence, GraphUnavailableError, Neo4jGraphStore
from legal_discovery_graph.retrieval.embeddings import SentenceTransformerEmbedder
from legal_discovery_graph.retrieval.store import PgVectorStore, RetrievedChunk


@dataclass(frozen=True)
class GraphHit:
    """A chunk contributed by graph expansion, with its evidence trail."""

    chunk: RetrievedChunk
    evidence: tuple[GraphEvidence, ...]


@dataclass(frozen=True)
class RankedChunk:
    """One entry in the fused ranking; ``sources`` ⊆ {'vector', 'graph'}.

    ``fused_score`` is ``1 / best per-leg rank`` — a deterministic ranking
    artifact, not a similarity (vector cosine lives on ``chunk.score``).
    """

    chunk: RetrievedChunk
    fused_score: float
    sources: tuple[str, ...]
    evidence: tuple[GraphEvidence, ...]


@dataclass(frozen=True)
class HybridResult:
    """Full output of one hybrid search."""

    question: str
    ranked: tuple[RankedChunk, ...]
    vector_hits: tuple[RetrievedChunk, ...]
    graph_hits: tuple[GraphHit, ...]
    graph_available: bool
    graph_error: str | None


def _rank_graph_candidates(evidence: list[GraphEvidence]) -> list[tuple[str, list[GraphEvidence]]]:
    """Order expansion targets by distinct connecting entities, deterministically."""
    by_chunk: dict[str, list[GraphEvidence]] = defaultdict(list)
    for item in evidence:
        by_chunk[item.chunk_id].append(item)
    return sorted(
        by_chunk.items(),
        key=lambda kv: (-len({e.entity_id for e in kv[1]}), kv[0]),
    )


def fuse_rankings(
    vector_hits: list[RetrievedChunk],
    graph_hits: list[GraphHit],
) -> list[RankedChunk]:
    """Interleave the two legs by best per-leg rank; the vector leg wins ties."""
    # (rank, leg_priority): lower sorts first; vector priority 0 beats graph 1.
    best_key: dict[str, tuple[int, int]] = {}
    sources: dict[str, set[str]] = defaultdict(set)
    chunks: dict[str, RetrievedChunk] = {}
    evidence: dict[str, tuple[GraphEvidence, ...]] = {}

    for rank, hit in enumerate(vector_hits, start=1):
        best_key[hit.chunk_id] = (rank, 0)
        sources[hit.chunk_id].add("vector")
        chunks[hit.chunk_id] = hit
    for rank, graph_hit in enumerate(graph_hits, start=1):
        chunk_id = graph_hit.chunk.chunk_id
        best_key[chunk_id] = min(best_key.get(chunk_id, (rank, 1)), (rank, 1))
        sources[chunk_id].add("graph")
        chunks.setdefault(chunk_id, graph_hit.chunk)
        evidence[chunk_id] = graph_hit.evidence

    return [
        RankedChunk(
            chunk=chunks[chunk_id],
            fused_score=round(1.0 / best_key[chunk_id][0], 6),
            sources=tuple(sorted(sources[chunk_id])),
            evidence=evidence.get(chunk_id, ()),
        )
        for chunk_id in sorted(best_key, key=lambda cid: (*best_key[cid], cid))
    ]


class HybridRetriever:
    """Vector retrieval seeded graph expansion, fused by rank interleaving."""

    def __init__(
        self,
        store: PgVectorStore,
        embedder: SentenceTransformerEmbedder,
        graph: Neo4jGraphStore | None,
        graph_error: str | None = None,
    ) -> None:
        self._store = store
        self._embedder = embedder
        self._graph = graph
        self._graph_error = graph_error
        self._chain: Runnable = (
            RunnableLambda(self._vector_leg)
            | RunnableLambda(self._graph_leg)
            | RunnableLambda(self._merge)
        )

    @classmethod
    def from_settings(cls) -> "HybridRetriever":
        """Build from application settings; a misconfigured graph degrades, not fails."""
        settings = get_settings()
        graph: Neo4jGraphStore | None = None
        graph_error: str | None = None
        try:
            graph = Neo4jGraphStore(
                settings.neo4j_uri, settings.neo4j_username, settings.neo4j_password
            )
        except GraphUnavailableError as exc:
            graph_error = str(exc)
        return cls(
            store=PgVectorStore(settings.database_url),
            embedder=SentenceTransformerEmbedder(settings.embedding_model_name),
            graph=graph,
            graph_error=graph_error,
        )

    def search(self, question: str, limit: int = 10, seed_limit: int = 5) -> HybridResult:
        """Run the hybrid pipeline; top ``seed_limit`` vector hits seed the graph."""
        return self._chain.invoke(
            {"question": question, "limit": limit, "seed_limit": seed_limit}
        )

    def _vector_leg(self, state: dict[str, Any]) -> dict[str, Any]:
        embedding = self._embedder.embed_query(state["question"])
        state["vector_hits"] = self._store.search(embedding, limit=state["limit"])
        return state

    def _graph_leg(self, state: dict[str, Any]) -> dict[str, Any]:
        state["graph_hits"] = []
        state["graph_error"] = self._graph_error
        state["graph_available"] = False
        if self._graph is None:
            return state
        seeds = [hit.chunk_id for hit in state["vector_hits"][: state["seed_limit"]]]
        try:
            evidence = self._graph.expand_from_chunks(seeds)
            state["graph_available"] = True
        except GraphUnavailableError as exc:
            state["graph_error"] = str(exc)
            return state
        ranked = _rank_graph_candidates(evidence)[: state["limit"]]
        hydrated = {
            chunk.chunk_id: chunk
            for chunk in self._store.fetch_chunks([chunk_id for chunk_id, _ in ranked])
        }
        state["graph_hits"] = [
            GraphHit(chunk=hydrated[chunk_id], evidence=tuple(items))
            for chunk_id, items in ranked
            if chunk_id in hydrated
        ]
        return state

    def _merge(self, state: dict[str, Any]) -> HybridResult:
        fused = fuse_rankings(state["vector_hits"], state["graph_hits"])
        return HybridResult(
            question=state["question"],
            ranked=tuple(fused[: state["limit"]]),
            vector_hits=tuple(state["vector_hits"]),
            graph_hits=tuple(state["graph_hits"]),
            graph_available=state["graph_available"],
            graph_error=state["graph_error"],
        )
