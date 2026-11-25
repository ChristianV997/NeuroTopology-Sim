"""Tests for export_sim_artifacts — offline, no network, no LLM."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Make tools/ importable from this test
_TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

try:
    from tools.export_sim_artifacts import (
        export,
        _render_markdown,
        _out_filename,
        classify_evidence_stamps,
    )
except ModuleNotFoundError:
    from export_sim_artifacts import (
        export,
        _render_markdown,
        _out_filename,
        classify_evidence_stamps,
    )

_RUN_ID = "deadbeef01234567"
_RUN_KIND = "hypothesis"


def _make_run_record(tmp_path: Path, **overrides) -> Path:
    """Write a minimal RunRecord.json to tmp_path/artifacts/run1/RunRecord.json."""
    record = {
        "schema_version": "0.1",
        "run_id": _RUN_ID,
        "run_kind": _RUN_KIND,
        "created_at": "2025-01-15T12:00:00+00:00",
        "elapsed_s": 0.5,
        "spec_id": "HYP-001",
        "claim_type": "topology_gain_control",
        "layer": "biophysical",
        "data_mode": "synthetic",
        "dataset_id": "ds_test",
        "verdict": "PASS",
        "metrics": {"I_mean": 0.5, "I_std": 0.1},
        "artifacts": {"summary.json": "artifacts/run1/summary.json"},
        "source": "governance/specs/HYP-001.yaml",
    }
    record.update(overrides)
    art_dir = tmp_path / "artifacts" / "run1"
    art_dir.mkdir(parents=True, exist_ok=True)
    rr = art_dir / "RunRecord.json"
    rr.write_text(json.dumps(record), encoding="utf-8")
    return rr


# ── _render_markdown ──────────────────────────────────────────────────────────

def test_render_has_frontmatter(tmp_path):
    _make_run_record(tmp_path)
    record = json.loads((tmp_path / "artifacts" / "run1" / "RunRecord.json").read_text())
    md = _render_markdown(record)
    assert md.startswith("---")
    assert "run_id:" in md
    assert "run_kind:" in md


def test_render_frontmatter_contains_required_keys(tmp_path):
    _make_run_record(tmp_path)
    record = json.loads((tmp_path / "artifacts" / "run1" / "RunRecord.json").read_text())
    md = _render_markdown(record)
    for key in (
        "run_id",
        "run_kind",
        "spec_id",
        "claim_type",
        "layer",
        "created_at",
        "verdict",
        "engineering_verdict",
        "evidence_class",
        "run_mode",
        "metrics_are_empirical",
        "scientific_pass",
        "epistemic_status",
    ):
        assert f"{key}:" in md, f"Missing frontmatter key: {key}"
    # Body must not present a bare empirical Verdict headline for incomplete stamps.
    assert "**Verdict:**" not in md


def test_render_has_metrics_table(tmp_path):
    _make_run_record(tmp_path)
    record = json.loads((tmp_path / "artifacts" / "run1" / "RunRecord.json").read_text())
    md = _render_markdown(record)
    assert "## Metrics" in md
    assert "I_mean" in md


def test_render_has_artifacts_section(tmp_path):
    _make_run_record(tmp_path)
    record = json.loads((tmp_path / "artifacts" / "run1" / "RunRecord.json").read_text())
    md = _render_markdown(record)
    assert "## Artifacts" in md
    assert "summary.json" in md


# ── _out_filename ─────────────────────────────────────────────────────────────

def test_out_filename_stable():
    record = {"run_id": _RUN_ID, "run_kind": _RUN_KIND}
    fname = _out_filename(record)
    assert fname == f"run_{_RUN_KIND}_{_RUN_ID}.md"


def test_out_filename_spaces_replaced():
    record = {"run_id": "abc", "run_kind": "my kind"}
    fname = _out_filename(record)
    assert " " not in fname


# ── export — primary path (RunRecord.json) ────────────────────────────────────

def test_export_finds_run_record(tmp_path):
    _make_run_record(tmp_path)
    out_dir = tmp_path / "out"
    written = export(tmp_path / "artifacts", out_dir)
    assert len(written) == 1


def test_export_creates_markdown_file(tmp_path):
    _make_run_record(tmp_path)
    out_dir = tmp_path / "out"
    written = export(tmp_path / "artifacts", out_dir)
    assert written[0].exists()
    assert written[0].suffix == ".md"


def test_export_filename_contains_run_id(tmp_path):
    _make_run_record(tmp_path)
    out_dir = tmp_path / "out"
    written = export(tmp_path / "artifacts", out_dir)
    assert _RUN_ID in written[0].name


def test_export_markdown_has_frontmatter(tmp_path):
    _make_run_record(tmp_path)
    out_dir = tmp_path / "out"
    written = export(tmp_path / "artifacts", out_dir)
    content = written[0].read_text()
    assert content.startswith("---")
    assert "run_id:" in content


def test_export_markdown_frontmatter_has_all_keys(tmp_path):
    _make_run_record(tmp_path)
    out_dir = tmp_path / "out"
    written = export(tmp_path / "artifacts", out_dir)
    content = written[0].read_text()
    for key in (
        "run_id",
        "run_kind",
        "spec_id",
        "claim_type",
        "layer",
        "created_at",
        "engineering_verdict",
        "epistemic_status",
    ):
        assert f"{key}:" in content, f"Missing: {key}"


def test_export_multiple_run_records(tmp_path):
    _make_run_record(tmp_path)
    # Second record in different sub-dir
    art2 = tmp_path / "artifacts" / "run2"
    art2.mkdir(parents=True)
    r2 = {
        "schema_version": "0.1", "run_id": "aabbccdd11223344", "run_kind": "hypothesis",
        "created_at": "2025-01-16T12:00:00+00:00", "elapsed_s": None,
        "spec_id": "HYP-002", "claim_type": None, "layer": None,
        "data_mode": None, "dataset_id": None, "verdict": "FAIL",
        "metrics": {}, "artifacts": {}, "source": "",
    }
    (art2 / "RunRecord.json").write_text(json.dumps(r2), encoding="utf-8")
    written = export(tmp_path / "artifacts", tmp_path / "out")
    assert len(written) == 2


# ── export — fallback path (summary.json) ─────────────────────────────────────

def test_export_fallback_summary_json(tmp_path):
    art_dir = tmp_path / "artifacts" / "run_legacy"
    art_dir.mkdir(parents=True)
    summary = {
        "run_id": "legacy001", "spec_id": "HYP-LEG",
        "verdict": "PASS", "metrics_summary": {"I_mean": 0.3},
        "created_at": "2025-01-15T12:00:00+00:00",
    }
    (art_dir / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    written = export(tmp_path / "artifacts", tmp_path / "out")
    assert len(written) == 1
    assert "legacy001" in written[0].name


def test_export_prefers_run_record_over_summary(tmp_path):
    """If both RunRecord.json and summary.json exist, prefer RunRecord.json."""
    _make_run_record(tmp_path)
    art_dir = tmp_path / "artifacts" / "run1"
    (art_dir / "summary.json").write_text('{"run_id":"should_not_appear"}', encoding="utf-8")
    written = export(tmp_path / "artifacts", tmp_path / "out")
    content = written[0].read_text()
    assert _RUN_ID in content
    assert "should_not_appear" not in content


def test_export_empty_artifacts_dir(tmp_path):
    (tmp_path / "artifacts").mkdir()
    written = export(tmp_path / "artifacts", tmp_path / "out")
    assert written == []


# ── Fail-closed evidence watermark gate ───────────────────────────────────────

def test_missing_watermarks_fail_closed_non_empirical():
    stamps = classify_evidence_stamps(
        {"run_id": "x", "verdict": "PASS", "metrics": {"I_mean": 1.0}}
    )
    assert stamps["treat_as_empirical"] is False
    assert stamps["epistemic_status"] == "NON_EMPIRICAL_INCOMPLETE"
    assert stamps["metrics_are_empirical"] is False
    assert stamps["scientific_pass"] is False
    assert stamps["engineering_verdict"] == "PASS"


def test_synthetic_watermarks_are_non_empirical_not_scientific():
    stamps = classify_evidence_stamps(
        {
            "verdict": "PASS",
            "evidence_class": "synthetic_hypothesis_demonstration",
            "run_mode": "synthetic",
            "metrics_are_empirical": False,
            "scientific_pass": False,
            "metric_kind": "cgl_topology",
        }
    )
    assert stamps["treat_as_empirical"] is False
    assert stamps["epistemic_status"] == "NON_EMPIRICAL"
    assert stamps["scientific_pass"] is False


def test_empirical_claim_with_synthetic_run_mode_is_conflict():
    stamps = classify_evidence_stamps(
        {
            "verdict": "PASS",
            "evidence_class": "descriptive_empirical",
            "run_mode": "synthetic",
            "metrics_are_empirical": True,
            "scientific_pass": False,
        }
    )
    assert stamps["treat_as_empirical"] is False
    assert stamps["epistemic_status"] == "NON_EMPIRICAL_CONFLICT"
    assert stamps["metrics_are_empirical"] is False


def test_complete_empirical_watermarks_declared_only_not_scientific_pass():
    stamps = classify_evidence_stamps(
        {
            "verdict": "PASS",
            "evidence_class": "descriptive_empirical",
            "run_mode": "recorded_dataset",
            "metrics_are_empirical": True,
            "scientific_pass": True,  # exporter must not echo scientific confirmation
            "metric_kind": "eeg_topology",
        }
    )
    assert stamps["treat_as_empirical"] is True
    assert stamps["epistemic_status"] == "DECLARED_EMPIRICAL_METRICS"
    assert stamps["scientific_pass"] is False


def test_render_stamps_pass_verdict_as_engineering_only_when_incomplete(tmp_path):
    _make_run_record(tmp_path, verdict="PASS")  # no watermarks
    record = json.loads((tmp_path / "artifacts" / "run1" / "RunRecord.json").read_text())
    md = _render_markdown(record)
    assert "NON-EMPIRICAL" in md
    assert "NON_EMPIRICAL_INCOMPLETE" in md
    assert "Engineering verdict" in md
    assert "not empirical" in md.lower()
    assert "## Evidence watermark" in md
    # Must not present a bare empirical Verdict headline.
    assert "**Verdict:** PASS" not in md


def test_export_stamps_legacy_summary_pass_as_non_empirical(tmp_path):
    art_dir = tmp_path / "artifacts" / "run_legacy"
    art_dir.mkdir(parents=True)
    summary = {
        "run_id": "legacy_pass",
        "spec_id": "HYP-LEG",
        "verdict": "PASS",
        "metrics_summary": {"I_mean": 0.9},
        "created_at": "2025-01-15T12:00:00+00:00",
    }
    (art_dir / "summary.json").write_text(json.dumps(summary), encoding="utf-8")
    written = export(tmp_path / "artifacts", tmp_path / "out")
    content = written[0].read_text()
    assert "NON-EMPIRICAL" in content
    assert "engineering_verdict: 'PASS'" in content or 'engineering_verdict: "PASS"' in content
    assert "metrics_are_empirical: False" in content


def test_export_preserves_complete_non_empirical_watermarks(tmp_path):
    _make_run_record(
        tmp_path,
        verdict="PASS",
        evidence_class="synthetic_hypothesis_demonstration",
        run_mode="synthetic",
        metrics_are_empirical=False,
        scientific_pass=False,
        metric_kind="cgl_topology",
    )
    written = export(tmp_path / "artifacts", tmp_path / "out")
    content = written[0].read_text()
    assert "epistemic_status: 'NON_EMPIRICAL'" in content or 'epistemic_status: "NON_EMPIRICAL"' in content
    assert "synthetic_hypothesis_demonstration" in content
    assert "metrics_are_empirical: False" in content
    assert "scientific_pass: False" in content
