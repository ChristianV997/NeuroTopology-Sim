"""Deterministic tests for the local research-claim auditor."""
from __future__ import annotations

import json
import math
import sys
from copy import deepcopy
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shared.research_claims.audit import (
    VERDICT_DOWNGRADED,
    VERDICT_FAIL,
    VERDICT_PASS,
    audit_claims,
    audit_claims_payload,
    audit_one,
)
from shared.research_claims.catalog import (
    CONSCIOUSNESS_BAD,
    ENGINEERING_CLAIM,
    FORMAL_COMPLETE,
    GRAPH_SPATIAL_BAD,
    MISSING_PROVENANCE,
    PROXY_BAYES_BAD,
    PROXY_BAYES_OK,
    QUANTUM_BAD,
    SYNTHETIC_CLAIM,
)
from shared.research_claims.json_util import NonFiniteJsonError, assert_finite_or_null, dumps_strict
from shared.research_claims.schema import CLAIM_CATEGORIES

SCRIPTS = ROOT / "scripts" / "validate_research_claims.py"


def _codes(record: dict) -> set[str]:
    return {item["code"] for item in record["violations"]}


def test_valid_engineering_claim() -> None:
    record = audit_one(ENGINEERING_CLAIM)
    assert record["verdict"] == VERDICT_PASS
    assert record["original_text"] == ENGINEERING_CLAIM["text"]
    assert record["text_rewritten"] is False
    assert record["results_rewritten"] is False
    assert record["violations"] == []


def test_synthetic_result() -> None:
    ok = audit_one(SYNTHETIC_CLAIM)
    assert ok["verdict"] == VERDICT_PASS
    bad = deepcopy(SYNTHETIC_CLAIM)
    bad["claim_id"] = "SYN-BAD-001"
    bad["claim_category"] = "empirical_observation"
    bad["evidence_class"] = "empirical_observation"
    bad["text"] = "Seeded synthetic winding confirms biology and is an empirical confirmation of the cortical mechanism."
    audited = audit_one(bad)
    assert audited["verdict"] in {VERDICT_FAIL, VERDICT_DOWNGRADED}
    assert "R1_SYNTHETIC_NOT_BIOLOGY" in _codes(audited)
    assert audited["original_text"] == bad["text"]


def test_proxy_bayesian_claim_labeled() -> None:
    record = audit_one(PROXY_BAYES_OK)
    assert record["verdict"] == VERDICT_PASS
    assert record["original_claim"]["proxy_formal_status"] == "proxy"


def test_proxy_bayesian_claim() -> None:
    record = audit_one(PROXY_BAYES_BAD)
    assert record["verdict"] in {VERDICT_FAIL, VERDICT_DOWNGRADED}
    assert "R2_PROXY_K_NOT_FORMAL" in _codes(record)
    assert record["recommended_category"] == "proxy_inference"
    assert record["original_text"] == PROXY_BAYES_BAD["text"]


def test_unsupported_consciousness_claim() -> None:
    record = audit_one(CONSCIOUSNESS_BAD)
    assert record["verdict"] in {VERDICT_FAIL, VERDICT_DOWNGRADED}
    assert "R3_BETA1_NOT_CONSCIOUSNESS" in _codes(record)
    assert record["text_rewritten"] is False


def test_unsupported_biological_quantum_claim() -> None:
    record = audit_one(QUANTUM_BAD)
    assert record["verdict"] in {VERDICT_FAIL, VERDICT_DOWNGRADED}
    codes = _codes(record)
    assert "R6_SIM_NOT_BIO_QUANTUM" in codes
    assert "R1_SYNTHETIC_NOT_BIOLOGY" in codes or "CATEGORY_EVIDENCE_MISMATCH" in codes


def test_missing_provenance() -> None:
    record = audit_one(MISSING_PROVENANCE)
    assert record["verdict"] in {VERDICT_FAIL, VERDICT_DOWNGRADED}
    assert "R7_MISSING_PROVENANCE" in _codes(record)
    assert record["recommended_category"] == "speculation"


def test_formal_evidence_complete_metadata() -> None:
    record = audit_one(FORMAL_COMPLETE)
    assert record["verdict"] == VERDICT_PASS, record["violations"]
    original = record["original_claim"]
    for field in (
        "claim_id", "text", "claim_category", "evidence_class", "provenance_reference",
        "data_origin", "empirical_synthetic_status", "proxy_formal_status", "test_reference",
        "required_controls", "falsifiability_condition", "allowed_language",
        "prohibited_language", "reviewer_state", "last_reviewed",
    ):
        assert original[field] == FORMAL_COMPLETE[field]


def test_graph_spatial_metric_confusion() -> None:
    record = audit_one(GRAPH_SPATIAL_BAD)
    assert record["verdict"] in {VERDICT_FAIL, VERDICT_DOWNGRADED}
    assert "R4_GRAPH_BETA1_NOT_SPATIAL" in _codes(record)


def test_deterministic_validation() -> None:
    payload = {"claims": [ENGINEERING_CLAIM, PROXY_BAYES_BAD, MISSING_PROVENANCE]}
    first = audit_claims_payload(payload)
    second = audit_claims_payload(payload)
    assert first == second
    encoded = dumps_strict(first)
    assert dumps_strict(second) == encoded
    assert dumps_strict(json.loads(encoded)) == encoded


def test_json_finite_null_compliance() -> None:
    report = audit_claims([ENGINEERING_CLAIM, MISSING_PROVENANCE])
    assert report["audits"][1]["original_claim"]["provenance_reference"] is None
    assert report["audits"][1]["original_claim"]["data_origin"] is None
    dumps_strict(report)
    with pytest.raises(NonFiniteJsonError):
        assert_finite_or_null({"k": math.nan})
    with pytest.raises(NonFiniteJsonError):
        assert_finite_or_null({"k": math.inf})
    with pytest.raises(ValueError):
        audit_claims_payload({"claims": [{"claim_id": "X", "k": math.nan}]})


def test_closed_classification_set() -> None:
    assert CLAIM_CATEGORIES == (
        "engineering_fact", "benchmark_result", "synthetic_demonstration",
        "empirical_observation", "proxy_inference", "formal_statistical_evidence",
        "hypothesis", "speculation", "unsupported_claim", "historical_context",
    )


def test_cli_roundtrip(tmp_path: Path) -> None:
    import runpy
    claims_path = tmp_path / "claims.json"
    out_path = tmp_path / "claim_audit.json"
    claims_path.write_text(json.dumps({"claims": [ENGINEERING_CLAIM, PROXY_BAYES_BAD]}, indent=2), encoding="utf-8")
    old = sys.argv
    try:
        sys.argv = ["validate_research_claims.py", "--input", str(claims_path), "--output", str(out_path), "--quiet"]
        try:
            runpy.run_path(str(SCRIPTS), run_name="__main__")
        except SystemExit as exc:
            assert exc.code == 1
    finally:
        sys.argv = old
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["text_rewritten"] is False
    assert payload["results_rewritten"] is False
    assert payload["counts"]["pass"] == 1
    assert payload["counts"]["downgraded"] + payload["counts"]["fail"] == 1


def test_validator_does_not_rewrite_source(tmp_path: Path) -> None:
    import runpy
    source = deepcopy(CONSCIOUSNESS_BAD)
    claims_path = tmp_path / "claims.json"
    out_path = tmp_path / "claim_audit.json"
    raw = json.dumps({"claims": [source]}, indent=2, sort_keys=True)
    claims_path.write_text(raw, encoding="utf-8")
    old = sys.argv
    try:
        sys.argv = ["validate_research_claims.py", "--input", str(claims_path), "--output", str(out_path), "--quiet"]
        try:
            runpy.run_path(str(SCRIPTS), run_name="__main__")
        except SystemExit:
            pass
    finally:
        sys.argv = old
    assert claims_path.read_text(encoding="utf-8") == raw
    audit = json.loads(out_path.read_text(encoding="utf-8"))
    assert audit["audits"][0]["original_text"] == source["text"]
    assert audit["audits"][0]["text_rewritten"] is False
