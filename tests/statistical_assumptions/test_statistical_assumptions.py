"""Tests for the read-only statistical-assumption auditor."""
from __future__ import annotations

import json
import socket
import sys
from copy import deepcopy
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.statistical_assumptions.audit import audit_payload
from analysis.statistical_assumptions.json_util import dumps_strict

SCRIPT = ROOT / "scripts" / "audit_statistical_assumptions.py"


def _pairs(n: int = 10, scale: float = 1.0) -> list[dict]:
    return [{"pair_id": f"s{i:02d}", "condition_a": scale * (0.2 + 0.05 * i), "condition_b": scale * (0.05 * (i % 3))} for i in range(n)]


def _clean_cohort(**kwargs) -> dict:
    spec = {"pairs": _pairs(10), "n_pairs_declared": 10, "effective_sample_size": 10, "n_tests_declared": 1, "n_tests_observed": 1, "correction_method": "none", "metric_family": "graph_beta1", "synthetic": False, "provenance": "fixture/cohort"}
    spec.update(kwargs)
    return spec


def _clean_null(**kwargs) -> dict:
    spec = {"null_model": "phase_shuffle", "n_replicates": 200, "effective_sample_size": 10, "synthetic_demo": False, "seed": 7}
    spec.update(kwargs)
    return spec


def _clean_prereg(**kwargs) -> dict:
    spec = {"estimand": "paired_mean_difference", "n_tests": 1, "correction_method": "none", "stopping_rule": "fixed_n_equals_10", "metric_family": "graph_beta1"}
    spec.update(kwargs)
    return spec


def _spec(cohort=None, null=None, prereg=None) -> dict:
    return {"cohort_statistics": cohort if cohort is not None else _clean_cohort(), "null_calibration": null if null is not None else _clean_null(), "preregistration": prereg if prereg is not None else _clean_prereg()}


def _codes(report: dict) -> set[str]:
    return {item["code"] for item in report["findings"]}


def test_adequate_paired_sample() -> None:
    report = audit_payload(_spec())
    assert report["status"] == "AUDIT_CLEAN"
    assert report["scientific_pass"] is False
    assert report["formal_bayes_factor"] is None
    assert report["evidence_class"] == "statistical_assumption_audit"


def test_insufficient_pairs() -> None:
    report = audit_payload(_spec(cohort=_clean_cohort(pairs=_pairs(3), n_pairs_declared=3, effective_sample_size=3)))
    assert report["status"] == "AUDIT_INSUFFICIENT_POWER"
    assert "INSUFFICIENT_PAIRS" in _codes(report)


def test_missing_multiplicity_correction() -> None:
    report = audit_payload(_spec(cohort=_clean_cohort(n_tests_declared=4, n_tests_observed=4, correction_method="none")))
    assert report["status"] == "AUDIT_MULTIPLICITY_UNRESOLVED"
    assert "MULTIPLICITY_UNRESOLVED" in _codes(report)


def test_missing_null_model() -> None:
    report = audit_payload(_spec(null={"n_replicates": 200, "effective_sample_size": 10}))
    assert report["status"] == "AUDIT_NULL_MODEL_UNRESOLVED"
    assert "NULL_MODEL_MISSING" in _codes(report)


def test_insufficient_null_replicates() -> None:
    report = audit_payload(_spec(null=_clean_null(n_replicates=20)))
    assert "NULL_REPLICATES_LOW" in _codes(report)


def test_zero_variance() -> None:
    pairs = [{"pair_id": f"s{i}", "difference": 0.4} for i in range(10)]
    report = audit_payload(_spec(cohort=_clean_cohort(pairs=pairs)))
    assert "ZERO_VARIANCE" in _codes(report)
    assert report["status"] == "AUDIT_SCIENTIFIC_REVIEW_REQUIRED"


def test_all_zero_differences() -> None:
    pairs = [{"pair_id": f"s{i}", "difference": 0.0} for i in range(10)]
    report = audit_payload(_spec(cohort=_clean_cohort(pairs=pairs)))
    assert "ALL_ZERO_DIFFERENCES" in _codes(report)


def test_duplicate_pairs() -> None:
    pairs = _pairs(10)
    pairs[3]["pair_id"] = pairs[0]["pair_id"]
    report = audit_payload(_spec(cohort=_clean_cohort(pairs=pairs)))
    assert report["status"] == "AUDIT_INVALID_INPUT"
    assert "DUPLICATE_PAIRS" in _codes(report)


def test_synthetic_input() -> None:
    report = audit_payload(_spec(cohort=_clean_cohort(synthetic=True), null=_clean_null(synthetic_demo=True)))
    assert report["status"] == "AUDIT_SYNTHETIC_ONLY"
    assert report["scientific_pass"] is False


def test_graph_spatial_metric_conflation() -> None:
    report = audit_payload(_spec(cohort=_clean_cohort(conflates_graph_and_spatial=True)))
    assert "GRAPH_SPATIAL_CONFLATION" in _codes(report)
    assert report["status"] == "AUDIT_SCIENTIFIC_REVIEW_REQUIRED"


def test_deterministic_output() -> None:
    spec = _spec()
    first = audit_payload(spec)
    second = audit_payload(deepcopy(spec))
    assert first == second
    assert dumps_strict(first) == dumps_strict(second)


def test_no_network_behavior() -> None:
    original = socket.socket

    def blocked(*args, **kwargs):
        raise AssertionError("network was used")

    socket.socket = blocked
    try:
        report = audit_payload(_spec())
        assert report["scientific_pass"] is False
    finally:
        socket.socket = original


def test_cli_and_never_pass(tmp_path: Path) -> None:
    import runpy
    spec_path = tmp_path / "spec.json"
    out_path = tmp_path / "assumption_audit.json"
    spec_path.write_text(json.dumps(_spec()), encoding="utf-8")
    old = sys.argv
    try:
        sys.argv = ["audit_statistical_assumptions.py", "--input", str(spec_path), "--output", str(out_path), "--quiet"]
        try:
            runpy.run_path(str(SCRIPT), run_name="__main__")
        except SystemExit as exc:
            assert exc.code in {0, 1}
    finally:
        sys.argv = old
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["scientific_pass"] is False
    assert payload["formal_bayes_factor"] is None
    assert payload["evidence_class"] == "statistical_assumption_audit"
