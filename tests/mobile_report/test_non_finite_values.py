from __future__ import annotations

import json

from tools.mobile_report.compiler import compile_report
from tools.mobile_report.evidence_loader import load_evidence_file

NOW = "2026-01-01T00:00:00+00:00"


def test_json_nan_and_infinity_are_rejected(tmp_path):
    path = tmp_path / "bad.json"
    path.write_text(json.dumps({"benchmarks": [{"name": "x", "value": float("nan")}]}), encoding="utf-8")
    result = load_evidence_file(path, list_key="benchmarks")
    assert result.ok is False
    assert "non_finite_value" in result.error

    path2 = tmp_path / "bad_inf.json"
    path2.write_text(json.dumps({"benchmarks": [{"name": "x", "value": float("inf")}]}), encoding="utf-8")
    result2 = load_evidence_file(path2, list_key="benchmarks")
    assert result2.ok is False
    assert "non_finite_value" in result2.error


def test_yaml_dot_nan_and_dot_inf_are_rejected(tmp_path):
    path = tmp_path / "bad.yaml"
    path.write_text("benchmarks:\n  - name: x\n    value: .nan\n", encoding="utf-8")
    result = load_evidence_file(path, list_key="benchmarks")
    assert result.ok is False
    assert "non_finite_value" in result.error

    path2 = tmp_path / "bad_inf.yaml"
    path2.write_text("benchmarks:\n  - name: x\n    value: -.inf\n", encoding="utf-8")
    result2 = load_evidence_file(path2, list_key="benchmarks")
    assert result2.ok is False
    assert "non_finite_value" in result2.error


def test_csv_nan_and_infinity_literals_are_rejected(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("name,value\nx,Infinity\n", encoding="utf-8")
    result = load_evidence_file(path, list_key="benchmarks")
    assert result.ok is False
    assert "non_finite_value" in result.error


def test_compiler_treats_non_finite_input_as_a_load_failure_not_a_crash(manifest_factory):
    manifest = manifest_factory({"performance_benchmark": ("json", '{"benchmarks": [{"name": "x", "value": NaN}]}')})

    report = compile_report(manifest, now=NOW)

    assert report["completeness"]["performance_benchmark"]["available"] is False
    assert "non_finite_value" in report["completeness"]["performance_benchmark"]["error"]
    assert report["performance_evidence"]["benchmarks"] == []
    assert report["status"] == "partial"


def test_overflowing_numeric_literal_is_nulled_not_left_as_inf(manifest_factory):
    manifest = manifest_factory({"performance_benchmark": ("json", '{"benchmarks": [{"name": "overflow", "value": 1e400}]}')})

    report = compile_report(manifest, now=NOW)

    assert report["completeness"]["performance_benchmark"]["available"] is True
    assert report["performance_evidence"]["benchmarks"][0]["value"] is None


def test_csv_row_numeric_string_nan_field_is_nulled_downstream(manifest_factory):
    csv_text = "name,metric,value,unit,baseline_value,regression_pct,status\nx,latency,not_a_number,ms,,,\n"
    manifest = manifest_factory({"performance_benchmark": ("csv", csv_text)})

    report = compile_report(manifest, now=NOW)
    assert report["completeness"]["performance_benchmark"]["available"] is True
    assert report["performance_evidence"]["benchmarks"][0]["value"] is None
