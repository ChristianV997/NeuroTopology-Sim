import re
from pathlib import Path
from typing import List

from awareness_studio.doc_schema import Document

_SOURCE_KIND_PATTERNS: List[tuple] = [
    ("book_system",     [r"book_system", r"book.seed.*arte.*soltar", r"sistema.*generaci"]),
    ("book_seed_q1",    [r"book_seed_q1", r"q1[^0-9]", r"autoayuda", r"soltar.para.vivir"]),
    ("book_seed_q2",    [r"book_seed_q2", r"q2[^0-9]", r"therav", r"manual.*soltar"]),
    ("book_seed_q3",    [r"book_seed_q3", r"q3[^0-9]", r"esc[eé]ptic", r"soltar.sin.creer"]),
    ("book_seed_q4",    [r"book_seed_q4", r"q4[^0-9]", r"liberation.eng", r"rigor.phd"]),
    ("answer_templates",[r"answer_templates", r"answer.template", r"monk.*scientist.*bot"]),
    ("rag_plan",        [r"rag_plan", r"rag.chatbot.*dev", r"development.plan"]),
]


def infer_source_kind(path: Path) -> str:
    name = path.stem.lower()
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
    docs: List[Document] = []
    for md_path in sorted(inputs_dir.glob("*.md")):
        text = md_path.read_text(encoding="utf-8")
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
            )
        )
    return docs
