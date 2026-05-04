import pytest

from awareness_studio.chunking import (
    _split_by_headings,
    _split_long_text,
    chunk_document,
)
from awareness_studio.doc_schema import Document


def _doc(text: str, path: str = "/test/doc.md", kind: str = "other") -> Document:
    return Document(
        title="Test Doc",
        source_path=path,
        source_kind=kind,
        headings=[],
        raw_text=text,
    )


# --- _split_by_headings ---

def test_split_no_headings():
    sections = _split_by_headings("Plain text without headings.")
    assert len(sections) == 1
    assert sections[0] == ("(root)", "Plain text without headings.")


def test_split_empty_text():
    sections = _split_by_headings("")
    assert sections == []


def test_split_basic_headings():
    text = "## Section A\n\nContent A.\n\n## Section B\n\nContent B."
    sections = _split_by_headings(text)
    assert len(sections) == 2
    paths = [p for p, _ in sections]
    assert any("Section A" in p for p in paths)
    assert any("Section B" in p for p in paths)


def test_split_preamble_before_heading():
    text = "Preamble text.\n\n## Section\n\nBody."
    sections = _split_by_headings(text)
    assert len(sections) == 2
    assert sections[0][0] == "(root)"
    assert "Preamble" in sections[0][1]


def test_split_nested_headings():
    text = "## Parent\n\nParent body.\n\n### Child\n\nChild body."
    sections = _split_by_headings(text)
    assert len(sections) == 2
    child_path = [p for p, _ in sections if "Child" in p]
    assert len(child_path) == 1
    assert "Parent" in child_path[0]


def test_split_heading_with_no_body_skipped():
    text = "## Empty\n\n## HasContent\n\nSome text here."
    sections = _split_by_headings(text)
    assert all("HasContent" in p or "text" in t for p, t in sections)


# --- _split_long_text ---

def test_split_long_text_short():
    result = _split_long_text("Short.", max_chars=1000, overlap=100)
    assert result == ["Short."]


def test_split_long_text_exact_boundary():
    text = "a" * 1000
    result = _split_long_text(text, max_chars=1000, overlap=100)
    assert len(result) == 1


def test_split_long_text_creates_multiple_chunks():
    text = "x" * 2500
    result = _split_long_text(text, max_chars=1000, overlap=100)
    assert len(result) > 1
    for chunk in result:
        assert len(chunk) <= 1000


def test_split_long_text_overlap():
    text = "a" * 1000 + "b" * 1000
    result = _split_long_text(text, max_chars=1000, overlap=200)
    assert len(result) >= 2
    # second chunk starts 800 chars in, so it begins with 'a's
    assert result[1][0] == "a"


# --- chunk_document ---

def test_chunk_document_produces_chunks():
    doc = _doc("## Section\n\nSome content here.", "/test/a.md")
    chunks = chunk_document(doc)
    assert len(chunks) > 0


def test_chunk_document_stable_ids():
    doc = _doc("## S1\n\nContent.\n\n## S2\n\nMore.", "/test/stable.md")
    ids1 = [c.chunk_id for c in chunk_document(doc)]
    ids2 = [c.chunk_id for c in chunk_document(doc)]
    assert ids1 == ids2


def test_chunk_document_different_paths_differ():
    text = "## Section\n\nContent."
    ids_a = [c.chunk_id for c in chunk_document(_doc(text, "/test/a.md"))]
    ids_b = [c.chunk_id for c in chunk_document(_doc(text, "/test/b.md"))]
    assert ids_a != ids_b


def test_chunk_document_metadata_propagated():
    doc = _doc("## Alpha\n\nBody text.", "/test/meta.md", "book_seed_q1")
    doc.title = "My Title"
    chunks = chunk_document(doc)
    c = chunks[0]
    assert c.source_title == "My Title"
    assert c.source_kind == "book_seed_q1"
    assert c.source_path == "/test/meta.md"
    assert "Alpha" in c.heading_path


def test_chunk_document_ids_unique():
    doc = _doc(
        "## S1\n\nContent 1.\n\n## S2\n\nContent 2.\n\n## S3\n\nContent 3.",
        "/test/uniq.md",
    )
    ids = [c.chunk_id for c in chunk_document(doc)]
    assert len(ids) == len(set(ids))


def test_chunk_document_index_sequential():
    doc = _doc("## A\n\nText.\n\n## B\n\nText.", "/test/idx.md")
    chunks = chunk_document(doc)
    for i, c in enumerate(chunks):
        assert c.index == i
