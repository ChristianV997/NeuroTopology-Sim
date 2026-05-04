import re
from typing import List, Tuple

from awareness_studio import config
from awareness_studio.doc_schema import Chunk, Document
from awareness_studio.utils import stable_id


def _split_by_headings(text: str) -> List[Tuple[str, str]]:
    """Split text into (heading_path, body) sections by markdown headings."""
    pattern = re.compile(r"^(#{1,3})\s+(.+)", re.MULTILINE)
    matches = list(pattern.finditer(text))

    if not matches:
        stripped = text.strip()
        return [("(root)", stripped)] if stripped else []

    sections: List[Tuple[str, str]] = []
    heading_stack: List[Tuple[int, str]] = []

    def current_path() -> str:
        return " > ".join(h for _, h in heading_stack) if heading_stack else "(root)"

    preamble = text[: matches[0].start()].strip()
    if preamble:
        sections.append(("(root)", preamble))

    for i, m in enumerate(matches):
        level = len(m.group(1))
        heading = m.group(2).strip()
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()

        while heading_stack and heading_stack[-1][0] >= level:
            heading_stack.pop()
        heading_stack.append((level, heading))

        if body:
            sections.append((current_path(), body))

    return sections


def _split_long_text(text: str, max_chars: int, overlap: int) -> List[str]:
    if len(text) <= max_chars:
        return [text]
    chunks: List[str] = []
    start = 0
    while start < len(text):
        end = start + max_chars
        chunks.append(text[start:end])
        if end >= len(text):
            break
        start = end - overlap
    return chunks


def chunk_document(doc: Document) -> List[Chunk]:
    sections = _split_by_headings(doc.raw_text)
    chunks: List[Chunk] = []
    for heading_path, body in sections:
        sub_texts = _split_long_text(body, config.MAX_CHUNK_CHARS, config.CHUNK_OVERLAP_CHARS)
        for sub_i, sub_text in enumerate(sub_texts):
            if not sub_text.strip():
                continue
            idx = len(chunks)
            cid = stable_id(doc.source_path, heading_path, sub_i)
            chunks.append(
                Chunk(
                    chunk_id=cid,
                    source_title=doc.title,
                    source_path=doc.source_path,
                    source_kind=doc.source_kind,
                    heading_path=heading_path,
                    text=sub_text.strip(),
                    index=idx,
                )
            )
    return chunks


def chunk_documents(docs: List[Document]) -> List[Chunk]:
    all_chunks: List[Chunk] = []
    for doc in docs:
        all_chunks.extend(chunk_document(doc))
    return all_chunks
