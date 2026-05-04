"""
Tests for embeddings.py and EmbeddingIndex.

All tests run offline (local_stub provider — no API key needed).
"""
import math
import os

import pytest

os.environ.setdefault("EMBEDDING_PROVIDER", "local_stub")
os.environ.setdefault("EMBEDDING_DIM", "64")


from awareness_studio.embeddings import (
    _stub_embed,
    cosine_sim,
    embed_texts,
)
from awareness_studio.doc_schema import Chunk
from awareness_studio.retrieval import EmbeddingIndex


# ── _stub_embed ───────────────────────────────────────────────────────────────

def test_stub_deterministic():
    v1 = _stub_embed("hello world", dim=64)
    v2 = _stub_embed("hello world", dim=64)
    assert v1 == v2, "stub must be deterministic"


def test_stub_is_unit_vector():
    v = _stub_embed("test text", dim=64)
    norm = math.sqrt(sum(x * x for x in v))
    assert abs(norm - 1.0) < 1e-9, f"norm={norm}, not a unit vector"


def test_stub_different_texts_differ():
    v1 = _stub_embed("vedana sensation", dim=64)
    v2 = _stub_embed("samsara cycles", dim=64)
    assert v1 != v2, "different texts should produce different vectors"


def test_stub_dim():
    v = _stub_embed("x", dim=32)
    assert len(v) == 32


def test_stub_default_dim():
    v = _stub_embed("x")
    assert len(v) == int(os.getenv("EMBEDDING_DIM", "64"))


# ── cosine_sim ───────────────────────────────────────────────────────────────

def test_cosine_self_similarity():
    v = _stub_embed("some text", dim=64)
    assert abs(cosine_sim(v, v) - 1.0) < 1e-9


def test_cosine_range():
    v1 = _stub_embed("a", dim=64)
    v2 = _stub_embed("b", dim=64)
    sim = cosine_sim(v1, v2)
    assert -1.0 <= sim <= 1.0


def test_cosine_zero_vector():
    zero = [0.0] * 64
    v = _stub_embed("x", dim=64)
    assert cosine_sim(zero, v) == 0.0


def test_cosine_symmetry():
    v1 = _stub_embed("alpha", dim=64)
    v2 = _stub_embed("beta", dim=64)
    assert abs(cosine_sim(v1, v2) - cosine_sim(v2, v1)) < 1e-12


# ── embed_texts ───────────────────────────────────────────────────────────────

def test_embed_texts_empty():
    result = embed_texts([])
    assert result == []


def test_embed_texts_single():
    result = embed_texts(["hello"])
    assert len(result) == 1
    assert len(result[0]) == 64


def test_embed_texts_multiple():
    texts = ["text one", "text two", "text three"]
    result = embed_texts(texts)
    assert len(result) == len(texts)


def test_embed_texts_order_stable():
    """Result order must match input order."""
    texts = ["alpha", "beta", "gamma"]
    r1 = embed_texts(texts)
    r2 = embed_texts(texts)
    assert r1 == r2


def test_embed_texts_deterministic():
    t = ["consciousness", "vedana", "tanha", "samsara"]
    assert embed_texts(t) == embed_texts(t)


def test_embed_texts_unknown_provider():
    import importlib
    import awareness_studio.config as cfg
    orig = cfg.EMBEDDING_PROVIDER
    cfg.EMBEDDING_PROVIDER = "nonexistent_provider"
    with pytest.raises(ValueError, match="Unknown EMBEDDING_PROVIDER"):
        embed_texts(["test"])
    cfg.EMBEDDING_PROVIDER = orig


# ── EmbeddingIndex ────────────────────────────────────────────────────────────

def _make_chunks():
    return [
        Chunk("c1", "Doc", "/p", "book_system", "H", "vedana sensation pleasant unpleasant", 0),
        Chunk("c2", "Doc", "/p", "book_system", "H", "tanha craving desire aversion", 1),
        Chunk("c3", "Doc", "/p", "book_seed_q3", "H", "samsara loops algorithm cycles", 2),
        Chunk("c4", "Doc", "/p", "book_seed_q4", "H", "liberation gain latch control signal", 3),
    ]


def test_embedding_index_retrieve_returns_results():
    chunks = _make_chunks()
    embs = embed_texts([c.text for c in chunks])
    idx = EmbeddingIndex(chunks, embs)
    results = idx.retrieve("vedana sensation", k=4)
    assert len(results) > 0


def test_embedding_index_retrieve_returns_tuple():
    chunks = _make_chunks()
    embs = embed_texts([c.text for c in chunks])
    idx = EmbeddingIndex(chunks, embs)
    results = idx.retrieve("tanha", k=2)
    for chunk, score in results:
        assert isinstance(chunk, Chunk)
        assert isinstance(score, float)


def test_embedding_index_empty():
    idx = EmbeddingIndex([], [])
    assert idx.retrieve("query", k=5) == []


def test_embedding_index_scores_bounded():
    chunks = _make_chunks()
    embs = embed_texts([c.text for c in chunks])
    idx = EmbeddingIndex(chunks, embs)
    for _, score in idx.retrieve("signal control", k=4):
        assert -1.0 <= score <= 1.0


def test_embedding_index_sorted_descending():
    chunks = _make_chunks()
    embs = embed_texts([c.text for c in chunks])
    idx = EmbeddingIndex(chunks, embs)
    results = idx.retrieve("vedana sensation pleasant", k=4)
    scores = [s for _, s in results]
    assert scores == sorted(scores, reverse=True)


# ── End-to-end: index_build with embedding backend ───────────────────────────

def test_index_build_embedding_e2e(tmp_path):
    """Full pipeline: markdown → chunk → embed → EmbeddingIndex → retrieve."""
    # Write a tiny markdown file
    (tmp_path / "sample.md").write_text(
        "# Vedana\n\n## Definition\n\nVedana is sensation tone.\n\n## Practice\n\nObserve the tone.",
        encoding="utf-8",
    )

    import awareness_studio.config as cfg
    orig_backend = cfg.INDEX_BACKEND
    orig_provider = cfg.EMBEDDING_PROVIDER
    cfg.INDEX_BACKEND = "embedding"
    cfg.EMBEDDING_PROVIDER = "local_stub"

    # Point DATA_DIR to tmp
    orig_data = cfg.DATA_DIR
    cfg.DATA_DIR = tmp_path / ".data"

    import awareness_studio.index_build as ib
    ib._embedding_cache = None

    try:
        idx = ib.build_index(inputs_dir=tmp_path, backend="embedding")
        assert len(idx.chunks) > 0
        results = idx.retrieve("sensation vedana", k=3)
        assert len(results) > 0
        # Verify the index contains expected content (stub embedding is not semantic)
        all_text = " ".join(c.text.lower() for c in idx.chunks)
        assert "vedana" in all_text or "sensation" in all_text
    finally:
        cfg.INDEX_BACKEND = orig_backend
        cfg.EMBEDDING_PROVIDER = orig_provider
        cfg.DATA_DIR = orig_data
        ib._embedding_cache = None
