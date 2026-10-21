"""Fail-closed promotion rules against the fixture matrix."""

from __future__ import annotations

from pathlib import Path

import pytest

from tools.evidence_promotion_gate.adapters import load_case_dir
from tools.evidence_promotion_gate.evaluator import evaluate_case, evaluate_path

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _result(name: str):
    return evaluate_case(load_case_dir(FIXTURES / name))


@pytest.mark.parametrize(
    "name,decision",
    [
        ("synthetic_run", "HOLD_SYNTHETIC_ONLY"),
        ("performance_only", "HOLD_SYNTHETIC_ONLY"),
        ("surrogate_null", "HOLD_SYNTHETIC_ONLY"),
        ("proxy_k", "HOLD_PROXY_ONLY"),
        ("literature_hypothesis", "HOLD_LITERATURE_HYPOTHESIS"),
        ("literature_review_required", "HOLD_LITERATURE_HYPOTHESIS"),
        ("incomplete_provenance", "HOLD_INCOMPLETE_PROVENANCE"),
        ("unknown_n_tests", "HOLD_INCONCLUSIVE"),
        ("missing_controls", "HOLD_INCONCLUSIVE"),
        ("downstream_pass_rag", "BLOCK_PROMOTION"),
        ("downstream_empirical_cc", "BLOCK_PROMOTION"),
        ("airtable_empirical_pass", "BLOCK_PROMOTION"),
        ("engineering_ok", "ADMISSIBLE_FOR_ENGINEERING_REPORT"),
        ("descriptive_review_ok", "ADMISSIBLE_FOR_DESCRIPTIVE_REVIEW"),
        ("formal_declared_still_refused", "HOLD_INCOMPLETE_PROVENANCE"),
    ],
)
def test_fixture_matrix_decisions(name: str, decision: str):
    result = _result(name)
    assert result.promotion_decision == decision
    assert result.scientific_pass is False
    assert result.to_dict()["scientific_pass"] is False
    assert result.allowed_evidence_class.lower() != "empirical"
    assert result.network_access_performed is False


def test_synthetic_cannot_become_empirical():
    for name in ("synthetic_run", "performance_only", "surrogate_null"):
        result = _result(name)
        assert result.synthetic_demo is True
        assert result.promotion_decision in {"HOLD_SYNTHETIC_ONLY", "BLOCK_PROMOTION"}
        assert "SYNTHETIC_NOT_EMPIRICAL" in result.reason_codes or "PERFORMANCE_ONLY_NOT_EMPIRICAL" in result.reason_codes


def test_proxy_keeps_formal_bayes_factor_null():
    result = _result("proxy_k")
    assert result.promotion_decision == "HOLD_PROXY_ONLY"
    assert result.formal_bayes_factor is None
    assert "PROXY_K_NOT_EMPIRICAL" in result.reason_codes
    assert result.allowed_evidence_class == "proxy_inference"


def test_literature_never_empirical():
    for name in ("literature_hypothesis", "literature_review_required"):
        result = _result(name)
        assert result.promotion_decision == "HOLD_LITERATURE_HYPOTHESIS"
        assert result.allowed_evidence_class == "hypothesis"
        assert "LITERATURE_HYPOTHESIS_NOT_EMPIRICAL" in result.reason_codes


def test_unknown_n_tests_never_treated_as_one():
    result = _result("unknown_n_tests")
    assert result.promotion_decision == "HOLD_INCONCLUSIVE"
    assert "UNKNOWN_N_TESTS" in result.reason_codes


def test_downstream_pass_and_empirical_are_blocked():
    rag = _result("downstream_pass_rag")
    assert "DOWNSTREAM_UNSAFE_PASS" in rag.reason_codes
    cc = _result("downstream_empirical_cc")
    assert "DOWNSTREAM_UNSAFE_EMPIRICAL" in cc.reason_codes
    card = _result("airtable_empirical_pass")
    assert card.promotion_decision == "BLOCK_PROMOTION"


def test_formal_k_100_is_not_pass_and_still_refused():
    result = _result("formal_declared_still_refused")
    assert result.scientific_pass is False
    assert result.promotion_decision not in {
        "ADMISSIBLE_FOR_DESCRIPTIVE_REVIEW",
        "ADMISSIBLE_FOR_ENGINEERING_REPORT",
    }
    assert "K_EQUALS_100_NOT_PASS" in result.reason_codes or result.declared_formal_bayes_factor == 100.0
    assert result.to_dict().get("scientific_pass") is False


def test_evaluate_claim_is_invoked_for_run_records():
    result = _result("synthetic_run")
    assert result.claim_gate is not None
    assert result.claim_gate.get("scientific_pass") is False
    assert result.claim_gate.get("schema_version") == "NeuroTopology.ResearchClaimGate.v1"


def test_directory_evaluation_covers_all_fixtures():
    results = evaluate_path(FIXTURES)
    ids = {item.case_id for item in results}
    expected = {path.name for path in FIXTURES.iterdir() if path.is_dir()}
    assert ids == expected
    assert all(item.scientific_pass is False for item in results)
