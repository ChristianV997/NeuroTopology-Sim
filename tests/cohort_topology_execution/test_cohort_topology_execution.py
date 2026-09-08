"""Comprehensive verification suite for streaming paired-cohort topology execution.

Tests all Batch 2/2 requirements:
- one-pair processing
- multiple paired subjects
- missing condition
- missing montage coordinates (explicit null)
- synthetic-only input (SYNTHETIC_DEMO_ONLY)
- bounded memory telemetry
- deterministic repeated output and canonical output_checksum
- node reordering invariance
- graph/spatial metric separation
- optional backend absence (MISSING_OPTIONAL_DEPENDENCY)
- no-network execution
- CLI isolated subprocess runner
"""
from __future__ import annotations

import json
from pathlib import Path
import socket
import subprocess
import sys
from typing import Any
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
    **kwargs: Any,
) -> Path:
    paired_records = []
    for idx, (fa, fb, cond_a, cond_b, is_synth) in enumerate(pairs):
        prov_a = {} if missing_prov else {"subject_source": "bids_dir", "condition_source": "filename"}
        prov_b = {} if missing_prov else {"subject_source": "bids_dir", "condition_source": "filename"}
        paired_records.append({
            "pairing_key": {"subject": f"sub-{idx+1:02d}"},
            "is_synthetic": is_synth,
            "condition_a_record": {
                "file_path": str(fa.resolve()) if fa else None,
                "format": fa.suffix.lstrip(".").lower() if fa else "unknown",
                "subject": f"sub-{idx+1:02d}",
                "condition": cond_a,
                "is_synthetic": is_synth,
                "provenance": prov_a,
                "sample_rate": 1000.0,
            },
            "condition_b_record": {
                "file_path": str(fb.resolve()) if fb else None,
                "format": fb.suffix.lstrip(".").lower() if fb else "unknown",
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


def test_one_pair_processing(tmp_path: Path):
    """Verifies single-pair processing with valid paired metrics and persistence distance."""
    f1a = _make_dummy_npy(tmp_path / "sub01_a.npy", seed=10)
    f1b = _make_dummy_npy(tmp_path / "sub01_b.npy", seed=11)

    manifest_p = _make_manifest_json(
        tmp_path / "manifest_one.json",
        [(f1a, f1b, "awake", "sedated", False)],
        min_pairs=1,
    )

    out = tmp_path / "out_one"
    summary = execute_cohort_topology(manifest_p, out, window_samples=512)

    assert summary.execution_status == ExecutionStatus.DESCRIPTIVE_READY.value
    assert summary.pairs_processed == 1
    assert summary.formal_bayes_factor is None
    assert summary.scientific_pass is False
    assert summary.evidence_class == "descriptive_topology_only"
    assert summary.output_checksum != ""
    assert summary.provenance_checksum != ""

    pair = summary.processed_pairs[0]
    assert pair["persistence_distance"] is not None
    assert pair["persistence_distance"] >= 0.0
    assert pair["delta_landscape_area"] is not None
    assert "h0" in pair["condition_a"]["persistence_interval_counts"]
    assert "h1" in pair["condition_a"]["persistence_interval_counts"]


def test_multiple_paired_subjects(tmp_path: Path):
    """Verifies processing of multiple empirical pairs with aggregate statistics."""
    f1a = _make_dummy_npy(tmp_path / "sub01_a.npy", seed=21)
    f1b = _make_dummy_npy(tmp_path / "sub01_b.npy", seed=22)
    f2a = _make_dummy_npy(tmp_path / "sub02_a.npy", seed=23)
    f2b = _make_dummy_npy(tmp_path / "sub02_b.npy", seed=24)

    manifest_p = _make_manifest_json(
        tmp_path / "manifest_multi.json",
        [
            (f1a, f1b, "awake", "sedated", False),
            (f2a, f2b, "awake", "sedated", False),
        ],
        min_pairs=2,
    )

    out = tmp_path / "out_multi"
    summary = execute_cohort_topology(manifest_p, out, window_samples=512)

    assert summary.execution_status == ExecutionStatus.DESCRIPTIVE_READY.value
    assert summary.pairs_processed == 2
    assert summary.empirical_pairs_count == 2
    assert (out / "cohort_topology_execution_summary.json").is_file()
    assert (out / "cohort_topology_pairs.csv").is_file()
    assert (out / "cohort_topology_windows.csv").is_file()

    emp_agg = summary.descriptive_aggregate["empirical"]
    assert emp_agg["pairs_count"] == 2
    assert emp_agg["delta_landscape_area"]["mean"] is not None
    assert emp_agg["persistence_distance"]["mean"] is not None


def test_missing_condition_and_file_recovery(tmp_path: Path):
    """Verifies that a missing file or condition in one pair is skipped while valid pairs succeed."""
    f1a = _make_dummy_npy(tmp_path / "sub01_a.npy", seed=31)
    f1b = _make_dummy_npy(tmp_path / "sub01_b.npy", seed=32)
    missing_file = tmp_path / "missing_recording.npy"
    f2b = _make_dummy_npy(tmp_path / "sub02_b.npy", seed=33)

    manifest_p = _make_manifest_json(
        tmp_path / "manifest_partial.json",
        [
            (f1a, f1b, "awake", "sedated", False),
            (missing_file, f2b, "awake", "sedated", False),
        ],
        min_pairs=1,
    )

    out = tmp_path / "out_partial"
    summary = execute_cohort_topology(manifest_p, out, window_samples=512)

    assert summary.pairs_processed == 1
    assert summary.pairs_skipped == 1
    assert len(summary.skipped_pairs) == 1
    assert "missing_recording" in summary.skipped_pairs[0]["reason"]


def test_missing_montage_coordinates_explicit_null(tmp_path: Path):
    """Verifies spatial_phase_charge is explicitly null when montage coordinates are missing."""
    f1a = _make_dummy_npy(tmp_path / "sub01_a.npy", channels=16, samples=1024)
    f1b = _make_dummy_npy(tmp_path / "sub01_b.npy", channels=16, samples=1024)

    manifest_p = _make_manifest_json(
        tmp_path / "manifest_nomontage.json",
        [(f1a, f1b, "awake", "sedated", False)],
        min_pairs=1,
    )

    out = tmp_path / "out_nomontage"
    summary = execute_cohort_topology(manifest_p, out, window_samples=512)

    pair = summary.processed_pairs[0]
    # In .npy without montage, spatial charge must be explicitly null
    assert pair["condition_a"]["spatial_phase_charge_summary"]["available"] is False
    assert pair["condition_a"]["spatial_phase_charge_summary"]["mean"] is None
    assert pair["condition_b"]["spatial_phase_charge_summary"]["available"] is False
    assert pair["condition_b"]["spatial_phase_charge_summary"]["mean"] is None


def test_synthetic_only_input_state(tmp_path: Path):
    """Verifies that synthetic-only cohort input produces SYNTHETIC_DEMO_ONLY state."""
    f_synth_a = _make_dummy_npy(tmp_path / "synth_a.npy")
    f_synth_b = _make_dummy_npy(tmp_path / "synth_b.npy")

    manifest_p = _make_manifest_json(
        tmp_path / "manifest_synth.json",
        [(f_synth_a, f_synth_b, "awake", "sedated", True)],
        min_pairs=1,
    )

    out = tmp_path / "out_synth"
    summary = execute_cohort_topology(manifest_p, out, window_samples=512)

    assert summary.execution_status == ExecutionStatus.SYNTHETIC_DEMO_ONLY.value
    assert summary.synthetic_pairs_count == 1
    assert summary.empirical_pairs_count == 0
    assert summary.scientific_pass is False


def test_bounded_memory_telemetry(tmp_path: Path):
    """Verifies bounded memory telemetry tracking without full cohort materialization."""
    f1a = _make_dummy_npy(tmp_path / "sub01_a.npy", samples=4000)
    f1b = _make_dummy_npy(tmp_path / "sub01_b.npy", samples=4000)

    manifest_p = _make_manifest_json(
        tmp_path / "manifest_mem.json",
        [(f1a, f1b, "awake", "sedated", False)],
        min_pairs=1,
    )

    out = tmp_path / "out_mem"
    summary = execute_cohort_topology(
        manifest_p,
        out,
        window_samples=500,
        max_windows=4,
        memory_telemetry=True,
    )

    assert summary.peak_memory_mb is not None
    assert summary.peak_memory_mb > 0.0
    assert "peak_mb" in summary.memory_telemetry
    assert summary.processed_pairs[0]["condition_a"]["windows_processed"] == 4


def test_deterministic_repeated_output_and_checksum(tmp_path: Path):
    """Verifies that two runs with the same seed yield identical output_checksum and metrics."""
    f1a = _make_dummy_npy(tmp_path / "sub01_a.npy", seed=50)
    f1b = _make_dummy_npy(tmp_path / "sub01_b.npy", seed=51)

    manifest_p = _make_manifest_json(
        tmp_path / "manifest_det.json",
        [(f1a, f1b, "awake", "sedated", False)],
        min_pairs=1,
    )

    out1 = tmp_path / "out1"
    out2 = tmp_path / "out2"

    sum1 = execute_cohort_topology(manifest_p, out1, window_samples=512, seed=42)
    sum2 = execute_cohort_topology(manifest_p, out2, window_samples=512, seed=42)

    assert sum1.output_checksum == sum2.output_checksum
    delta1 = sum1.processed_pairs[0]["delta_landscape_area"]
    delta2 = sum2.processed_pairs[0]["delta_landscape_area"]
    assert delta1 == delta2


def test_node_reordering_invariance(tmp_path: Path):
    """Verifies that reordering channels leaves persistent homology invariant."""
    channels = 8
    samples = 512
    rng = np.random.default_rng(77)
    data = rng.standard_normal((channels, samples))

    # Permutation of channels
    perm = rng.permutation(channels)
    data_perm = data[perm, :]

    m1 = compute_window_topology(data)
    m2 = compute_window_topology(data_perm)

    assert m1.filtration_beta1_max == m2.filtration_beta1_max
    assert np.isclose(m1.integrated_beta1_landscape_area, m2.integrated_beta1_landscape_area, atol=1e-6)
    assert m1.h0_intervals_count == m2.h0_intervals_count
    assert m1.h1_intervals_count == m2.h1_intervals_count


def test_graph_and_spatial_metric_separation():
    """Verifies graph beta-1 and spatial phase charge are strictly separate metrics."""
    channels = 4
    samples = 256
    data = np.zeros((channels, samples))
    for c in range(channels):
        data[c] = np.sin(np.linspace(0, 10, samples) + c * 0.5)

    # 1. Without montage coordinates -> spatial charge MUST be null
    m_no_montage = compute_window_topology(data, montage_coordinates=None)
    assert m_no_montage.spatial_phase_charge is None
    assert m_no_montage.spatial_charge_available is False
    assert isinstance(m_no_montage.filtration_beta1_max, int)

    # 2. With montage coordinates -> spatial charge is computed separately
    coords = np.array([
        [0.0, 1.0, 0.0],
        [1.0, 0.0, 0.0],
        [0.0, -1.0, 0.0],
        [-1.0, 0.0, 0.0],
    ])
    m_with_montage = compute_window_topology(data, montage_coordinates=coords)
    assert m_with_montage.spatial_charge_available is True
    assert m_with_montage.spatial_phase_charge is not None
    assert isinstance(m_with_montage.spatial_phase_charge, float)


def test_optional_backend_absence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Verifies MISSING_OPTIONAL_DEPENDENCY state when ripser is not importable."""
    import builtins
    real_import = builtins.__import__

    def mock_import(name, *args, **kwargs):
        if name == "ripser":
            raise ImportError("No module named 'ripser'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", mock_import)

    f1a = _make_dummy_npy(tmp_path / "sub01_a.npy")
    f1b = _make_dummy_npy(tmp_path / "sub01_b.npy")
    manifest = _make_manifest_json(
        tmp_path / "manifest.json",
        [(f1a, f1b, "awake", "sedated", False)],
        min_pairs=1,
    )

    out = tmp_path / "out_nodeps"
    summary = execute_cohort_topology(manifest, out, window_samples=512)

    assert summary.execution_status == ExecutionStatus.MISSING_OPTIONAL_DEPENDENCY.value
    assert any("ripser" in r for r in summary.refusal_reasons)
    assert summary.pairs_processed == 0


def test_no_network_execution(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Verifies that execution runs 100% locally with zero socket network connections."""
    def forbid_connect(self, *args, **kwargs):
        raise RuntimeError("Network connection forbidden during local execution")

    monkeypatch.setattr(socket.socket, "connect", forbid_connect)

    f1a = _make_dummy_npy(tmp_path / "sub01_a.npy")
    f1b = _make_dummy_npy(tmp_path / "sub01_b.npy")
    manifest = _make_manifest_json(
        tmp_path / "manifest_offline.json",
        [(f1a, f1b, "awake", "sedated", False)],
        min_pairs=1,
    )

    out = tmp_path / "out_offline"
    summary = execute_cohort_topology(manifest, out, window_samples=512)
    assert summary.execution_status == ExecutionStatus.DESCRIPTIVE_READY.value
    assert summary.pairs_processed == 1


def test_manifest_refusal_gates(tmp_path: Path):
    """Verifies refusal states: NO_DATA, INVALID_INPUT, INSUFFICIENT_PAIRED_SUBJECTS, INCOMPLETE_PROVENANCE."""
    out = tmp_path / "out_gates"

    # 1. NO_DATA
    m_no_data = tmp_path / "no_data.json"
    m_no_data.write_text(json.dumps({"status": "no_data", "paired_records": []}), encoding="utf-8")
    s1 = execute_cohort_topology(m_no_data, out)
    assert s1.execution_status == ExecutionStatus.NO_DATA.value

    # 2. INVALID_INPUT (bad json)
    m_bad = tmp_path / "bad.json"
    m_bad.write_text("{ unclosed", encoding="utf-8")
    s2 = execute_cohort_topology(m_bad, out)
    assert s2.execution_status == ExecutionStatus.INVALID_INPUT.value

    # 3. INSUFFICIENT_PAIRED_SUBJECTS
    f1a = _make_dummy_npy(tmp_path / "sub01_a.npy")
    f1b = _make_dummy_npy(tmp_path / "sub01_b.npy")
    m_insuf = _make_manifest_json(
        tmp_path / "insuf.json",
        [(f1a, f1b, "awake", "sedated", False)],
        status="insufficient_pairs",
        min_pairs=2,
    )
    s3 = execute_cohort_topology(m_insuf, out, allow_insufficient=False)
    assert s3.execution_status == ExecutionStatus.INSUFFICIENT_PAIRED_SUBJECTS.value

    # 4. INCOMPLETE_PROVENANCE
    m_prov = _make_manifest_json(
        tmp_path / "inc_prov.json",
        [(f1a, f1b, "awake", "sedated", False)],
        provenance_status="incomplete_provenance",
        min_pairs=1,
    )
    s4 = execute_cohort_topology(m_prov, out)
    assert s4.execution_status == ExecutionStatus.INCOMPLETE_PROVENANCE.value


def test_cli_runner_subprocesses(tmp_path: Path):
    """Verifies CLI runner scripts/run_cohort_topology.py in isolated subprocesses."""
    f1a = _make_dummy_npy(tmp_path / "sub01_a.npy")
    f1b = _make_dummy_npy(tmp_path / "sub01_b.npy")

    manifest_valid = _make_manifest_json(
        tmp_path / "manifest_cli.json",
        [(f1a, f1b, "awake", "sedated", False)],
        min_pairs=1,
    )

    out_cli = tmp_path / "out_cli"
    res = subprocess.run(
        [
            sys.executable,
            "scripts/run_cohort_topology.py",
            "--manifest",
            str(manifest_valid),
            "--output-dir",
            str(out_cli),
            "--window-samples",
            "512",
            "--channel-limit",
            "8",
            "--sample-limit",
            "1024",
        ],
        capture_output=True,
        text=True,
    )
    assert res.returncode == 0
    parsed = json.loads(res.stdout)
    assert parsed["execution_status"] == ExecutionStatus.DESCRIPTIVE_READY.value
    assert parsed["formal_bayes_factor"] is None
    assert parsed["scientific_pass"] is False
    assert parsed["evidence_class"] == "descriptive_topology_only"
    assert parsed["output_checksum"] != ""
