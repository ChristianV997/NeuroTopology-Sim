"""Deterministic tests for the null-calibration framework."""
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

from analysis.null_calibration.calibrate import calibrate, calibrate_payload
from analysis.null_calibration.json_util import NonFiniteJsonError, assert_finite_or_null, dumps_strict
from analysis.null_calibration.schema import NULL_MODELS

SCRIPT = ROOT / "scripts" / "run_null_calibration.py"
SERIES = [0.2, -0.1, 0.4, -0.3, 0.15, 0.05, -0.2, 0.1, 0.0, 0.25, -0.05, 0.3]


def _base(**kwargs):
    spec = {
        "null_model": "gaussian",
        "metric_family": "graph_beta1",
        "observations": list(SERIES),
        "observed_statistic": sum(SERIES) / len(SERIES),
        "n_replicates": 40,
        "seed": 7,
        "correction_method": "none",
        "n_tests": 1,
        "provenance": "tests/null_calibration",
        "synthetic_demo": True,
    }
    spec.update(kwargs)
    return spec


def test_flat_null() -> None:
    report = calibrate(_base(null_model="flat", n_replicates=20))
    assert report["status"] == "CALIBRATION_ONLY"
    assert report["scientific_pass"] is False
    assert report["k_value"] is None
    assert report["null_mean"] == 0.0
    assert report["null_variance"] == 0.0
    assert report["synthetic_demo"] is True


def test_gaussian_null() -> None:
    report = calibrate(_base(null_model="gaussian"))
    assert report["n_replicates"] == 40
    assert report["null_mean"] is not None
    assert report["permutation_p_value"] is not None
    assert report["formal_biological_evidence"] is False


def test_phase_shuffle() -> None:
    report = calibrate(_base(null_model="phase_shuffle", n_replicates=16))
    assert report["status"] == "CALIBRATION_ONLY"
    assert report["n_failed"] == 0
    assert report["parameters"]["null_model"] == "phase_shuffle"


def test_label_permutation() -> None:
    report = calibrate({
        "null_model": "label_permutation",
        "metric_family": "spatial_winding_q",
        "group_a": [0.1, 0.2, 0.15, 0.05],
        "group_b": [-0.1, 0.0, -0.05, 0.02],
        "n_replicates": 24,
        "seed": 3,
        "correction_method": "bonferroni",
        "n_tests": 4,
        "synthetic_demo": True,
        "provenance": "fixture",
    })
    assert report["metric_family"] == "spatial_winding_q"
    assert report["n_replicates"] == 24
    assert report["correction_method"] == "bonferroni"
    assert report["p_value_corrected"] is not None
    assert report["scientific_pass"] is False


def test_circular_shift() -> None:
    report = calibrate(_base(null_model="circular_shift", n_replicates=11))
    assert report["n_replicates"] == 11
    assert report["null_mean"] is not None


def test_deterministic_repeat() -> None:
    spec = _base(null_model="matched_variance", seed=99)
    first = calibrate(spec)
    second = calibrate(deepcopy(spec))
    assert first == second
    assert dumps_strict(first) == dumps_strict(second)


def test_zero_variance_input() -> None:
    report = calibrate(_base(null_model="matched_autocorrelation", observations=[1.0] * 12, observed_statistic=1.0))
    assert report["status"] in {"CALIBRATION_ONLY", "ERROR"}
    assert any("fell back" in w or "does not preserve" in w for w in report["warnings"]) or report["errors"]


def test_non_finite_input() -> None:
    report = calibrate(_base(observations=[0.1, float("nan"), 0.2]))
    assert report["status"] == "ERROR"
    assert report["ok"] is False
    assert report["scientific_pass"] is False


def test_failed_replicate() -> None:
    report = calibrate(_base(null_model="phase_shuffle", observations=[0.1, 0.2], n_replicates=5))
    assert report["n_failed"] == 5 or report["status"] == "ERROR"
    if report["status"] != "ERROR":
        assert report["failed_replicates"]


def test_insufficient_replicates() -> None:
    report = calibrate(_base(n_replicates=1, null_model="flat"))
    assert report["status"] == "INSUFFICIENT"
    assert any("recommended minimum" in w or "hard minimum" in w for w in report["warnings"])
    assert report["scientific_pass"] is False


def test_multiple_comparison_correction() -> None:
    report = calibrate(_base(correction_method="holm", n_tests=10, null_model="flat"))
    assert report["correction_method"] == "holm"
    assert report["n_tests"] == 10
    raw = report["permutation_p_value"]
    corrected = report["p_value_corrected"]
    assert raw is not None and corrected is not None
    assert corrected >= raw - 1e-12
    unknown = calibrate(_base(correction_method="bonferroni", n_tests=None, null_model="flat"))
    assert unknown["multiplicity_status"] == "unknown"
    assert unknown["p_value_corrected"] is None


def test_json_finite_null_compliance() -> None:
    report = calibrate(_base(null_model="block_shuffle", provenance=None))
    assert report["k_value"] is None
    assert report["falsification_verdict"] is None
    dumps_strict(report)
    with pytest.raises(NonFiniteJsonError):
        assert_finite_or_null({"x": math.inf})
    with pytest.raises(ValueError):
        calibrate_payload({"observations": [math.nan], "null_model": "flat", "n_replicates": 2, "seed": 1})


def test_never_emits_scientific_pass() -> None:
    for model in NULL_MODELS:
        if model == "label_permutation":
            spec = {
                "null_model": model,
                "metric_family": "scalar_chirality",
                "group_a": [1.0, 2.0, 3.0, 0.5],
                "group_b": [0.0, 0.2, -0.1, 0.1],
                "n_replicates": 8,
                "seed": 1,
                "synthetic_demo": True,
            }
        else:
            spec = _base(null_model=model, n_replicates=8, seed=1)
        report = calibrate(spec)
        assert report["scientific_pass"] is False
        assert report["k_value"] is None
        assert report.get("falsification_verdict") is None


def test_cli_roundtrip(tmp_path: Path) -> None:
    import runpy
    spec_path = tmp_path / "spec.json"
    out_path = tmp_path / "calibration.json"
    spec_path.write_text(json.dumps(_base(null_model="circular_shift")), encoding="utf-8")
    old = sys.argv
    try:
        sys.argv = ["run_null_calibration.py", "--input", str(spec_path), "--output", str(out_path), "--quiet"]
        try:
            runpy.run_path(str(SCRIPT), run_name="__main__")
        except SystemExit as exc:
            assert exc.code in {0, 1}
    finally:
        sys.argv = old
    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["scientific_pass"] is False
    assert payload["synthetic_demo"] is True
