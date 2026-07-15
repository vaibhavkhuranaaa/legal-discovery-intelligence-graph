"""Question → ranked chunks: composes the embedder and the pgvector store."""

from legal_discovery_graph.config import get_settings
from legal_discovery_graph.retrieval.embeddings import Embedder, build_embedder
from legal_discovery_graph.retrieval.store import PgVectorStore, RetrievedChunk


class SemanticRetriever:
    """Embeds a natural-language question and searches the pgvector store."""

    def __init__(self, store: PgVectorStore, embedder: Embedder) -> None:
        self._store = store
        self._embedder = embedder

    @classmethod
    def from_settings(cls) -> "SemanticRetriever":
        """Build a retriever from application settings (requires DATABASE_URL)."""
        settings = get_settings()
        return cls(
            store=PgVectorStore(settings.database_url),
            embedder=build_embedder(settings.embedding_model_name, settings.embedding_backend),
        )

    def search(self, question: str, limit: int = 5) -> list[RetrievedChunk]:
        """Return the top ``limit`` chunks for ``question``, best first."""
        return self._store.search(self._embedder.embed_query(question), limit=limit)
