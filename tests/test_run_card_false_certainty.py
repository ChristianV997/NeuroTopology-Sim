"""Fail-closed invariants for sim run-card fabricated-zero / watermark gaps.

Proves:
  - run_meditation_sim does not fabricate topology zeros (null/n/a instead)
  - psi + meditation cards stamp evidence watermarks and scientific_pass=False
  - to_sim_dict persists watermarks on .run.json
  - run-card watermark scanner rejects fabricated meditation zeros / missing stamps
  - per-step topology failure markers are non-finite (not fabricated 0.0)
"""
from __future__ import annotations

import ast
import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from sim.run_cards import run_meditation_sim, run_psi_os
from tools.check_run_card_artifact_watermarks import main as watermark_scan_main
from tools.check_run_card_artifact_watermarks import scan_json

_NOW = datetime(2025, 1, 15, 12, 0, 0, tzinfo=timezone.utc)
_REPO = Path(__file__).resolve().parents[1]
_RUN_CARDS_PY = _REPO / "sim" / "run_cards.py"


def test_meditation_module_has_no_literal_fabricated_topology_zeros():
    """AST guard: meditation metrics block must not assign 0.0 to topology keys."""
    tree = ast.parse(_RUN_CARDS_PY.read_text(encoding="utf-8"))
    in_meditation = False
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "run_meditation_sim":
            for child in ast.walk(node):
                if isinstance(child, ast.Dict):
                    for key, val in zip(child.keys, child.values):
                        if key is None or not isinstance(key, ast.Constant):
                            continue
                        k = key.value
                        if k not in {"Qz_mean", "Qabs_mean", "f_dress", "vort_mean"}:
                            continue
                        if isinstance(val, ast.Constant) and val.value == 0.0:
                            offenders.append((k, getattr(child, "lineno", "?")))
            in_meditation = True
            break
    assert in_meditation
    assert not offenders, f"Fabricated topology zero literal(s): {offenders}"


def test_run_meditation_sim_topology_is_null_not_fabricated_zero(tmp_path):
    record, md_path, json_path = run_meditation_sim(
        n_epochs=5, seed=0, out_dir=tmp_path, _now=_NOW
    )
    for key in ("Qz_mean", "Qabs_mean", "f_dress", "vort_mean"):
        assert record.metrics[key] is None, f"{key} must be null, not fabricated zero"
    data = json.loads(json_path.read_text(encoding="utf-8"))
    for key in ("Qz_mean", "Qabs_mean", "f_dress", "vort_mean"):
        assert data["metrics"][key] is None
    md = md_path.read_text(encoding="utf-8")
    assert "n/a" in md
    assert "Evidence watermark" in md


def test_run_meditation_sim_watermarks_block_scientific_pass(tmp_path):
    record, _, json_path = run_meditation_sim(
        n_epochs=5, seed=0, out_dir=tmp_path, _now=_NOW
    )
    assert record.metrics_are_empirical is False
    assert record.scientific_pass is False
    assert record.evidence_class == "synthetic_meditation_scaffold"
    assert record.run_mode == "synthetic"
    assert record.metric_kind == "synthetic_alpha_band_intensity_only"
    assert record.guardrails.get("topology_metrics_applicable") is False

    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["metrics_are_empirical"] is False
    assert data["scientific_pass"] is False
    assert data["evidence_class"] == "synthetic_meditation_scaffold"
    assert data["run_mode"] == "synthetic"
    assert data["metric_kind"] == "synthetic_alpha_band_intensity_only"
    assert watermark_scan_main([str(tmp_path)]) == 0


def test_run_psi_os_watermarks_and_real_topology(tmp_path):
    record, _, json_path = run_psi_os(
        N=8, n_steps=5, seed=42, out_dir=tmp_path, _now=_NOW
    )
    assert record.metrics_are_empirical is False
    assert record.scientific_pass is False
    assert record.evidence_class == "synthetic_cgl_demonstration"
    assert record.run_mode == "synthetic"
    assert record.metric_kind == "cgl_topology_metrics"
    # Final topology must be finite floats (real CGL path, not null/zeros-only stub).
    for key in ("Qz_mean", "Qabs_mean", "f_dress"):
        assert isinstance(record.metrics[key], float)
    data = json.loads(json_path.read_text(encoding="utf-8"))
    assert data["scientific_pass"] is False
    assert data["metric_kind"] == "cgl_topology_metrics"
    assert watermark_scan_main([str(tmp_path)]) == 0


def test_step_topology_except_returns_nan_not_zero():
    """Source-level: except path must not return fabricated (0.0, 0.0, 0.0)."""
    src = _RUN_CARDS_PY.read_text(encoding="utf-8")
    assert 'return 0.0, 0.0, 0.0' not in src
    assert 'return float("nan"), float("nan"), float("nan")' in src


def test_watermark_scanner_rejects_meditation_fabricated_zeros(tmp_path):
    bad = {
        "schema_version": "1",
        "run_id": "0123456789abcdef",
        "mode": "meditation",
        "metrics": {
            "I_mean": 0.5,
            "I_std": 0.1,
            "I_final": 0.4,
            "vort_mean": 0.0,
            "n_steps": 5.0,
            "Qz_mean": 0.0,
            "Qabs_mean": 0.0,
            "f_dress": 0.0,
        },
        "evidence_class": "synthetic_meditation_scaffold",
        "run_mode": "synthetic",
        "metrics_are_empirical": False,
        "scientific_pass": False,
        "metric_kind": "synthetic_alpha_band_intensity_only",
    }
    path = tmp_path / "bad.run.json"
    path.write_text(json.dumps(bad), encoding="utf-8")
    errs = scan_json(path)
    assert any("fabricates topology zero" in e for e in errs)
    assert watermark_scan_main([str(tmp_path)]) == 1


def test_watermark_scanner_rejects_missing_watermarks(tmp_path):
    bare = {
        "schema_version": "1",
        "run_id": "fedcba9876543210",
        "mode": "psi",
        "metrics": {
            "I_mean": 0.5,
            "I_std": 0.1,
            "I_final": 0.4,
            "vort_mean": 0.1,
            "n_steps": 5.0,
            "Qz_mean": 1.0,
            "Qabs_mean": 2.0,
            "f_dress": 0.5,
        },
    }
    path = tmp_path / "bare.run.json"
    path.write_text(json.dumps(bare), encoding="utf-8")
    errs = scan_json(path)
    assert any("missing required watermark key" in e for e in errs)
    assert watermark_scan_main([str(tmp_path)]) == 1


def test_watermark_scanner_rejects_synthetic_scientific_pass(tmp_path):
    bad = {
        "schema_version": "1",
        "run_id": "aaaaaaaaaaaaaaaa",
        "mode": "psi",
        "metrics": {
            "I_mean": 0.5,
            "I_std": 0.1,
            "I_final": 0.4,
            "vort_mean": 0.1,
            "n_steps": 5.0,
            "Qz_mean": 1.0,
            "Qabs_mean": 2.0,
            "f_dress": 0.5,
        },
        "evidence_class": "synthetic_cgl_demonstration",
        "run_mode": "synthetic",
        "metrics_are_empirical": False,
        "scientific_pass": True,
        "metric_kind": "cgl_topology_metrics",
    }
    path = tmp_path / "sci_pass.run.json"
    path.write_text(json.dumps(bad), encoding="utf-8")
    assert any("scientific_pass=True" in e for e in scan_json(path))
    assert watermark_scan_main([str(tmp_path)]) == 1
