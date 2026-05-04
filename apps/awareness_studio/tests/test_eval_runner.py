"""Unit tests for eval_runner — no LLM calls."""
import json
from pathlib import Path

import pytest

from awareness_studio.eval_runner import (
    EvalResult,
    _check_no_llm,
    _DEFAULT_GOLDEN,
    run_eval,
)


# ── Golden file sanity ────────────────────────────────────────────────────────

def test_golden_file_exists():
    assert _DEFAULT_GOLDEN.exists(), f"Golden file not found: {_DEFAULT_GOLDEN}"


def test_golden_file_parseable():
    with open(_DEFAULT_GOLDEN, encoding="utf-8") as fh:
        data = json.load(fh)
    assert isinstance(data, list) and len(data) > 0


def test_golden_entries_have_required_fields():
    with open(_DEFAULT_GOLDEN, encoding="utf-8") as fh:
        data = json.load(fh)
    required = {"id", "mode", "question", "must_include", "must_not_include", "min_sources"}
    for entry in data:
        missing = required - entry.keys()
        assert not missing, f"Entry {entry.get('id')} missing fields: {missing}"


def test_golden_modes_valid():
    valid_modes = {"TEACH", "EXPLAIN", "ELABORATE", "MATRIX", "CARD", "CANONICAL"}
    with open(_DEFAULT_GOLDEN, encoding="utf-8") as fh:
        data = json.load(fh)
    for entry in data:
        assert entry["mode"] in valid_modes, f"Invalid mode: {entry['mode']}"


def test_golden_ids_unique():
    with open(_DEFAULT_GOLDEN, encoding="utf-8") as fh:
        data = json.load(fh)
    ids = [e["id"] for e in data]
    assert len(ids) == len(set(ids)), "Duplicate question IDs"


# ── run_eval (no-LLM) ─────────────────────────────────────────────────────────

def test_run_eval_no_llm_all_pass():
    results = run_eval(no_llm=True, verbose=False)
    assert all(r.passed for r in results), [
        f"{r.question_id}: {r.failures}" for r in results if not r.passed
    ]


def test_run_eval_no_llm_returns_eval_results():
    results = run_eval(no_llm=True, verbose=False)
    assert all(isinstance(r, EvalResult) for r in results)


def test_run_eval_no_llm_llm_used_is_false():
    results = run_eval(no_llm=True, verbose=False)
    assert all(not r.llm_used for r in results)


def test_run_eval_ids_filter():
    results = run_eval(no_llm=True, verbose=False, ids=["q001", "q003"])
    assert len(results) == 2
    assert {r.question_id for r in results} == {"q001", "q003"}


def test_run_eval_retrieved_count_positive():
    results = run_eval(no_llm=True, verbose=False, ids=["q001"])
    assert results[0].retrieved_count > 0


def test_run_eval_no_llm_single_question():
    """Spot-check the most important question: not-self via controllability."""
    results = run_eval(no_llm=True, verbose=False, ids=["q001"])
    r = results[0]
    assert r.passed, r.failures
    assert r.retrieved_count >= 2


# ── _check_no_llm edge cases ─────────────────────────────────────────────────

def _make_entry(must_include=None, must_not_include=None, min_sources=1):
    return {
        "id": "test",
        "mode": "EXPLAIN",
        "question": "What is vedana?",
        "must_include": must_include or [],
        "must_not_include": must_not_include or [],
        "min_sources": min_sources,
    }


def test_check_no_llm_min_sources_too_high():
    entry = _make_entry(min_sources=999)
    result = _check_no_llm(entry, k=8, verbose=False)
    assert not result.passed
    assert any("min_sources" in f for f in result.failures)


def test_check_no_llm_must_include_in_system_prompt():
    """'Direct teaching' is in the system prompt — must_include should pass."""
    entry = _make_entry(must_include=["Direct teaching"])
    result = _check_no_llm(entry, k=8, verbose=False)
    assert result.passed, result.failures


def test_check_no_llm_must_include_absent():
    entry = _make_entry(must_include=["ZZZNEVERINTHEPROMPTZZZ"])
    result = _check_no_llm(entry, k=8, verbose=False)
    assert not result.passed
    assert any("must_include" in f for f in result.failures)


def test_check_no_llm_must_not_include_not_in_system():
    """'I am certain' must NOT appear in SYSTEM_PROMPT."""
    entry = _make_entry(must_not_include=["I am certain"])
    result = _check_no_llm(entry, k=8, verbose=False)
    # Should pass: these phrases should not be in the system prompt
    assert not any("guardrail leak" in f for f in result.failures)


# ── EvalResult dataclass ─────────────────────────────────────────────────────

def test_eval_result_dataclass():
    r = EvalResult(
        question_id="q001", mode="EXPLAIN", question="test?",
        passed=True, failures=[], retrieved_count=5, llm_used=False,
    )
    assert r.passed
    assert r.retrieved_count == 5
    assert not r.llm_used
