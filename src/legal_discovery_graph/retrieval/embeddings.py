"""Sentence-transformer embeddings for chunks and queries.

The model is loaded lazily on first use so importing the retrieval package
stays cheap (tests, CLI help). Embeddings are L2-normalized at encode time,
which makes pgvector's cosine distance (``<=>``) the correct and stable
ranking metric (see ``docs/DATA_MODEL.md``).
"""

from collections.abc import Sequence
from typing import Any

# Fixed by the pgvector schema: chunks.embedding VECTOR(384). Changing the
# embedding model requires a migration and an ADR (docs/DATA_MODEL.md).
EMBEDDING_DIMENSION = 384


class SentenceTransformerEmbedder:
    """Embeds texts with a sentence-transformers model, normalized, 384-dim."""

    def __init__(self, model_name: str) -> None:
        if not model_name:
            raise ValueError(
                "embedding model name is empty — check EMBEDDING_MODEL_NAME in .env "
                "(an empty value overrides the default)"
            )
        self._model_name = model_name
        self._model: Any = None

    def _load(self) -> Any:
        if self._model is None:
            from sentence_transformers import SentenceTransformer

            model = SentenceTransformer(self._model_name)
            # renamed in newer sentence-transformers; support both
            dimension_of = getattr(
                model, "get_embedding_dimension", model.get_sentence_embedding_dimension
            )
            dimension = dimension_of()
            if dimension != EMBEDDING_DIMENSION:
                raise ValueError(
                    f"model {self._model_name!r} produces {dimension}-dim embeddings; "
                    f"the pgvector schema requires {EMBEDDING_DIMENSION} (docs/DATA_MODEL.md)"
                )
            self._model = model
        return self._model

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed a batch of chunk texts."""
        model = self._load()
        vectors = model.encode(list(texts), normalize_embeddings=True, convert_to_numpy=True)
        return [vector.tolist() for vector in vectors]

    def embed_query(self, text: str) -> list[float]:
        """Embed a single search query."""
        return self.embed_texts([text])[0]
