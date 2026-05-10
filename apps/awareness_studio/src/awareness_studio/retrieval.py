"""
Retrieval backends.

BM25Index   — offline, pure-Python, default
EmbeddingIndex — vector cosine similarity; requires precomputed embeddings

Both expose the same interface:
    .chunks: List[Chunk]
    .retrieve(query: str, k: int) -> List[Tuple[Chunk, float]]
"""
import math
from collections import Counter
from typing import List, Tuple

from awareness_studio import config
from awareness_studio.doc_schema import Chunk
from awareness_studio.utils import simple_tokenize


# ── BM25 ──────────────────────────────────────────────────────────────────────

class BM25Index:
    def __init__(
        self,
        chunks: List[Chunk],
        k1: float = config.BM25_K1,
        b: float = config.BM25_B,
    ) -> None:
        self.chunks = chunks
        self.k1 = k1
        self.b = b
        corpus = [simple_tokenize(c.text) for c in chunks]
        self.doc_lengths = [len(doc) for doc in corpus]
        n = len(corpus)
        self.avg_dl = sum(self.doc_lengths) / n if n > 0 else 1.0
        self.tf: List[Counter] = [Counter(doc) for doc in corpus]
        df: Counter = Counter()
        for doc in corpus:
            for term in set(doc):
                df[term] += 1
        self.idf: dict = {
            term: math.log((n - freq + 0.5) / (freq + 0.5) + 1.0)
            for term, freq in df.items()
        }

    def _score(self, query_tokens: List[str], doc_idx: int) -> float:
        dl = self.doc_lengths[doc_idx]
        tf_doc = self.tf[doc_idx]
        score = 0.0
        for term in query_tokens:
            if term not in self.idf:
                continue
            f = tf_doc.get(term, 0)
            numerator = f * (self.k1 + 1)
            denominator = f + self.k1 * (1 - self.b + self.b * dl / self.avg_dl)
            score += self.idf[term] * numerator / denominator
        return score

    def retrieve(
        self, query: str, k: int = config.DEFAULT_TOP_K
    ) -> List[Tuple[Chunk, float]]:
        if not self.chunks:
            return []
        tokens = simple_tokenize(query)
        scores = sorted(
            ((i, self._score(tokens, i)) for i in range(len(self.chunks))),
            key=lambda x: x[1],
            reverse=True,
        )
        return [(self.chunks[i], s) for i, s in scores[:k] if s > 0]


# ── Embedding ────────────────────────────────────────────────────────────────

class EmbeddingIndex:
    """
    Vector similarity index.

    embeddings: precomputed vectors in the same order as chunks.
    Query vectors are computed at retrieval time via embeddings.embed_texts().
    Cosine similarity uses pure-Python fallback; numpy fast path auto-detected
    in embeddings.cosine_sim.
    """

    def __init__(self, chunks: List[Chunk], embeddings: List[List[float]]) -> None:
        self.chunks = chunks
        self.embeddings = embeddings

    def retrieve(
        self, query: str, k: int = config.DEFAULT_TOP_K
    ) -> List[Tuple[Chunk, float]]:
        if not self.chunks:
            return []
        from awareness_studio.embeddings import cosine_sim, embed_texts

        q_vec = embed_texts([query])[0]
        scores = sorted(
            ((i, cosine_sim(q_vec, self.embeddings[i])) for i in range(len(self.chunks))),
            key=lambda x: x[1],
            reverse=True,
        )
        return [(self.chunks[i], s) for i, s in scores[:k]]
