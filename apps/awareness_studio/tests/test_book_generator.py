import pytest

from awareness_studio.book_generator import (
    _QUADRANT_VOICES,
    _BOOK_SYSTEM_ADDON,
    build_book_prompt,
)
from awareness_studio.doc_schema import Chunk


def _chunk(
    text: str = "Content.",
    kind: str = "book_system",
    title: str = "Test Source",
    cid: str = "abc123",
) -> Chunk:
    return Chunk(
        chunk_id=cid,
        source_title=title,
        source_path="/test/doc.md",
        source_kind=kind,
        heading_path="Section",
        text=text,
        index=0,
    )


# --- quadrant voice registry ---

def test_all_quadrants_defined():
    for q in ("q1", "q2", "q3", "q4"):
        assert q in _QUADRANT_VOICES
        assert "voice" in _QUADRANT_VOICES[q]
        assert "name" in _QUADRANT_VOICES[q]


def test_q1_voice_warmth():
    assert "warm" in _QUADRANT_VOICES["q1"]["voice"].lower() or "story" in _QUADRANT_VOICES["q1"]["voice"].lower()


def test_q2_voice_pali():
    voice = _QUADRANT_VOICES["q2"]["voice"].lower()
    assert "pali" in voice or "ebt" in voice


def test_q3_voice_science():
    voice = _QUADRANT_VOICES["q3"]["voice"].lower()
    assert "algorithm" in voice or "signal" in voice or "loop" in voice


def test_q4_voice_rigour():
    voice = _QUADRANT_VOICES["q4"]["voice"].lower()
    assert "falsif" in voice or "hypothesis" in voice or "formal" in voice


# --- build_book_prompt ---

def test_build_book_prompt_returns_strings():
    system, user = build_book_prompt("q1", "Test Chapter", 900, [_chunk()])
    assert isinstance(system, str) and len(system) > 50
    assert isinstance(user, str) and len(user) > 50


def test_build_book_prompt_chapter_in_user():
    _, user = build_book_prompt("q2", "Vedana as Signal", 600, [_chunk()])
    assert "Vedana as Signal" in user


def test_build_book_prompt_word_count_in_user():
    _, user = build_book_prompt("q3", "Loops", 750, [_chunk()])
    assert "750" in user


def test_build_book_prompt_quadrant_name_in_user():
    _, user = build_book_prompt("q4", "Chapter", 1000, [_chunk()])
    assert "Q4" in user or "PhD" in user or "Liberation" in user


def test_build_book_prompt_practices_in_system():
    system, _ = build_book_prompt("q1", "Chapter", 900, [_chunk()])
    assert "Practices" in system


def test_build_book_prompt_falsifiers_in_system():
    system, _ = build_book_prompt("q2", "Chapter", 900, [_chunk()])
    assert "Falsifiers" in system


def test_build_book_prompt_confusions_in_system():
    system, _ = build_book_prompt("q3", "Chapter", 900, [_chunk()])
    assert "confusions" in system.lower()


def test_build_book_prompt_preguntas_duras_in_system():
    system, _ = build_book_prompt("q4", "Chapter", 900, [_chunk()])
    system_lower = system.lower()
    assert "preguntas duras" in system_lower or "hard questions" in system_lower


def test_build_book_prompt_samsara_perspective_in_system():
    system, _ = build_book_prompt("q1", "Samsara loops", 900, [_chunk()])
    assert "perspective" in system.lower() or "traditional" in system.lower()


def test_build_book_prompt_six_element_matrix_in_system():
    system, _ = build_book_prompt("q1", "Any", 900, [_chunk()])
    assert "6-element" in system or "six" in system.lower() or "matrix" in system.lower()


def test_build_book_prompt_sources_appended():
    c = _chunk("Vedana.", "book_seed_q2", "Book Q2", "cid001")
    _, user = build_book_prompt("q2", "Vedana", 600, [c])
    assert "Sources used" in user
    assert "Book Q2" in user
    assert "cid001" in user


def test_build_book_prompt_role_labels_instruction():
    system, _ = build_book_prompt("q3", "Loops", 700, [_chunk()])
    assert "Direct teaching" in system
    assert "Method-synthesis" in system
    assert "Hypothesis" in system


def test_build_book_prompt_multiple_chunks():
    chunks = [_chunk(f"Content {i}.", cid=f"id{i}") for i in range(5)]
    system, user = build_book_prompt("q1", "Multi", 1200, chunks)
    assert "Content 0" in user
    assert "Content 4" in user
