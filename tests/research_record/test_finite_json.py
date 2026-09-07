"""Rule 10: NaN and Infinity must be rejected -- across JSON, YAML, and CSV
inputs, and against the compiler's own output serialization."""
from __future__ import annotations

import json

from tools.research_record.compiler import compile_record
from tools.research_record.evidence_loader import load_evidence_file

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


def test_csv_infinity_literal_is_rejected(tmp_path):
    path = tmp_path / "bad.csv"
    path.write_text("name,value\nx,Infinity\n", encoding="utf-8")
    result = load_evidence_file(path, list_key="benchmarks")
    assert result.ok is False
    assert "non_finite_value" in result.error


def test_compiler_treats_non_finite_input_as_a_load_failure_not_a_crash(manifest_factory):
    manifest = manifest_factory({"performance_benchmark": ("json", '{"benchmarks": [{"name": "x", "value": NaN}]}')})

    record = compile_record(manifest, now=NOW)

    assert record["completeness"]["performance_benchmark"]["available"] is False
    assert "non_finite_value" in record["completeness"]["performance_benchmark"]["error"]
    assert record["performance_evidence"]["benchmarks"] == []
    assert record["status"] == "partial"


def test_overflowing_numeric_literal_is_nulled_not_left_as_inf(manifest_factory):
    manifest = manifest_factory({"performance_benchmark": ("json", '{"benchmarks": [{"name": "overflow", "value": 1e400}]}')})

    record = compile_record(manifest, now=NOW)
    assert record["performance_evidence"]["benchmarks"][0]["value"] is None


def test_full_record_json_serializes_with_allow_nan_false(manifest_factory):
    manifest = manifest_factory({})
    record = compile_record(manifest, now=NOW)
    # Would raise ValueError if any float in the record were non-finite.
    text = json.dumps(record, indent=2, sort_keys=True, allow_nan=False)
    assert "NaN" not in text
    assert "Infinity" not in text
