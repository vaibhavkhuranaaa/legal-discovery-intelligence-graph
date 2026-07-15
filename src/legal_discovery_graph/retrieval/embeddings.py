"""Embeddings for chunks and queries: torch and ONNX backends.

Two interchangeable embedders produce the same normalized 384-dim MiniLM
vectors (ADR-0015): ``SentenceTransformerEmbedder`` (torch; used for indexing
and evaluation) and ``OnnxEmbedder`` (onnxruntime; used by the deployed web
app, where torch does not fit in memory). Models load lazily on first use so
importing the retrieval package stays cheap. Embeddings are L2-normalized at
encode time, which makes pgvector's cosine distance (``<=>``) the correct and
stable ranking metric (see ``docs/DATA_MODEL.md``).
"""

from collections.abc import Sequence
from typing import Any, Protocol

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


class Embedder(Protocol):
    """What retrieval needs from an embedding backend."""

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


# The ONNX export published in the model's own Hugging Face repository.
_ONNX_MODEL_FILE = "onnx/model.onnx"
_TOKENIZER_FILE = "tokenizer.json"
# MiniLM-L6-v2's trained sequence limit (sentence_bert_config.json).
_MAX_TOKENS = 256


class OnnxEmbedder:
    """MiniLM embeddings via onnxruntime — same vectors, no torch (ADR-0015).

    Reimplements the sentence-transformers pipeline for this model exactly:
    tokenize (pad/truncate to 256), transformer forward pass, attention-mask
    mean pooling, L2 normalization. Parity with the torch backend is asserted
    by test and was verified against the live index before deployment.
    """

    def __init__(self, model_name: str) -> None:
        if not model_name:
            raise ValueError(
                "embedding model name is empty — check EMBEDDING_MODEL_NAME in .env "
                "(an empty value overrides the default)"
            )
        self._model_name = model_name
        self._session: Any = None
        self._tokenizer: Any = None

    def _load(self) -> None:
        if self._session is not None:
            return
        import onnxruntime
        from huggingface_hub import hf_hub_download
        from tokenizers import Tokenizer

        model_path = hf_hub_download(self._model_name, _ONNX_MODEL_FILE)
        tokenizer_path = hf_hub_download(self._model_name, _TOKENIZER_FILE)
        tokenizer = Tokenizer.from_file(tokenizer_path)
        tokenizer.enable_truncation(max_length=_MAX_TOKENS)
        tokenizer.enable_padding()
        session = onnxruntime.InferenceSession(model_path, providers=["CPUExecutionProvider"])
        dimension = session.get_outputs()[0].shape[-1]
        if dimension != EMBEDDING_DIMENSION:
            raise ValueError(
                f"ONNX model {self._model_name!r} produces {dimension}-dim embeddings; "
                f"the pgvector schema requires {EMBEDDING_DIMENSION} (docs/DATA_MODEL.md)"
            )
        self._tokenizer = tokenizer
        self._session = session

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        """Embed a batch of texts (mean-pooled, L2-normalized)."""
        import numpy as np

        self._load()
        encodings = self._tokenizer.encode_batch(list(texts))
        input_ids = np.asarray([e.ids for e in encodings], dtype=np.int64)
        attention_mask = np.asarray([e.attention_mask for e in encodings], dtype=np.int64)
        feeds = {"input_ids": input_ids, "attention_mask": attention_mask}
        if any(inp.name == "token_type_ids" for inp in self._session.get_inputs()):
            feeds["token_type_ids"] = np.zeros_like(input_ids)
        (hidden_states,) = self._session.run(None, feeds)[:1]
        mask = attention_mask[:, :, None].astype(hidden_states.dtype)
        pooled = (hidden_states * mask).sum(axis=1) / mask.sum(axis=1).clip(min=1e-9)
        normalized = pooled / np.linalg.norm(pooled, axis=1, keepdims=True).clip(min=1e-12)
        return [vector.tolist() for vector in normalized]

    def embed_query(self, text: str) -> list[float]:
        """Embed a single search query."""
        return self.embed_texts([text])[0]


def build_embedder(model_name: str, backend: str) -> Embedder:
    """Construct the configured embedding backend (``torch`` or ``onnx``)."""
    if backend == "torch":
        return SentenceTransformerEmbedder(model_name)
    if backend == "onnx":
        return OnnxEmbedder(model_name)
    raise ValueError(f"unknown EMBEDDING_BACKEND {backend!r} — expected 'torch' or 'onnx'")
