"""Fail-closed invariants for hypothesis pipeline false-certainty gaps.

Proves:
  - run_hypothesis never fabricates Q/Qabs/f_dress via rng.normal
  - synthetic / seed-imputed runs stamp watermarks and scientific_pass=False
  - empirical-mode thresholds cannot PASS as empirical without empirical metrics
  - YAML run() RunRecord carries evidence_class / metrics_are_empirical / run_mode
  - watermark scanner rejects mock-as-empirical hypothesis artifacts
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from governance.spec import DataSpec, HypothesisSpec, PassFail
from pipelines.hypothesis import run, run_hypothesis
from tools.check_hypothesis_artifact_watermarks import main as watermark_scan_main
from tools.check_hypothesis_artifact_watermarks import scan_json


_REPO = Path(__file__).resolve().parents[1]
_HYP_PY = _REPO / "pipelines" / "hypothesis.py"


def _m_spec(**overrides) -> HypothesisSpec:
    kwargs = dict(
        id="HYP-20261125-FC1",
        title="False-certainty guard",
        claim_type="M",
        layer="Marker",
        summary="Synthetic marker for reliability invariants.",
        pass_fail=PassFail(criteria="Any result", thresholds={}),
        data=DataSpec(mode="synthetic", params={"N": 8, "n_steps": 3, "seed": 7}),
    )
    kwargs.update(overrides)
    return HypothesisSpec(**kwargs)


def test_hypothesis_module_has_no_rng_normal_fabrication():
    """AST guard: governance path must not invent topology from rng.normal."""
    tree = ast.parse(_HYP_PY.read_text(encoding="utf-8"))
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute) and func.attr == "normal":
                offenders.append(node.lineno)
            if isinstance(func, ast.Attribute) and func.attr == "nan_to_num":
                offenders.append(node.lineno)
    assert not offenders, f"Forbidden fabrication call(s) at lines {offenders}"


def test_run_hypothesis_uses_real_cgl_not_fixed_fabricated_means(tmp_path):
    """Different seeds must change topology metrics (RNG-normal stub was seed=42 fixed)."""
    s1 = run_hypothesis(
        _m_spec(data=DataSpec(mode="synthetic", params={"N": 8, "n_steps": 4, "seed": 1})),
        output_dir=tmp_path / "a",
    )
    s2 = run_hypothesis(
        _m_spec(
            id="HYP-20261125-FC2",
            data=DataSpec(mode="synthetic", params={"N": 8, "n_steps": 4, "seed": 99}),
        ),
        output_dir=tmp_path / "b",
    )
    m1, m2 = s1["metrics_summary"], s2["metrics_summary"]
    assert m1["metric_kind"] == "cgl_topology_metrics"
    assert m2["metric_kind"] == "cgl_topology_metrics"
    # Real CGL differs across seeds; the old stub always produced identical floats.
    assert (m1["Qabs_mean"], m1["Q_mean"], m1["I_mean"]) != (
        m2["Qabs_mean"],
        m2["Q_mean"],
        m2["I_mean"],
    )


def test_run_hypothesis_watermarks_and_blocks_scientific_pass(tmp_path):
    summary = run_hypothesis(_m_spec(), output_dir=tmp_path)
    assert summary["metrics_are_empirical"] is False
    assert summary["scientific_pass"] is False
    assert summary["evidence_class"] == "synthetic_hypothesis_demonstration"
    assert summary["run_mode"] == "synthetic"
    assert summary["verdict"] == "ambiguous"

    rr = json.loads((tmp_path / summary["run_id"] / "RunRecord.json").read_text())
    assert rr["metrics_are_empirical"] is False
    assert rr["scientific_pass"] is False
    assert rr["evidence_class"] == "synthetic_hypothesis_demonstration"
    assert rr["run_mode"] == "synthetic"
    assert rr["metric_kind"] == "cgl_topology_metrics"
    assert watermark_scan_main([str(tmp_path / summary["run_id"])]) == 0


def test_run_hypothesis_never_pass_empirical_mode_on_synthetic_metrics(tmp_path):
    """openneuro/empirical data_mode + CGL-only metrics cannot claim empirical pass."""
    spec = _m_spec(
        id="HYP-20261125-EMP",
        data=DataSpec(mode="openneuro", dataset_id="ds002094", params={"N": 8, "n_steps": 3, "seed": 3}),
        pass_fail=PassFail(criteria="Qabs_mean > -999", thresholds={"Qabs": -999.0}),
    )
    summary = run_hypothesis(spec, output_dir=tmp_path)
    assert summary["metrics_are_empirical"] is False
    assert summary["scientific_pass"] is False
    assert summary["evidence_class"] == "governance_hypothesis_scaffold"
    assert summary["run_mode"] == "synthetic"
    assert summary["verdict"] == "blocked_non_empirical"


def test_yaml_run_stamps_watermarks_and_seed_imputed(tmp_path):
    spec = tmp_path / "spec.yaml"
    # No seed → seed_imputed watermark; synthetic PASS is engineering-only.
    spec.write_text(
        "spec_id: WM-001\ndata_mode: synthetic\n"
        "threshold:\n  I_mean_min: 0.0\n"
        "sim_params:\n  N: 8\n  n_steps: 3\n"
    )
    summary = run(spec, tmp_path / "out")
    assert summary["verdict"] == "PASS"
    assert summary["scientific_pass"] is False
    assert summary["metrics_are_empirical"] is False
    assert summary["metrics_summary"]["seed_imputed"] is True
    rr = json.loads((tmp_path / "out" / "RunRecord.json").read_text())
    for key in (
        "evidence_class",
        "run_mode",
        "metrics_are_empirical",
        "scientific_pass",
        "metric_kind",
    ):
        assert key in rr and rr[key] is not None
    assert rr["scientific_pass"] is False
    assert watermark_scan_main([str(tmp_path / "out")]) == 0


def test_yaml_run_deterministic_run_id_with_explicit_seed(tmp_path):
    spec = tmp_path / "spec.yaml"
    spec.write_text(
        "spec_id: DET-001\nsim_params:\n  N: 8\n  n_steps: 3\n  seed: 11\n"
    )
    run(spec, tmp_path / "o1")
    run(spec, tmp_path / "o2")
    r1 = json.loads((tmp_path / "o1" / "RunRecord.json").read_text())
    r2 = json.loads((tmp_path / "o2" / "RunRecord.json").read_text())
    assert r1["run_id"] == r2["run_id"]
    assert r1["metrics"]["seed_imputed"] is False


def test_watermark_scanner_rejects_synthetic_claiming_empirical(tmp_path):
    bad = {
        "schema_version": "0.1",
        "run_id": "a" * 16,
        "run_kind": "hypothesis",
        "spec_id": "BAD",
        "verdict": "PASS",
        "metrics": {"metric_kind": "cgl_topology_metrics"},
        "evidence_class": "synthetic_hypothesis_demonstration",
        "run_mode": "synthetic",
        "metrics_are_empirical": True,
        "scientific_pass": True,
        "metric_kind": "cgl_topology_metrics",
    }
    path = tmp_path / "RunRecord.json"
    path.write_text(json.dumps(bad), encoding="utf-8")
    errors = scan_json(path)
    assert any("metrics_are_empirical=True" in e for e in errors)
    assert any("scientific_pass=True" in e for e in errors)
    assert watermark_scan_main([str(tmp_path)]) == 1


def test_run_hypothesis_deterministic_run_id(tmp_path):
    spec = _m_spec()
    s1 = run_hypothesis(spec, output_dir=tmp_path / "x")
    s2 = run_hypothesis(spec, output_dir=tmp_path / "y")
    assert s1["run_id"] == s2["run_id"]
