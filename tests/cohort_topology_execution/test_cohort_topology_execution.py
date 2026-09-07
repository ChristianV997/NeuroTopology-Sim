"""Comprehensive tests for streaming paired-cohort topology execution subsystem."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import numpy as np
import pytest

from tools.cohort_execution import (
    CohortTopologyExecutionSummary,
    ExecutionStatus,
    RecordingStreamer,
    RefusalReasonCode,
    compute_window_topology,
    execute_cohort_topology,
    validate_manifest_readiness,
)


def _make_dummy_npy(path: Path, channels: int = 16, samples: int = 2048, seed: int = 42) -> Path:
    rng = np.random.default_rng(seed)
    # Sine wave with noise
    t = np.linspace(0, 2 * np.pi * 10, samples)
    data = np.zeros((channels, samples), dtype=np.float64)
    for ch in range(channels):
        data[ch] = np.sin(t + ch * 0.2) + 0.1 * rng.standard_normal(samples)
    np.save(path, data)
    return path


def _make_manifest_json(
    path: Path,
    pairs: list[tuple[Path, Path, str, str, bool]],
    *,
    status: str = "valid_paired_cohort",
    min_pairs: int = 2,
    ambiguous: list[dict] | None = None,
    provenance_status: str = "complete_provenance",
    missing_prov: bool = False,
    **kwargs,
) -> Path:
    paired_records = []
    for idx, (fa, fb, cond_a, cond_b, is_synth) in enumerate(pairs):
        prov_a = {} if missing_prov else {"subject_source": "bids_dir", "condition_source": "filename"}
        prov_b = {} if missing_prov else {"subject_source": "bids_dir", "condition_source": "filename"}
        paired_records.append({
            "pairing_key": {"subject": f"sub-{idx+1:02d}"},
            "is_synthetic": is_synth,
            "condition_a_record": {
                "file_path": str(fa.resolve()),
                "format": fa.suffix.lstrip(".").lower(),
                "subject": f"sub-{idx+1:02d}",
                "condition": cond_a,
                "is_synthetic": is_synth,
                "provenance": prov_a,
                "sample_rate": 1000.0,
            },
            "condition_b_record": {
                "file_path": str(fb.resolve()),
                "format": fb.suffix.lstrip(".").lower(),
                "subject": f"sub-{idx+1:02d}",
                "condition": cond_b,
                "is_synthetic": is_synth,
                "provenance": prov_b,
                "sample_rate": 1000.0,
            },
        })

    data = {
        "status": status,
        "status_reason": f"Cohort readiness status: {status}",
        "provenance_status": provenance_status,
        "condition_a": "awake",
        "condition_b": "sedated",
        "min_pairs": min_pairs,
        "empirical_paired_count": sum(1 for p in paired_records if not p["is_synthetic"]),
        "synthetic_paired_count": sum(1 for p in paired_records if p["is_synthetic"]),
        "paired_records": paired_records,
        "ambiguous_matches": ambiguous or [],
        "invalid_files": [],
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return path


def test_valid_paired_manifest_execution(tmp_path: Path):
    """Verifies that a valid empirical paired manifest executes end-to-end."""
    f1a = _make_dummy_npy(tmp_path / "sub01_a.npy", seed=1)
    f1b = _make_dummy_npy(tmp_path / "sub01_b.npy", seed=2)
    f2a = _make_dummy_npy(tmp_path / "sub02_a.npy", seed=3)
    f2b = _make_dummy_npy(tmp_path / "sub02_b.npy", seed=4)

    manifest_p = _make_manifest_json(
        tmp_path / "manifest.json",
        [
            (f1a, f1b, "awake", "sedated", False),
            (f2a, f2b, "awake", "sedated", False),
        ],
        status="valid_paired_cohort",
        min_pairs=2,
    )

    out_dir = tmp_path / "artifacts"
    summary = execute_cohort_topology(
        manifest_p,
        out_dir,
        window_samples=512,
        chunk_size=1024,
    )

    assert summary.execution_status == ExecutionStatus.VALID_COHORT_PROCESSED.value
    assert summary.pairs_processed == 2
    assert summary.pairs_skipped == 0
    assert summary.empirical_pairs_count == 2
    assert summary.synthetic_pairs_count == 0

    # Check output files exist
    assert (out_dir / "cohort_topology_execution_summary.json").is_file()
    assert (out_dir / "cohort_topology_pairs.csv").is_file()
    assert (out_dir / "cohort_topology_windows.csv").is_file()

    # Check descriptive Wilcoxon presence
    wilcoxon = summary.descriptive_wilcoxon
    assert wilcoxon["n_pairs"] == 2
    assert "Descriptive non-parametric test only" in wilcoxon.get("note", "")


def test_insufficient_pairs_refusal_and_override(tmp_path: Path):
    """Verifies refusal on insufficient_pairs status unless allow_insufficient is set."""
    f1a = _make_dummy_npy(tmp_path / "sub01_a.npy")
    f1b = _make_dummy_npy(tmp_path / "sub01_b.npy")

    manifest_p = _make_manifest_json(
        tmp_path / "manifest_insufficient.json",
        [(f1a, f1b, "awake", "sedated", False)],
        status="insufficient_pairs",
        min_pairs=2,
    )

    # 1. Default refusal
    out_dir1 = tmp_path / "artifacts_refused"
    summary1 = execute_cohort_topology(manifest_p, out_dir1, allow_insufficient=False)
    assert summary1.execution_status == ExecutionStatus.REFUSED.value
    assert any("insufficient_pairs" in r for r in summary1.refusal_reasons)
    assert summary1.pairs_processed == 0

    # 2. Allowed insufficient
    out_dir2 = tmp_path / "artifacts_allowed"
    summary2 = execute_cohort_topology(manifest_p, out_dir2, allow_insufficient=True, window_samples=512)
    assert summary2.execution_status == ExecutionStatus.INSUFFICIENT_PAIRS_PROCESSED.value
    assert summary2.pairs_processed == 1
    # Wilcoxon should indicate insufficient pairs for test (N < 2)
    assert summary2.descriptive_wilcoxon["status"] == "insufficient_empirical_pairs"


def test_malformed_manifest_refusal(tmp_path: Path):
    """Verifies refusal on malformed manifest or bad JSON."""
    bad_json_p = tmp_path / "bad.json"
    bad_json_p.write_text("{ not json ", encoding="utf-8")

    out_dir = tmp_path / "artifacts_bad"
    summary = execute_cohort_topology(bad_json_p, out_dir)
    assert summary.execution_status == ExecutionStatus.REFUSED.value
    assert any("Malformed JSON" in r for r in summary.refusal_reasons)

    malformed_p = tmp_path / "malformed.json"
    malformed_p.write_text(json.dumps({"status": "malformed", "status_reason": "Header corruption"}), encoding="utf-8")
    summary2 = execute_cohort_topology(malformed_p, out_dir)
    assert summary2.execution_status == ExecutionStatus.REFUSED.value
    assert any("malformed" in r for r in summary2.refusal_reasons)


def test_no_data_refusal(tmp_path: Path):
    """Verifies refusal when cohort manifest contains no data."""
    manifest_p = tmp_path / "no_data.json"
    manifest_p.write_text(json.dumps({
        "status": "no_data",
        "status_reason": "No BIDS directory found",
        "paired_records": [],
    }), encoding="utf-8")

    out_dir = tmp_path / "artifacts_no_data"
    summary = execute_cohort_topology(manifest_p, out_dir)
    assert summary.execution_status == ExecutionStatus.REFUSED.value
    assert any("no_data" in r for r in summary.refusal_reasons)


def test_ambiguous_labels_refusal(tmp_path: Path):
    """Verifies refusal when manifest contains ambiguous matches."""
    f1a = _make_dummy_npy(tmp_path / "sub01_a.npy")
    f1b = _make_dummy_npy(tmp_path / "sub01_b.npy")

    manifest_p = _make_manifest_json(
        tmp_path / "ambiguous.json",
        [(f1a, f1b, "awake", "sedated", False)],
        ambiguous=[{"subject": "sub-01", "reason": "multiple sessions unresolvable"}],
    )

    out_dir = tmp_path / "artifacts_ambiguous"
    summary = execute_cohort_topology(manifest_p, out_dir)
    assert summary.execution_status == ExecutionStatus.REFUSED.value
    assert any("ambiguous" in r for r in summary.refusal_reasons)


def test_incomplete_provenance_refusal(tmp_path: Path):
    """Verifies refusal when manifest has incomplete provenance metadata."""
    f1a = _make_dummy_npy(tmp_path / "sub01_a.npy")
    f1b = _make_dummy_npy(tmp_path / "sub01_b.npy")

    manifest_p = _make_manifest_json(
        tmp_path / "incomplete_prov.json",
        [(f1a, f1b, "awake", "sedated", False)],
        provenance_status="incomplete_provenance",
    )

    out_dir = tmp_path / "artifacts_incomplete_prov"
    summary = execute_cohort_topology(manifest_p, out_dir)
    assert summary.execution_status == ExecutionStatus.REFUSED.value
    assert any("incomplete_provenance" in r for r in summary.refusal_reasons)


def test_diagnostic_only_mode(tmp_path: Path):
    """Verifies diagnostic-only mode inspects readiness without streaming recordings."""
    manifest_p = tmp_path / "no_data.json"
    manifest_p.write_text(json.dumps({
        "status": "no_data",
        "status_reason": "No recordings found",
        "paired_records": [],
    }), encoding="utf-8")

    out_dir = tmp_path / "artifacts_diagnostic"
    summary = execute_cohort_topology(manifest_p, out_dir, diagnostic_only=True)

    assert summary.execution_status == ExecutionStatus.REFUSED.value
    assert len(summary.refusal_reasons) > 0
    assert summary.pairs_processed == 0
    assert "Diagnostic-only execution mode" in summary.scientific_note


def test_one_invalid_pair_skipped_while_valid_processed(tmp_path: Path):
    """Verifies that a cohort with one missing/broken file skips that pair without aborting the run."""
    f1a = _make_dummy_npy(tmp_path / "sub01_a.npy", seed=10)
    f1b = _make_dummy_npy(tmp_path / "sub01_b.npy", seed=11)
    missing_file = tmp_path / "non_existent.npy"
    f2b = _make_dummy_npy(tmp_path / "sub02_b.npy", seed=12)

    manifest_p = _make_manifest_json(
        tmp_path / "manifest_partial.json",
        [
            (f1a, f1b, "awake", "sedated", False),
            (missing_file, f2b, "awake", "sedated", False),
        ],
        status="valid_paired_cohort",
        min_pairs=1,
    )

    out_dir = tmp_path / "artifacts_partial"
    summary = execute_cohort_topology(manifest_p, out_dir, window_samples=512)

    assert summary.pairs_processed == 1
    assert summary.pairs_skipped == 1
    assert len(summary.skipped_pairs) == 1
    assert "non_existent" in summary.skipped_pairs[0]["reason"]


def test_deterministic_repeatability(tmp_path: Path):
    """Verifies that two runs with the same seed yield identical metrics."""
    f1a = _make_dummy_npy(tmp_path / "sub01_a.npy", seed=100)
    f1b = _make_dummy_npy(tmp_path / "sub01_b.npy", seed=101)

    manifest_p = _make_manifest_json(
        tmp_path / "manifest_det.json",
        [(f1a, f1b, "awake", "sedated", False)],
        allow_insufficient=True,
    )

    out1 = tmp_path / "out1"
    out2 = tmp_path / "out2"

    sum1 = execute_cohort_topology(manifest_p, out1, window_samples=512, seed=42, allow_insufficient=True)
    sum2 = execute_cohort_topology(manifest_p, out2, window_samples=512, seed=42, allow_insufficient=True)

    delta1 = sum1.processed_pairs[0]["delta_landscape_area"]
    delta2 = sum2.processed_pairs[0]["delta_landscape_area"]
    assert delta1 is not None
    assert delta1 == delta2


def test_bounded_streaming_and_max_windows(tmp_path: Path):
    """Verifies bounded streaming window limits via max_windows parameter."""
    # 4000 samples -> with window_samples=500, yields 8 windows
    f1a = _make_dummy_npy(tmp_path / "sub01_a.npy", samples=4000)
    f1b = _make_dummy_npy(tmp_path / "sub01_b.npy", samples=4000)

    manifest_p = _make_manifest_json(
        tmp_path / "manifest_bounded.json",
        [(f1a, f1b, "awake", "sedated", False)],
        allow_insufficient=True,
    )

    out = tmp_path / "out_bounded"
    summary = execute_cohort_topology(
        manifest_p,
        out,
        window_samples=500,
        max_windows=3,
        allow_insufficient=True,
    )

    pair = summary.processed_pairs[0]
    assert pair["condition_a"]["windows_processed"] == 3
    assert pair["condition_b"]["windows_processed"] == 3


def test_metric_separation_graph_vs_spatial(tmp_path: Path):
    """Verifies graph persistent homology (beta_1) and spatial topological charge (Q_spatial) are separate."""
    # Create a 16-channel array (4x4 grid) with known vortex
    channels = 16
    samples = 512
    side = 4
    yy, xx = np.mgrid[:side, :side]
    vortex = np.arctan2(yy - (side - 1) / 2, xx - (side - 1) / 2).ravel()

    t = np.linspace(0, 1, samples)
    data = np.zeros((channels, samples))
    for ch in range(channels):
        data[ch] = np.sin(2 * np.pi * 20 * t + vortex[ch])

    metrics = compute_window_topology(data)

    assert metrics.is_finite is True
    # Graph persistent homology: beta1_max, filtration_beta1_max, integrated_landscape_area
    assert isinstance(metrics.filtration_beta1_max, int)
    assert isinstance(metrics.integrated_landscape_area, float)
    # Spatial charge: separate field
    assert metrics.spatial_charge_available is True
    assert metrics.spatial_charge is not None
    assert isinstance(metrics.spatial_charge, float)


def test_finite_null_safe_json_serialization(tmp_path: Path):
    """Verifies that all generated summary files contain strictly finite null-safe values."""
    f1a = _make_dummy_npy(tmp_path / "sub01_a.npy")
    f1b = _make_dummy_npy(tmp_path / "sub01_b.npy")

    manifest_p = _make_manifest_json(
        tmp_path / "manifest_nullsafe.json",
        [(f1a, f1b, "awake", "sedated", False)],
        allow_insufficient=True,
    )

    out = tmp_path / "out_nullsafe"
    execute_cohort_topology(manifest_p, out, window_samples=512, allow_insufficient=True)

    json_p = out / "cohort_topology_execution_summary.json"
    raw_text = json_p.read_text(encoding="utf-8")

    # Strict JSON standard forbids NaN, Infinity, -Infinity
    assert "NaN" not in raw_text
    assert "Infinity" not in raw_text

    parsed = json.loads(raw_text)
    assert parsed["schema"] == "NeuroTopologySim.CohortTopologyExecutionSummary.v1"


def test_synthetic_data_labeling_and_segregation(tmp_path: Path):
    """Verifies synthetic demo pairs are labeled is_synthetic: True and segregated."""
    f_synth_a = _make_dummy_npy(tmp_path / "synth_a.npy")
    f_synth_b = _make_dummy_npy(tmp_path / "synth_b.npy")
    f_emp_a = _make_dummy_npy(tmp_path / "emp_a.npy")
    f_emp_b = _make_dummy_npy(tmp_path / "emp_b.npy")

    manifest_p = _make_manifest_json(
        tmp_path / "manifest_segregated.json",
        [
            (f_synth_a, f_synth_b, "awake", "sedated", True),
            (f_emp_a, f_emp_b, "awake", "sedated", False),
        ],
        allow_insufficient=True,
    )

    out = tmp_path / "out_segregated"
    summary = execute_cohort_topology(manifest_p, out, window_samples=512, allow_insufficient=True)

    assert summary.synthetic_pairs_count == 1
    assert summary.empirical_pairs_count == 1
    assert summary.processed_pairs[0]["is_synthetic"] is True
    assert summary.processed_pairs[1]["is_synthetic"] is False
    assert summary.descriptive_aggregate["synthetic"]["pairs_count"] == 1
    assert summary.descriptive_aggregate["empirical"]["pairs_count"] == 1


def test_cli_runner_exit_codes(tmp_path: Path):
    """Verifies CLI runner exit codes and execution from scripts/run_cohort_topology.py."""
    f1a = _make_dummy_npy(tmp_path / "sub01_a.npy")
    f1b = _make_dummy_npy(tmp_path / "sub01_b.npy")

    manifest_valid = _make_manifest_json(
        tmp_path / "manifest_valid.json",
        [(f1a, f1b, "awake", "sedated", False)],
        allow_insufficient=True,
    )

    out_valid = tmp_path / "cli_valid"
    res_valid = subprocess.run(
        [
            sys.executable,
            "scripts/run_cohort_topology.py",
            "--manifest",
            str(manifest_valid),
            "--output-dir",
            str(out_valid),
            "--window-samples",
            "512",
            "--allow-insufficient",
        ],
        capture_output=True,
        text=True,
    )
    assert res_valid.returncode == 0
    assert "VALID_COHORT_PROCESSED" in res_valid.stdout or "INSUFFICIENT_PAIRS_PROCESSED" in res_valid.stdout

    # Test CLI refusal exit code = 2
    manifest_refused = tmp_path / "manifest_no_data.json"
    manifest_refused.write_text(json.dumps({"status": "no_data", "paired_records": []}), encoding="utf-8")
    out_refused = tmp_path / "cli_refused"
    res_refused = subprocess.run(
        [
            sys.executable,
            "scripts/run_cohort_topology.py",
            "--manifest",
            str(manifest_refused),
            "--output-dir",
            str(out_refused),
        ],
        capture_output=True,
        text=True,
    )
    assert res_refused.returncode == 2


def test_optional_dependency_unavailable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Verifies that if an optional dependency like ripser fails, execution skips gracefully."""
    import tools.cohort_execution.topology as top_mod

    def mock_analyze(*args, **kwargs):
        raise RuntimeError("ripser is required for persistent H1")

    monkeypatch.setattr(top_mod, "analyze_adjacency", mock_analyze)

    f1a = _make_dummy_npy(tmp_path / "sub01_a.npy")
    f1b = _make_dummy_npy(tmp_path / "sub01_b.npy")

    manifest = _make_manifest_json(
        tmp_path / "manifest.json",
        [(f1a, f1b, "awake", "sedated", False)],
        allow_insufficient=True,
    )

    out = tmp_path / "out_deps"
    summary = execute_cohort_topology(manifest, out, window_samples=512, allow_insufficient=True)

    assert summary.pairs_processed == 0
    assert summary.pairs_skipped == 1
    assert len(summary.skipped_pairs) == 1
    assert "ripser is required" in summary.skipped_pairs[0]["reason"]

