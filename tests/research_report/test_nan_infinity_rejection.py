from __future__ import annotations

import json

from tools.research_report.compiler import compile_report
from tools.research_report.json_safe import load_json_strict

NOW = "2026-01-01T00:00:00+00:00"


def test_loader_rejects_literal_nan_and_infinity(tmp_path):
    path = tmp_path / "bad.json"
    # json.dumps with default allow_nan=True writes the non-standard but
    # Python-parseable literals NaN / Infinity -- exactly what a careless
    # producer might emit.
    path.write_text(json.dumps({"benchmarks": [{"name": "x", "value": float("nan")}]}), encoding="utf-8")

    result = load_json_strict(path)
    assert result.ok is False
    assert "non_finite_value" in result.error

    path2 = tmp_path / "bad_inf.json"
    path2.write_text(json.dumps({"benchmarks": [{"name": "x", "value": float("inf")}]}), encoding="utf-8")
    result2 = load_json_strict(path2)
    assert result2.ok is False
    assert "non_finite_value" in result2.error


def test_compiler_treats_nan_infinity_input_as_a_load_failure_not_a_crash(manifest_factory):
    manifest = manifest_factory({"performance_benchmark": json.dumps({"benchmarks": [{"name": "x", "value": float("nan")}]})})

    report = compile_report(manifest, now=NOW)

    assert report["completeness"]["performance_benchmark"]["available"] is False
    assert "non_finite_value" in report["completeness"]["performance_benchmark"]["error"]
    assert report["performance_evidence"]["benchmarks"] == []
    assert report["status"] == "partial"


def test_overflowing_numeric_literal_is_nulled_not_left_as_inf(manifest_factory):
    # "1e400" is valid JSON syntax that overflows to float('inf') in Python,
    # so it slips past parse_constant and must be caught downstream.
    manifest = manifest_factory({"performance_benchmark": '{"benchmarks": [{"name": "overflow", "value": 1e400}]}'})

    report = compile_report(manifest, now=NOW)

    assert report["completeness"]["performance_benchmark"]["available"] is True
    assert report["performance_evidence"]["benchmarks"][0]["value"] is None
