"""
Markdown document loader.

Loads all .md files recursively from a directory tree (supports
nested Notion export folders like "Page Title/Page Body.md").

Source kind is inferred heuristically from the file path stem.
Document IDs are stable SHA-256 hashes of the path relative to inputs_dir
so they survive renames of the parent directory.
"""
import hashlib
import re
from pathlib import Path
from typing import List

from awareness_studio.doc_schema import Document

_SOURCE_KIND_PATTERNS: List[tuple] = [
    ("theravada_sutta",   [r"theravada", r"suttacentral", r"sutta", r"pali", r"tipitaka"]),
    ("book_system",      [r"book_system", r"book.seed.*arte.*soltar", r"sistema.*generaci"]),
    ("book_seed_q1",     [r"book_seed_q1", r"q1[^0-9]", r"autoayuda", r"soltar.para.vivir"]),
    ("book_seed_q2",     [r"book_seed_q2", r"q2[^0-9]", r"therav", r"manual.*soltar"]),
    ("book_seed_q3",     [r"book_seed_q3", r"q3[^0-9]", r"esc[eé]ptic", r"soltar.sin.creer"]),
    ("book_seed_q4",     [r"book_seed_q4", r"q4[^0-9]", r"liberation.eng", r"rigor.phd"]),
    ("answer_templates", [r"answer_templates", r"answer.template", r"monk.*scientist.*bot"]),
    ("rag_plan",         [r"rag_plan", r"rag.chatbot.*dev", r"development.plan"]),
]

_SKIP_NAMES = frozenset({"readme", ".gitkeep", "changelog", "license"})


def _stable_doc_id(rel_path: str) -> str:
    return hashlib.sha256(rel_path.encode("utf-8")).hexdigest()[:16]


def infer_source_kind(path: Path) -> str:
    """Match a Markdown path (case-insensitive) against known source-kind patterns."""
    # Include parent directory names so nested exports such as
    # ``notion_export/SuttaCentral/sn22_59.md`` retain their source kind.
    name = path.with_suffix("").as_posix().lower()
    for kind, patterns in _SOURCE_KIND_PATTERNS:
        for pat in patterns:
            if re.search(pat, name):
                return kind
    return "other"


def _extract_title(lines: List[str], fallback: str) -> str:
    for line in lines:
        m = re.match(r"^#{1,2}\s+(.+)", line)
        if m:
            return m.group(1).strip()
    return fallback


def _extract_headings(lines: List[str]) -> List[str]:
    return [
        m.group(2).strip()
        for line in lines
        if (m := re.match(r"^(#{1,6})\s+(.+)", line))
    ]


def load_documents(inputs_dir: Path) -> List[Document]:
    """
    Load all .md files recursively under inputs_dir.

    - Sorts by relative path for stable ordering.
    - Skips README / .gitkeep / meta files.
    - Skips *.run.json sim artifacts (handled by airtable_sync, not RAG ingestion).
    - Assigns stable doc_id = sha256(rel_path)[:16].
    """
    inputs_dir = inputs_dir.resolve()
    docs: List[Document] = []

    # rglob for recursive discovery; sort for determinism.
    # Only *.md files are collected — *.run.json sim artifacts are intentionally excluded here
    # (they are consumed by airtable_sync, not RAG ingestion).
    md_paths = sorted(inputs_dir.rglob("*.md"))

    for md_path in md_paths:
        # Skip meta files anywhere in the tree
        if md_path.stem.lower() in _SKIP_NAMES:
            continue

        rel = str(md_path.relative_to(inputs_dir))
        doc_id = _stable_doc_id(rel)

        try:
            text = md_path.read_text(encoding="utf-8")
        except OSError:
            continue

        lines = text.splitlines()
        title = _extract_title(lines, md_path.stem)
        headings = _extract_headings(lines)
        kind = infer_source_kind(md_path)

        docs.append(
            Document(
                title=title,
                source_path=str(md_path),
                source_kind=kind,
                headings=headings,
                raw_text=text,
                doc_id=doc_id,
            )
        )

    return docs