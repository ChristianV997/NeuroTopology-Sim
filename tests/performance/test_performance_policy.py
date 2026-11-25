"""Tests for the additive performance-regression policy evaluator.

Assert deterministic policy decisions on benchmark JSON records: valid vs invalid
comparisons, correctness gating, missing-metric handling (None, never zero),
regression thresholds, hardware-advisory behavior, synthetic labeling, and
JSON-safety. No absolute wall-clock thresholds are asserted. Records here are
synthetic performance scaffolding only, never scientific evidence.
"""
from __future__ import annotations

import importlib.util
import json
import math
import sys
from pathlib import Path

import pytest

from tools.streaming.performance_policy import (
    Confidence,
    PolicyThresholds,
    Verdict,
    compare_records,
    dumps,
    evaluate_against_budget,
    json_safe,
)

# Load the CLI script by path (scripts/ is not a package).
_SPEC = importlib.util.spec_from_file_location(
    "evaluate_performance_budget",
    Path(__file__).resolve().parents[2] / "scripts" / "evaluate_performance_budget.py",
)
cli = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = cli
_SPEC.loader.exec_module(cli)


def _baseline():
    return dict(
        label="synthetic_full", backend="numpy",
        input_dims={"samples": 200000, "channels": 32}, chunk_size=None,
        repetitions=5, wall_best_s=0.050, wall_mean_s=0.052,
        tracemalloc_peak_bytes=51_200_000, peak_rss_bytes=212_000_000,
        checksum=123.456, hardware={"platform": "linux", "cpu": "x86_64"},
        synthetic=True,
    )


def _candidate(**overrides):
    cand = _baseline()
    cand["label"] = "synthetic_bounded"
    cand["chunk_size"] = 16384
    cand["tracemalloc_peak_bytes"] = 8_400_000
    cand["wall_best_s"] = 0.047
    cand.update(overrides)
    return cand


# --------------------------------------------------------------------------- #
# Valid comparison
# --------------------------------------------------------------------------- #
def test_valid_comparison_passes():
    report = compare_records(_baseline(), _candidate())
    assert report.verdict == Verdict.PASS
    assert report.valid_comparison is True
    assert report.correctness_ok is True
    assert report.tracemalloc_ratio < 1.0
    assert report.confidence.value in {"high", "medium"}
    assert report.evidence_class == "performance_only"


# --------------------------------------------------------------------------- #
# Shape / backend / hardware
# --------------------------------------------------------------------------- #
def test_shape_mismatch_is_invalid_not_regression():
    report = compare_records(_baseline(), _candidate(input_dims={"samples": 100, "channels": 8}))
    assert report.verdict == Verdict.INVALID_COMPARISON
    assert "input_shape_mismatch" in report.invalid_reasons
    assert report.input_shape["match"] is False


def test_backend_mismatch_is_invalid_by_default():
    report = compare_records(_baseline(), _candidate(backend="numba"))
    assert report.verdict == Verdict.INVALID_COMPARISON
    assert "backend_mismatch" in report.invalid_reasons


def test_backend_mismatch_allowed_when_configured():
    thr = PolicyThresholds(require_same_backend=False)
    report = compare_records(_baseline(), _candidate(backend="numba"), thr)
    assert "backend_mismatch" not in report.invalid_reasons
    assert report.backend["match"] is False


def test_hardware_mismatch_makes_runtime_advisory_not_regression():
    # Candidate is 10x slower but on different hardware -> not a regression verdict.
    report = compare_records(
        _baseline(),
        _candidate(hardware={"platform": "darwin", "cpu": "arm64"}, wall_best_s=0.5),
    )
    assert report.runtime_regression is True          # reported...
    assert report.verdict == Verdict.PASS             # ...but advisory, not authoritative
    assert report.confidence == Confidence.MEDIUM
    assert report.measurement_quality["runtime_rss_authoritative"] is False


def test_require_same_hardware_makes_mismatch_invalid():
    thr = PolicyThresholds(require_same_hardware=True)
    report = compare_records(_baseline(), _candidate(hardware={"platform": "darwin"}), thr)
    assert report.verdict == Verdict.INVALID_COMPARISON
    assert "hardware_mismatch" in report.invalid_reasons


# --------------------------------------------------------------------------- #
# Correctness gating
# --------------------------------------------------------------------------- #
def test_checksum_mismatch_is_correctness_failure():
    report = compare_records(_baseline(), _candidate(checksum=999.0))
    assert report.verdict == Verdict.CORRECTNESS_FAILURE
    assert report.correctness_ok is False
    assert report.checksum_rel_err > 0


def test_missing_checksum_is_inconclusive():
    base = _baseline(); base.pop("checksum")
    report = compare_records(base, _candidate())
    assert report.verdict == Verdict.INCONCLUSIVE
    assert report.correctness_ok is None


def test_checksum_within_tolerance_passes():
    report = compare_records(_baseline(), _candidate(checksum=123.456 + 1e-12))
    assert report.correctness_ok is True


# --------------------------------------------------------------------------- #
# Missing metrics -> None, never zero
# --------------------------------------------------------------------------- #
def test_missing_rss_yields_none_ratio_not_zero():
    report = compare_records(_baseline(), _candidate(peak_rss_bytes=None))
    assert report.peak_rss_ratio is None
    assert report.peak_rss_regression is None
    assert report.verdict == Verdict.PASS


def test_missing_tracemalloc_yields_none_ratio():
    report = compare_records(_baseline(), _candidate(tracemalloc_peak_bytes=None))
    assert report.tracemalloc_ratio is None
    assert report.tracemalloc_regression is None


def test_baseline_missing_rss_only_still_none():
    base = _baseline(); base["peak_rss_bytes"] = None
    report = compare_records(base, _candidate())
    assert report.peak_rss_ratio is None


# --------------------------------------------------------------------------- #
# Regression thresholds
# --------------------------------------------------------------------------- #
def test_tracemalloc_regression_is_authoritative():
    report = compare_records(_baseline(), _candidate(tracemalloc_peak_bytes=60_000_000))
    assert report.tracemalloc_regression is True
    assert report.verdict == Verdict.REGRESSION


def test_regression_threshold_is_configurable():
    cand = _candidate(tracemalloc_peak_bytes=int(51_200_000 * 1.08))  # +8%
    strict = PolicyThresholds(max_tracemalloc_regression_ratio=1.05)
    lenient = PolicyThresholds(max_tracemalloc_regression_ratio=1.20)
    assert compare_records(_baseline(), cand, strict).verdict == Verdict.REGRESSION
    assert compare_records(_baseline(), cand, lenient).verdict == Verdict.PASS


def test_same_hardware_runtime_regression_is_authoritative():
    # Same hardware + big runtime ratio -> regression.
    report = compare_records(_baseline(), _candidate(wall_best_s=0.10))  # 2x baseline
    assert report.runtime_regression is True
    assert report.verdict == Verdict.REGRESSION


# --------------------------------------------------------------------------- #
# Confidence / determinism / synthetic / JSON
# --------------------------------------------------------------------------- #
def test_low_repetitions_lowers_confidence():
    report = compare_records(_baseline(), _candidate(repetitions=1))
    assert report.confidence.value == "low"
    assert report.measurement_quality["low_repetitions"] is True


def test_deterministic_output():
    a = compare_records(_baseline(), _candidate()).to_dict()
    b = compare_records(_baseline(), _candidate()).to_dict()
    assert a == b


def test_synthetic_labeling():
    report = compare_records(_baseline(), _candidate())
    assert report.synthetic is True
    assert report.evidence_class == "performance_only"
    # If either record is not marked synthetic, the flag is False.
    non_synth = _candidate(synthetic=False, label="real_run")
    assert compare_records(_baseline(), non_synth).synthetic is False


def test_report_json_is_finite_and_valid():
    report = compare_records(_baseline(), _candidate(peak_rss_bytes=None))
    text = dumps(report.to_dict())
    assert "NaN" not in text and "Infinity" not in text
    parsed = json.loads(text)

    def _finite(o):
        if isinstance(o, float):
            assert math.isfinite(o)
        elif isinstance(o, dict):
            for v in o.values():
                _finite(v)
        elif isinstance(o, list):
            for v in o:
                _finite(v)

    _finite(parsed)


def test_json_safe_replaces_non_finite():
    assert json_safe(float("nan")) is None
    assert json_safe(float("inf")) is None
    assert json_safe({"a": [float("-inf"), 1.0]}) == {"a": [None, 1.0]}


# --------------------------------------------------------------------------- #
# Budget mode
# --------------------------------------------------------------------------- #
def test_budget_within_and_over():
    rec = _candidate()
    ok = evaluate_against_budget(rec, peak_rss_budget_bytes=300_000_000,
                                 tracemalloc_budget_bytes=16_000_000)
    assert ok["within_budget"] is True
    over = evaluate_against_budget(rec, tracemalloc_budget_bytes=1_000_000)
    assert over["within_budget"] is False


def test_budget_missing_metric_is_none_not_pass():
    rec = _candidate(peak_rss_bytes=None)
    result = evaluate_against_budget(rec, peak_rss_budget_bytes=300_000_000)
    assert result["checks"]["peak_rss_within_budget"] is None
    assert result["within_budget"] is None  # nothing evaluable -> unknown


def test_budget_no_budgets_is_unknown():
    result = evaluate_against_budget(_candidate())
    assert result["within_budget"] is None


# --------------------------------------------------------------------------- #
# CLI exit codes
# --------------------------------------------------------------------------- #
def _write(tmp_path, name, record):
    p = tmp_path / name
    p.write_text(json.dumps(record), encoding="utf-8")
    return str(p)


def test_cli_compare_exit_codes(tmp_path, capsys):
    base = _write(tmp_path, "base.json", _baseline())
    cand = _write(tmp_path, "cand.json", _candidate())
    assert cli.main(["compare", "--baseline", base, "--candidate", cand]) == 0
    capsys.readouterr()
    reg = _write(tmp_path, "reg.json", _candidate(tracemalloc_peak_bytes=60_000_000))
    assert cli.main(["compare", "--baseline", base, "--candidate", reg]) == 2
    capsys.readouterr()
    badck = _write(tmp_path, "badck.json", _candidate(checksum=999.0))
    assert cli.main(["compare", "--baseline", base, "--candidate", badck]) == 3
    capsys.readouterr()
    badshape = _write(tmp_path, "shape.json", _candidate(input_dims={"samples": 1, "channels": 1}))
    assert cli.main(["compare", "--baseline", base, "--candidate", badshape]) == 4
    capsys.readouterr()


def test_cli_compare_json_is_finite(tmp_path, capsys):
    base = _write(tmp_path, "base.json", _baseline())
    cand = _write(tmp_path, "cand.json", _candidate(peak_rss_bytes=None))
    cli.main(["compare", "--baseline", base, "--candidate", cand])
    out = capsys.readouterr().out
    assert "NaN" not in out and "Infinity" not in out
    json.loads(out)


def test_cli_budget_exit_codes(tmp_path, capsys):
    rec = _write(tmp_path, "rec.json", _candidate())
    assert cli.main(["budget", "--record", rec, "--tracemalloc-budget-mb", "16"]) == 0
    capsys.readouterr()
    assert cli.main(["budget", "--record", rec, "--tracemalloc-budget-mb", "1"]) == 2
    capsys.readouterr()
    assert cli.main(["budget", "--record", rec]) == 5  # no budgets -> unknown
    capsys.readouterr()
