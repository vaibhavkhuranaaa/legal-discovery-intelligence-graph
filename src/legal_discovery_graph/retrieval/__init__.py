"""Semantic retrieval: sentence-transformer embeddings over PostgreSQL + pgvector."""

from legal_discovery_graph.retrieval.embeddings import (
    EMBEDDING_DIMENSION,
    SentenceTransformerEmbedder,
)
from legal_discovery_graph.retrieval.retriever import SemanticRetriever
from legal_discovery_graph.retrieval.store import PgVectorStore, RetrievedChunk

__all__ = [
    "EMBEDDING_DIMENSION",
    "PgVectorStore",
    "RetrievedChunk",
    "SemanticRetriever",
    "SentenceTransformerEmbedder",
]
