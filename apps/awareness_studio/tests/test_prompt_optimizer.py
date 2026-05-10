"""
Tests for prompt_optimizer.py — all offline, no LLM key needed.
"""
import os

import pytest

os.environ.setdefault("PROMPT_OPTIMIZER", "none")

from awareness_studio.prompt_optimizer import (
    DSPyStubOptimizer,
    PassthroughOptimizer,
    _get_optimizer,
    get_optimized_prompt,
    score_no_certainty_leak,
    score_response,
    score_role_label_compliance,
    score_sources_present,
)
from awareness_studio.doc_schema import Chunk


# ── Scoring helpers ───────────────────────────────────────────────────────────

def test_role_label_score_empty():
    assert score_role_label_compliance("") == 0.0


def test_role_label_score_all_labelled():
    resp = "[Direct teaching] vedana is tone. [Method-synthesis] work with it. [Hypothesis] maybe."
    score = score_role_label_compliance(resp)
    assert score > 0.0


def test_role_label_score_none_labelled():
    resp = "vedana is tone. craving follows. liberation is possible."
    score = score_role_label_compliance(resp)
    assert score == 0.0


def test_sources_present_yes():
    assert score_sources_present("some text\n## Sources used\n- chunk `c1`") == 1.0


def test_sources_present_no():
    assert score_sources_present("some text without sources") == 0.0


def test_no_certainty_leak_clean():
    assert score_no_certainty_leak("Vedana is the sensation tone.") == 1.0


def test_no_certainty_leak_dirty():
    assert score_no_certainty_leak("I am certain that vedana is X.") == 0.0


def test_no_certainty_leak_case_insensitive():
    assert score_no_certainty_leak("It Is Proven that tanha causes dukkha.") == 0.0


def test_score_response_keys():
    result = score_response("some answer")
    assert set(result.keys()) == {"role_label_compliance", "sources_present", "no_certainty_leak"}


def test_score_response_ranges():
    result = score_response("[Direct teaching] vedana. ## Sources used\n- c1")
    assert 0.0 <= result["role_label_compliance"] <= 1.0
    assert result["sources_present"] == 1.0
    assert result["no_certainty_leak"] == 1.0


# ── Optimizer factory ─────────────────────────────────────────────────────────

def test_get_optimizer_none_returns_passthrough():
    import awareness_studio.prompt_optimizer as po
    orig = po.PROMPT_OPTIMIZER
    po.PROMPT_OPTIMIZER = "none"
    try:
        opt = _get_optimizer()
        assert isinstance(opt, PassthroughOptimizer)
    finally:
        po.PROMPT_OPTIMIZER = orig


def test_get_optimizer_dspy_stub():
    import awareness_studio.prompt_optimizer as po
    orig = po.PROMPT_OPTIMIZER
    po.PROMPT_OPTIMIZER = "dspy_stub"
    try:
        opt = _get_optimizer()
        assert isinstance(opt, DSPyStubOptimizer)
    finally:
        po.PROMPT_OPTIMIZER = orig


def test_get_optimizer_unknown_falls_back():
    import awareness_studio.prompt_optimizer as po
    orig = po.PROMPT_OPTIMIZER
    po.PROMPT_OPTIMIZER = "nonexistent"
    try:
        opt = _get_optimizer()
        assert isinstance(opt, PassthroughOptimizer)
    finally:
        po.PROMPT_OPTIMIZER = orig


# ── Prompt output ─────────────────────────────────────────────────────────────

def _make_chunks():
    return [
        Chunk("c1", "Doc", "/p", "book_system", "H", "vedana sensation pleasant", 0),
    ]


def test_passthrough_returns_tuple():
    opt = PassthroughOptimizer()
    result = opt.optimize("What is vedana?", "EXPLAIN", _make_chunks())
    assert isinstance(result, tuple) and len(result) == 2


def test_passthrough_system_not_empty():
    opt = PassthroughOptimizer()
    system, _ = opt.optimize("What is vedana?", "EXPLAIN", _make_chunks())
    assert len(system) > 0


def test_dspy_stub_returns_same_as_passthrough():
    chunks = _make_chunks()
    pt = PassthroughOptimizer()
    ds = DSPyStubOptimizer()
    assert pt.optimize("q", "TEACH", chunks) == ds.optimize("q", "TEACH", chunks)


def test_get_optimized_prompt_returns_tuple():
    result = get_optimized_prompt("What is tanha?", "EXPLAIN", _make_chunks())
    assert isinstance(result, tuple) and len(result) == 2


def test_dspy_stub_score_and_log_returns_dict():
    opt = DSPyStubOptimizer()
    scores = opt.score_and_log(
        "[Direct teaching] vedana. ## Sources used\n- c1",
        "What is vedana?",
        "EXPLAIN",
    )
    assert "role_label_compliance" in scores
    assert "sources_present" in scores
