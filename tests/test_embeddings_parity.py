"""ONNX ↔ torch embedding parity (ADR-0015).

The deployed web app embeds queries with onnxruntime against an index that
was built with the torch backend — these tests are the contract that both
backends produce the same vectors. They download models on first run and are
skipped automatically when the model cache/network is unavailable.
"""

import numpy as np
import pytest

from legal_discovery_graph.retrieval import OnnxEmbedder, SentenceTransformerEmbedder

_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
_QUERIES = [
    "Who approved the payments to Northgate Supply Group?",
    "invoice for consulting services",
    "What did the audit find about Project Falcon?",
]


@pytest.fixture(scope="module")
def vectors() -> tuple[np.ndarray, np.ndarray]:
    try:
        torch_vecs = np.asarray(SentenceTransformerEmbedder(_MODEL).embed_texts(_QUERIES))
        onnx_vecs = np.asarray(OnnxEmbedder(_MODEL).embed_texts(_QUERIES))
    except Exception as exc:  # model download/load requires network on first run
        pytest.skip(f"embedding models unavailable: {exc}")
    return torch_vecs, onnx_vecs


def test_backends_produce_matching_vectors(vectors: tuple[np.ndarray, np.ndarray]) -> None:
    torch_vecs, onnx_vecs = vectors
    cosines = (torch_vecs * onnx_vecs).sum(axis=1)  # both are L2-normalized
    assert cosines.min() > 0.9999, f"backend divergence: cosine similarities {cosines}"


def test_onnx_vectors_are_normalized_and_384_dim(vectors: tuple[np.ndarray, np.ndarray]) -> None:
    _, onnx_vecs = vectors
    assert onnx_vecs.shape == (len(_QUERIES), 384)
    np.testing.assert_allclose(np.linalg.norm(onnx_vecs, axis=1), 1.0, atol=1e-6)


def test_build_embedder_rejects_unknown_backend() -> None:
    from legal_discovery_graph.retrieval import build_embedder

    with pytest.raises(ValueError, match="EMBEDDING_BACKEND"):
        build_embedder(_MODEL, "tensorflow")
