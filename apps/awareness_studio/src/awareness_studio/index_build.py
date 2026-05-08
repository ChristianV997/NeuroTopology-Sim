"""
Build and load the retrieval index.

Usage:
    python -m awareness_studio.index_build [--force] [--backend bm25|embedding] [--inputs-dir PATH]
"""
import argparse
import json
import logging
import sys
from dataclasses import asdict
from pathlib import Path
from typing import List, Optional, Union

from awareness_studio import config
from awareness_studio.chunking import chunk_documents
from awareness_studio.doc_schema import Chunk
from awareness_studio.io_markdown import load_documents
from awareness_studio.retrieval import BM25Index

logger = logging.getLogger(__name__)

_INDEX_FILE = config.INDEX_DIR / "chunks.json"
_EMBEDDING_FILE = config.DATA_DIR / "embeddings.json"

_bm25_cache: Optional[BM25Index] = None
_embedding_cache = None  # EmbeddingIndex, typed lazily to avoid circular import


# ── helpers ──────────────────────────────────────────────────────────────────

# Default sim_artifacts input directory (relative to this app's root)
_SIM_ARTIFACTS_DIR: Path = config.APP_ROOT / "inputs" / "sim_artifacts"


def _load_docs_or_exit(inputs_dir: Path) -> list:
    if not inputs_dir.exists():
        logger.warning(
            "Inputs directory not found: %s\n"
            "  mkdir -p %s && cp your_exports/*.md %s/\n"
            "  Then re-run: awareness-index --force",
            inputs_dir, inputs_dir, inputs_dir,
        )
        return []
    # Use rglob to discover files recursively (Notion exports nested folders)
    md_files = list(inputs_dir.rglob("*.md"))
    if not md_files:
        logger.warning(
            "No .md files found in %s (searched recursively)\n"
            "  Export Notion pages as Markdown → drop into that directory → run:\n"
            "  awareness-index --force",
            inputs_dir,
        )
        return []
    docs = load_documents(inputs_dir)
    if not docs:
        logger.warning("All .md files were skipped (meta-only). Add content pages.")
        return []

    from collections import Counter
    kind_counts = Counter(d.source_kind for d in docs)
    logger.info(
        "Loaded %d document(s) from %s  [%s]",
        len(docs), inputs_dir,
        "  ".join(f"{k}×{v}" for k, v in sorted(kind_counts.items())),
    )
    return docs


def _load_sim_artifact_docs() -> list:
    """Load simulation artifact Markdown docs if the sim_artifacts folder exists."""
    if not _SIM_ARTIFACTS_DIR.exists():
        return []
    md_files = list(_SIM_ARTIFACTS_DIR.glob("*.md"))
    if not md_files:
        return []
    docs = load_documents(_SIM_ARTIFACTS_DIR)
    logger.info("Loaded %d sim artifact doc(s) from %s", len(docs), _SIM_ARTIFACTS_DIR)
    return docs


def invalidate_cache() -> None:
    global _bm25_cache, _embedding_cache
    _bm25_cache = None
    _embedding_cache = None
    if _INDEX_FILE.exists():
        _INDEX_FILE.unlink()
        logger.info("Removed %s", _INDEX_FILE)
    if _EMBEDDING_FILE.exists():
        _EMBEDDING_FILE.unlink()
        logger.info("Removed %s", _EMBEDDING_FILE)


# ── BM25 ─────────────────────────────────────────────────────────────────────

def _build_bm25(chunks: List[Chunk]) -> BM25Index:
    global _bm25_cache
    config.INDEX_DIR.mkdir(parents=True, exist_ok=True)
    with open(_INDEX_FILE, "w", encoding="utf-8") as fh:
        json.dump([asdict(c) for c in chunks], fh, ensure_ascii=False, indent=2)
    logger.info("BM25 index saved → %s  (%d chunks)", _INDEX_FILE, len(chunks))
    _bm25_cache = BM25Index(chunks)
    return _bm25_cache


def _load_bm25() -> Optional[BM25Index]:
    global _bm25_cache
    if _bm25_cache is not None:
        return _bm25_cache
    if _INDEX_FILE.exists():
        with open(_INDEX_FILE, encoding="utf-8") as fh:
            raw = json.load(fh)
        chunks: List[Chunk] = [Chunk(**item) for item in raw]
        logger.debug("Loaded BM25 index from disk (%d chunks)", len(chunks))
        _bm25_cache = BM25Index(chunks)
        return _bm25_cache
    return None


# ── Embedding ────────────────────────────────────────────────────────────────

def _build_embedding(chunks: List[Chunk]):
    global _embedding_cache
    from awareness_studio.embeddings import embed_texts
    from awareness_studio.retrieval import EmbeddingIndex

    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    texts = [c.text for c in chunks]
    logger.info(
        "Computing %d embeddings (provider=%s)…", len(texts), config.EMBEDDING_PROVIDER
    )
    embeddings = embed_texts(texts)
    data = {
        "chunks": [asdict(c) for c in chunks],
        "embeddings": embeddings,
        "provider": config.EMBEDDING_PROVIDER,
    }
    with open(_EMBEDDING_FILE, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False)
    logger.info("Embeddings saved → %s", _EMBEDDING_FILE)
    _embedding_cache = EmbeddingIndex(chunks, embeddings)
    return _embedding_cache


def _load_embedding():
    global _embedding_cache
    if _embedding_cache is not None:
        return _embedding_cache
    if _EMBEDDING_FILE.exists():
        from awareness_studio.retrieval import EmbeddingIndex
        with open(_EMBEDDING_FILE, encoding="utf-8") as fh:
            data = json.load(fh)
        chunks = [Chunk(**c) for c in data["chunks"]]
        logger.debug("Loaded embedding index from disk (%d chunks)", len(chunks))
        _embedding_cache = EmbeddingIndex(chunks, data["embeddings"])
        return _embedding_cache
    return None


# ── Public API ───────────────────────────────────────────────────────────────

def build_index(
    inputs_dir: Optional[Union[Path, str]] = None,
    backend: Optional[str] = None,
) -> Union[BM25Index, "EmbeddingIndex"]:
    """Always rebuilds. Use get_or_build_index() for cached access."""
    backend = backend or config.INDEX_BACKEND
    inputs_dir = Path(inputs_dir) if inputs_dir else config.INPUTS_DIR

    docs = _load_docs_or_exit(inputs_dir)

    # Also include simulation artifact docs (closed-loop Studio↔Sim bridge)
    sim_docs = _load_sim_artifact_docs()
    docs = docs + sim_docs

    if not docs:
        # Return empty index rather than crashing
        if backend == "embedding":
            from awareness_studio.retrieval import EmbeddingIndex
            return EmbeddingIndex([], [])
        return BM25Index([])

    chunks = chunk_documents(docs)
    logger.info("Chunked into %d chunks (backend=%s)", len(chunks), backend)

    if backend == "embedding":
        return _build_embedding(chunks)
    return _build_bm25(chunks)


def get_or_build_index(
    inputs_dir: Optional[Union[Path, str]] = None,
) -> Union[BM25Index, "EmbeddingIndex"]:
    """Return cached index, load from disk if possible, or build fresh."""
    backend = config.INDEX_BACKEND
    if backend == "embedding":
        cached = _load_embedding()
        if cached is not None:
            return cached
    else:
        cached = _load_bm25()
        if cached is not None:
            return cached
    return build_index(inputs_dir, backend=backend)


# ── CLI entry point ───────────────────────────────────────────────────────────

def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
    parser = argparse.ArgumentParser(
        description="Build the Awareness Studio retrieval index from Notion exports."
    )
    parser.add_argument(
        "--force", action="store_true",
        help="Rebuild even if a cached index already exists",
    )
    parser.add_argument(
        "--backend", choices=["bm25", "embedding"], default=None,
        help="Index backend (default: INDEX_BACKEND env var, fallback 'bm25')",
    )
    parser.add_argument(
        "--inputs-dir", default=None,
        help="Override inputs directory (default: NOTION_EXPORT_DIR env var or inputs/notion_export/)",
    )
    args = parser.parse_args()

    if args.force:
        invalidate_cache()

    backend = args.backend or config.INDEX_BACKEND
    inputs_dir = Path(args.inputs_dir) if args.inputs_dir else config.INPUTS_DIR

    idx = build_index(inputs_dir=inputs_dir, backend=backend)
    n = len(idx.chunks)
    if n == 0:
        print(
            f"[WARN] Empty index. Drop .md files into {inputs_dir} and re-run with --force.",
            file=sys.stderr,
        )
        sys.exit(1)
    print(f"[OK]  backend={backend}  chunks={n}  inputs={inputs_dir}", file=sys.stderr)


if __name__ == "__main__":
    main()
