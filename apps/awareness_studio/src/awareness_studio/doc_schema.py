from dataclasses import dataclass
from typing import List


@dataclass
class Document:
    title: str
    source_path: str
    source_kind: str
    headings: List[str]
    raw_text: str


@dataclass
class Chunk:
    chunk_id: str
    source_title: str
    source_path: str
    source_kind: str
    heading_path: str
    text: str
    index: int
