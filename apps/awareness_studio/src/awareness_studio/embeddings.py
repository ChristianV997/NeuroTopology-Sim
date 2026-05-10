"""
Embedding providers.

EMBEDDING_PROVIDER env var:
  local_stub (default) — deterministic hash-seeded unit vectors; offline; for testing
  openai               — text-embedding-3-small via urllib (no SDK needed)

Usage:
  from awareness_studio.embeddings import embed_texts
  vecs = embed_texts(["some text", "another text"])   # List[List[float]]
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import urllib.error
import urllib.request
from typing import List

from awareness_studio import config


# ── cosine similarity (pure Python; fast path via numpy if available) ─────────

try:
    import numpy as _np

    def cosine_sim(a: List[float], b: List[float]) -> float:
        va = _np.array(a)
        vb = _np.array(b)
        na, nb = _np.linalg.norm(va), _np.linalg.norm(vb)
        return float(_np.dot(va, vb) / (na * nb)) if na > 0 and nb > 0 else 0.0

except ImportError:

    def cosine_sim(a: List[float], b: List[float]) -> float:  # type: ignore[misc]
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(x * x for x in b))
        return dot / (na * nb) if na > 0 and nb > 0 else 0.0


# ── local stub ───────────────────────────────────────────────────────────────

def _stub_embed(text: str, dim: int = config.EMBEDDING_DIM) -> List[float]:
    """Deterministic unit vector seeded by SHA-256 of text.  NOT semantically meaningful."""
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    seed = int(digest[:16], 16)
    rng = random.Random(seed)
    vec = [rng.gauss(0.0, 1.0) for _ in range(dim)]
    norm = math.sqrt(sum(x * x for x in vec))
    return [x / norm for x in vec] if norm > 0 else [0.0] * dim


# ── OpenAI embeddings via urllib ─────────────────────────────────────────────

_OPENAI_EMBED_URL = "https://api.openai.com/v1/embeddings"
_BATCH_SIZE = 96  # OpenAI limit is 2048 texts; keep batches small


def _openai_embed_batch(texts: List[str]) -> List[List[float]]:
    payload = {
        "input": texts,
        "model": config.OPENAI_EMBEDDING_MODEL,
    }
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        _OPENAI_EMBED_URL,
        data=data,
        headers={
            "Authorization": f"Bearer {config.OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=config.OPENAI_TIMEOUT_S) as resp:
            result = json.load(resp)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode(errors="replace")
        raise RuntimeError(f"OpenAI embeddings {exc.code}: {body}") from exc
    # Sort by index to guarantee order matches input
    items = sorted(result["data"], key=lambda x: x["index"])
    return [item["embedding"] for item in items]


def _openai_embed(texts: List[str]) -> List[List[float]]:
    results: List[List[float]] = []
    for i in range(0, len(texts), _BATCH_SIZE):
        results.extend(_openai_embed_batch(texts[i : i + _BATCH_SIZE]))
    return results


# ── Public API ───────────────────────────────────────────────────────────────

def embed_texts(texts: List[str]) -> List[List[float]]:
    """Embed a list of strings using the configured provider.

    Returns a list of float vectors in the same order as input.
    Deterministic: same text + provider + model → same vector.
    """
    if not texts:
        return []
    provider = config.EMBEDDING_PROVIDER
    if provider == "local_stub":
        return [_stub_embed(t) for t in texts]
    if provider == "openai":
        if not config.OPENAI_API_KEY:
            raise ValueError(
                "OPENAI_API_KEY is not set. "
                "Set it or use EMBEDDING_PROVIDER=local_stub for offline testing."
            )
        return _openai_embed(texts)
    raise ValueError(
        f"Unknown EMBEDDING_PROVIDER: {provider!r}. "
        "Use 'local_stub' (offline) or 'openai'."
    )
