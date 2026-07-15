"""Semantic retrieval: sentence-transformer embeddings over PostgreSQL + pgvector,
plus hybrid orchestration with Neo4j graph expansion."""

from legal_discovery_graph.retrieval.embeddings import (
    EMBEDDING_DIMENSION,
    Embedder,
    OnnxEmbedder,
    SentenceTransformerEmbedder,
    build_embedder,
)
from legal_discovery_graph.retrieval.hybrid import (
    GraphHit,
    HybridResult,
    HybridRetriever,
    RankedChunk,
    fuse_rankings,
)
from legal_discovery_graph.retrieval.retriever import SemanticRetriever
from legal_discovery_graph.retrieval.store import PgVectorStore, RetrievedChunk

__all__ = [
    "EMBEDDING_DIMENSION",
    "GraphHit",
    "HybridResult",
    "HybridRetriever",
    "PgVectorStore",
    "RankedChunk",
    "RetrievedChunk",
    "SemanticRetriever",
    "Embedder",
    "OnnxEmbedder",
    "SentenceTransformerEmbedder",
    "build_embedder",
    "fuse_rankings",
]
