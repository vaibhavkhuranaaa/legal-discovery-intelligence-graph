"""Hybrid orchestration tests: rank interleaving, provenance, degraded mode.

Uses in-memory fakes for the vector store, embedder, and graph store — no
cloud services. The live pipeline is verified via scripts/load_neo4j.py and
scripts/evaluate_retrieval.py.
"""

from legal_discovery_graph.graph import GraphEvidence, GraphUnavailableError
from legal_discovery_graph.retrieval.hybrid import GraphHit, HybridRetriever, fuse_rankings
from legal_discovery_graph.retrieval.store import RetrievedChunk


def _chunk(chunk_id: str, score: float = 0.0) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id=chunk_id,
        document_id=f"doc-{chunk_id}",
        sequence=0,
        text=f"text {chunk_id}",
        metadata={},
        score=score,
    )


def _evidence(chunk_id: str, entity: str = "Omar Tran") -> GraphEvidence:
    return GraphEvidence(
        entity_id=f"id-{entity}",
        entity_name=entity,
        relation="co_mentioned",
        document_id=f"doc-{chunk_id}",
        source_chunk_id="seed-chunk",
        chunk_id=chunk_id,
    )


class FakeEmbedder:
    def embed_query(self, text: str) -> list[float]:
        return [0.0]


class FakeVectorStore:
    def __init__(self, hits: list[RetrievedChunk]) -> None:
        self._hits = hits
        self.seen_fetches: list[list[str]] = []

    def search(self, embedding, limit: int = 5) -> list[RetrievedChunk]:
        return self._hits[:limit]

    def fetch_chunks(self, chunk_ids) -> list[RetrievedChunk]:
        self.seen_fetches.append(list(chunk_ids))
        return [_chunk(chunk_id) for chunk_id in chunk_ids]


class FakeGraph:
    def __init__(self, evidence: list[GraphEvidence]) -> None:
        self._evidence = evidence
        self.seen_seeds: list[list[str]] = []

    def expand_from_chunks(self, seed_chunk_ids) -> list[GraphEvidence]:
        self.seen_seeds.append(list(seed_chunk_ids))
        return self._evidence


class BrokenGraph:
    def expand_from_chunks(self, seed_chunk_ids):
        raise GraphUnavailableError("connection refused")


class TestFuseRankings:
    def test_chunk_in_both_legs_takes_its_best_rank(self):
        vector = [_chunk("a", 0.9), _chunk("b", 0.8)]
        graph = [GraphHit(chunk=_chunk("b"), evidence=(_evidence("b"),))]
        ranked = fuse_rankings(vector, graph)
        # "b" is vector rank 2 but graph rank 1 → interleaves right after "a";
        # the vector top-1 is never displaced.
        assert [r.chunk.chunk_id for r in ranked] == ["a", "b"]
        assert ranked[1].sources == ("graph", "vector")

    def test_interleave_pattern_is_v1_g1_v2_g2(self):
        vector = [_chunk("v1", 0.9), _chunk("v2", 0.8), _chunk("v3", 0.7)]
        graph = [
            GraphHit(chunk=_chunk("g1"), evidence=(_evidence("g1"),)),
            GraphHit(chunk=_chunk("g2"), evidence=(_evidence("g2"),)),
        ]
        ranked = fuse_rankings(vector, graph)
        assert [r.chunk.chunk_id for r in ranked] == ["v1", "g1", "v2", "g2", "v3"]

    def test_equal_rrf_ties_break_toward_vector_then_chunk_id(self):
        vector = [_chunk("v", 0.9)]
        graph = [GraphHit(chunk=_chunk("g"), evidence=(_evidence("g"),))]
        ranked = fuse_rankings(vector, graph)  # both rank 1 in their leg
        assert [r.chunk.chunk_id for r in ranked] == ["v", "g"]

    def test_graph_only_hits_keep_their_evidence(self):
        graph = [GraphHit(chunk=_chunk("g"), evidence=(_evidence("g", "Northgate"),))]
        ranked = fuse_rankings([], graph)
        assert ranked[0].evidence[0].entity_name == "Northgate"
        assert ranked[0].evidence[0].relation == "co_mentioned"

    def test_fusion_is_deterministic(self):
        vector = [_chunk("a", 0.9), _chunk("b", 0.8), _chunk("c", 0.7)]
        graph = [
            GraphHit(chunk=_chunk("d"), evidence=(_evidence("d"),)),
            GraphHit(chunk=_chunk("b"), evidence=(_evidence("b"),)),
        ]
        first = [r.chunk.chunk_id for r in fuse_rankings(vector, graph)]
        second = [r.chunk.chunk_id for r in fuse_rankings(vector, graph)]
        assert first == second


class TestHybridRetriever:
    def test_vector_hits_seed_graph_and_results_merge(self):
        vector_hits = [_chunk(c, 0.9 - i / 10) for i, c in enumerate("abcdef")]
        graph = FakeGraph([_evidence("z"), _evidence("z", "Northgate"), _evidence("y")])
        store = FakeVectorStore(vector_hits)
        retriever = HybridRetriever(store, FakeEmbedder(), graph)

        result = retriever.search("who paid?", limit=6, seed_limit=3)

        assert graph.seen_seeds == [["a", "b", "c"]]  # top seed_limit vector hits
        assert result.graph_available is True
        ranked_ids = [r.chunk.chunk_id for r in result.ranked]
        assert "z" in ranked_ids  # graph-only chunk entered the ranking
        z = next(r for r in result.ranked if r.chunk.chunk_id == "z")
        assert z.sources == ("graph",)
        assert {e.entity_name for e in z.evidence} == {"Omar Tran", "Northgate"}

    def test_graph_candidates_ranked_by_distinct_connecting_entities(self):
        graph = FakeGraph([_evidence("z"), _evidence("z", "Northgate"), _evidence("y")])
        retriever = HybridRetriever(FakeVectorStore([_chunk("a", 0.9)]), FakeEmbedder(), graph)
        result = retriever.search("q", limit=10)
        graph_ids = [hit.chunk.chunk_id for hit in result.graph_hits]
        assert graph_ids == ["z", "y"]  # two entities beat one

    def test_unconfigured_graph_degrades_with_reason(self):
        retriever = HybridRetriever(
            FakeVectorStore([_chunk("a", 0.9)]),
            FakeEmbedder(),
            graph=None,
            graph_error="Neo4j is not configured",
        )
        result = retriever.search("q")
        assert result.graph_available is False
        assert "not configured" in result.graph_error
        assert [r.chunk.chunk_id for r in result.ranked] == ["a"]  # vector leg intact

    def test_graph_failure_mid_query_degrades_not_raises(self):
        store = FakeVectorStore([_chunk("a", 0.9)])
        retriever = HybridRetriever(store, FakeEmbedder(), BrokenGraph())
        result = retriever.search("q")
        assert result.graph_available is False
        assert "connection refused" in result.graph_error
        assert [hit.chunk_id for hit in result.vector_hits] == ["a"]


class TestDriverErrorBoundary:
    """Raw neo4j driver exceptions must never escape the graph boundary.

    ServiceUnavailable subclasses DriverError, not Neo4jError — the real
    Neo4j-down failure mode. The store must convert it so HybridRetriever
    degrades to vector-only instead of crashing.
    """

    @staticmethod
    def _unreachable_store(failure: Exception):
        from legal_discovery_graph.graph import Neo4jGraphStore

        class _FailingDriver:
            def execute_query(self, *args, **kwargs):
                raise failure

            def verify_connectivity(self):
                raise failure

            def close(self):
                pass

        store = Neo4jGraphStore("bolt://127.0.0.1:9", "neo4j", "unused-test-password")
        store._driver = _FailingDriver()  # driver never dials out in tests
        return store

    def test_service_unavailable_becomes_graph_unavailable(self):
        import neo4j.exceptions
        import pytest

        store = self._unreachable_store(neo4j.exceptions.ServiceUnavailable("cannot reach"))
        with pytest.raises(GraphUnavailableError, match="cannot reach"):
            store.expand_from_chunks(["c1"])
        with pytest.raises(GraphUnavailableError):
            store.verify_connectivity()

    def test_hybrid_degrades_to_vector_only_on_driver_error(self):
        import neo4j.exceptions

        store = self._unreachable_store(neo4j.exceptions.ServiceUnavailable("instance paused"))
        vector = FakeVectorStore([_chunk("a", 0.9), _chunk("b", 0.8)])
        retriever = HybridRetriever(vector, FakeEmbedder(), store)

        result = retriever.search("who paid?")  # must not raise

        assert result.graph_available is False
        assert result.graph_error and "instance paused" in result.graph_error
        assert [hit.chunk_id for hit in result.vector_hits] == ["a", "b"]
        assert [r.chunk.chunk_id for r in result.ranked] == ["a", "b"]
