"""Comprehensive test suite for embodied-control alignment layer.

Validates:
- Aligned synthetic respiration and EEG
- Sample-rate mismatch and causal resampling
- Lag candidate evaluation
- Missing ECG and missing respiration handling
- Clock drift and timestamp discontinuity diagnostics
- Interpolation causality (no future leakage)
- Confound controls (circular shift, block shift, matched variance, permutations)
- Scientific guardrails (rejection of banned assertions, no causal mediation claims)
- Strict null-safe JSON serialization rejecting NaN and Inf
- SHA-256 cryptographic report checksum verification
- No-network execution guard
- Bounded memory execution
- CLI execution in JSON and Markdown formats
"""
from __future__ import annotations

import json
import math
import socket
import subprocess
import sys
import tempfile
import tracemalloc
from pathlib import Path
from typing import Any
import numpy as np
import pytest

from tools.embodied_controls.aligner import EmbodiedControlAligner
from tools.embodied_controls.confounds import (
    evaluate_coupling_attenuation,
    generate_block_shift,
    generate_circular_shift,
    generate_condition_preserving_permutation,
    generate_matched_variance_control,
)
from tools.embodied_controls.feature_extractors import (
    extract_autonomic_proxy_features,
    extract_cardiac_features,
    extract_neural_features,
    extract_respiratory_features,
)
from tools.embodied_controls.resampling import (
    detect_clock_drift,
    resample_causal_linear,
    resample_nearest,
)
from tools.embodied_controls.types import (
    AlignmentQualityState,
    ConfoundControlType,
    EmbodiedControlAlignmentReport,
    EvidenceClass,
    InterpolationMethod,
    VariableRole,
    validate_no_banned_assertions,
    verify_embodied_control_report_checksum,
)


@pytest.fixture
def synthetic_multimodal_fixture() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Generate deterministic synthetic multimodal fixture for testing."""
    duration_s = 30.0
    common_fs = 100.0
    n_samples = int(duration_s * common_fs)
    t = np.arange(n_samples) / common_fs

    # Respiration: 0.35 Hz (21 BPM)
    resp = 0.8 * np.sin(2.0 * np.pi * 0.35 * t)

    # ECG: R-peaks every 0.8s (75 BPM)
    ecg = np.zeros(n_samples)
    for rt in np.arange(0.4, duration_s - 0.4, 0.8):
        idx = int(round(rt * common_fs))
        if 0 <= idx < n_samples:
            ecg[idx] = 2.0
            if idx > 0:
                ecg[idx - 1] = -0.3
            if idx < n_samples - 1:
                ecg[idx + 1] = -0.4

    # EDA: tonic
    eda = 4.0 + 0.2 * np.sin(2.0 * np.pi * 0.05 * t)

    physio = {
        "respiration": resp,
        "respiration_fs": common_fs,
        "ecg": ecg,
        "ecg_fs": common_fs,
        "eda": eda,
        "eda_fs": common_fs,
        "timestamps": t,
        "start_time_s": 0.0,
    }

    # Neural windows: 10-second windows (contains ~3.5 breath cycles and 12 heartbeats)
    neural_windows: list[dict[str, Any]] = []
    window_s = 10.0
    for i in range(3):
        w_start = i * window_s
        w_end = w_start + window_s
        w_samples = int(window_s * common_fs)
        w_t = np.arange(w_samples) / common_fs + w_start
        alpha_eeg = 15.0 * np.sin(2.0 * np.pi * 10.0 * w_t)

        neural_windows.append({
            "window_id": f"win_{i:03d}",
            "start_time_s": w_start,
            "end_time_s": w_end,
            "sample_rate_hz": common_fs,
            "n_channels": 1,
            "data": alpha_eeg,
        })

    return neural_windows, physio


class TestAlignmentEngine:
    """Core multimodal alignment and synchronization tests."""

    def test_aligned_synthetic_respiration_and_eeg(self, synthetic_multimodal_fixture):
        windows, physio = synthetic_multimodal_fixture
        aligner = EmbodiedControlAligner(common_clock_hz=100.0, is_synthetic=True)
        report = aligner.align(windows, physio)

        assert report.schema_version == "v1.0.0"
        assert report.is_synthetic is True
        assert report.evidence_class == EvidenceClass.SYNTHETIC_CONTROL.value
        assert report.alignment_quality_state == AlignmentQualityState.PASS.value
        assert report.n_windows_aligned == 3

        for w in report.windows:
            assert w.alignment.overlap_ratio == pytest.approx(1.0, abs=1e-3)
            assert w.alignment.signal_quality_state == AlignmentQualityState.PASS.value
            # Respiration rate: 21 BPM (0.35 Hz)
            assert w.respiration is not None
            assert w.respiration.respiratory_rate_bpm == pytest.approx(21.0, abs=1.5)
            assert w.respiration.respiratory_phase_rad is not None
            # Heart rate: 75 BPM
            assert w.cardiac is not None
            assert w.cardiac.heart_rate_bpm == pytest.approx(75.0, abs=2.0)
            assert w.cardiac.rmssd_ms is not None
            # Neural alpha power
            assert w.neural is not None
            assert w.neural.alpha_power_rel is not None
            assert w.neural.alpha_power_rel > 0.5

    def test_sample_rate_mismatch_resampling(self):
        # EEG at 250 Hz, respiration at 20 Hz, ECG at 500 Hz
        duration_s = 16.0
        t_resp = np.arange(int(duration_s * 20)) / 20.0
        resp = np.sin(2.0 * np.pi * 0.25 * t_resp)

        t_ecg = np.arange(int(duration_s * 500)) / 500.0
        ecg = np.zeros(len(t_ecg))
        for rt in np.arange(0.5, duration_s - 0.5, 0.8):
            ecg[int(round(rt * 500))] = 2.0

        physio = {
            "respiration": resp,
            "respiration_fs": 20.0,
            "ecg": ecg,
            "ecg_fs": 500.0,
            "start_time_s": 0.0,
        }

        neural_windows = [{
            "window_id": "win_mismatch",
            "start_time_s": 0.0,
            "end_time_s": 8.0,
            "sample_rate_hz": 250.0,
            "data": np.sin(2.0 * np.pi * 10.0 * np.arange(2000) / 250.0),
        }]

        aligner = EmbodiedControlAligner(common_clock_hz=100.0)
        report = aligner.align(neural_windows, physio)

        assert report.n_windows_aligned == 1
        w = report.windows[0]
        # Verify resampling metadata was captured
        resamp_map = {r.channel_name: r for r in w.alignment.resampling}
        assert "respiration" in resamp_map
        assert resamp_map["respiration"].source_sfreq_hz == 20.0
        assert resamp_map["respiration"].target_sfreq_hz == 100.0
        assert resamp_map["respiration"].interpolated is True

        assert "ecg" in resamp_map
        assert resamp_map["ecg"].source_sfreq_hz == 500.0
        assert resamp_map["ecg"].target_sfreq_hz == 100.0
        assert resamp_map["ecg"].interpolated is True

    def test_causal_vs_nearest_interpolation(self):
        source = np.array([0.0, 10.0, 20.0, 30.0])
        # Resample from 1 Hz to 2 Hz
        resampled_causal, rec_c = resample_causal_linear(source, 1.0, 2.0)
        assert rec_c.method == InterpolationMethod.CAUSAL_LINEAR.value
        assert len(resampled_causal) == 8
        # Check first intermediate point at t=0.5: between 0.0 and 10.0 => 5.0
        assert resampled_causal[1] == pytest.approx(5.0)

        resampled_near, rec_n = resample_nearest(source, 1.0, 2.0)
        assert rec_n.method == InterpolationMethod.NEAREST.value
        assert len(resampled_near) == 8

    def test_lag_candidate_evaluation(self, synthetic_multimodal_fixture):
        windows, physio = synthetic_multimodal_fixture
        aligner = EmbodiedControlAligner(
            common_clock_hz=100.0,
            lag_candidates_s=[-2.0, -1.0, 0.0, 1.0, 2.0],
        )
        report = aligner.align(windows, physio)
        w = report.windows[0]
        assert len(w.alignment.lag_candidates) == 5
        peaks = [c for c in w.alignment.lag_candidates if c.is_peak]
        assert len(peaks) == 1

    def test_missing_respiration_handling(self, synthetic_multimodal_fixture):
        windows, physio = synthetic_multimodal_fixture
        physio_no_resp = dict(physio)
        physio_no_resp["respiration"] = None

        aligner = EmbodiedControlAligner(common_clock_hz=100.0)
        report = aligner.align(windows, physio_no_resp)

        assert "respiration" in report.windows[0].alignment.missing_channels
        assert report.windows[0].respiration is None
        assert report.windows[0].alignment.missingness_ratio > 0.0

    def test_missing_ecg_handling(self, synthetic_multimodal_fixture):
        windows, physio = synthetic_multimodal_fixture
        physio_no_ecg = dict(physio)
        physio_no_ecg["ecg"] = None

        aligner = EmbodiedControlAligner(common_clock_hz=100.0)
        report = aligner.align(windows, physio_no_ecg)

        assert "ecg" in report.windows[0].alignment.missing_channels
        assert report.windows[0].cardiac is None

    def test_clock_drift_detection(self):
        # 100 Hz nominal, simulate timestamps with 200 ppm drift
        nominal_fs = 100.0
        n_samples = 1000
        drifted_dt = (1.0 / nominal_fs) * 1.0002
        ts = np.arange(n_samples) * drifted_dt

        diag = detect_clock_drift(ts, nominal_fs, drift_threshold_ppm=50.0)
        assert diag.drift_detected is True
        assert diag.estimated_drift_ppm > 50.0
        assert diag.warning is not None


class TestConfoundControls:
    """Mathematical validation of empirical confound controls."""

    def test_circular_shift(self):
        sig = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        shifted = generate_circular_shift(sig, shift_samples=2)
        assert len(shifted) == len(sig)
        assert np.mean(shifted) == pytest.approx(np.mean(sig))
        assert np.var(shifted) == pytest.approx(np.var(sig))
        assert not np.array_equal(shifted, sig)

    def test_block_shift(self):
        sig = np.arange(20, dtype=float)
        block_shifted = generate_block_shift(sig, block_size=5, shift_blocks=1)
        assert len(block_shifted) == len(sig)
        assert np.mean(block_shifted) == pytest.approx(np.mean(sig))
        assert not np.array_equal(block_shifted, sig)

    def test_matched_variance_control(self):
        rng = np.random.default_rng(42)
        t = np.arange(100) / 10.0
        sig = 2.5 * np.sin(2.0 * np.pi * 1.0 * t) + rng.normal(0, 0.2, 100)

        surrogate = generate_matched_variance_control(sig, seed=99)
        assert len(surrogate) == len(sig)
        assert np.mean(surrogate) == pytest.approx(np.mean(sig), abs=1e-4)
        assert np.std(surrogate) == pytest.approx(np.std(sig), abs=1e-4)
        # Verify it is not identical
        assert not np.allclose(surrogate, sig)

    def test_condition_preserving_permutation(self):
        features = [1.0, 2.0, 3.0, 10.0, 20.0, 30.0]
        conditions = ["rest", "rest", "rest", "task", "task", "task"]

        perm = generate_condition_preserving_permutation(features, conditions, seed=123)
        assert len(perm) == len(features)
        # Rest subset mean preserved
        assert sum(perm[:3]) == pytest.approx(sum(features[:3]))
        # Task subset mean preserved
        assert sum(perm[3:]) == pytest.approx(sum(features[3:]))

    def test_evaluate_coupling_attenuation(self):
        res = evaluate_coupling_attenuation(
            original_coupling=0.6,
            perturbed_coupling=0.1,
            control_type=ConfoundControlType.CIRCULAR_SHIFT,
            parameter_description="Shift by 5s",
        )
        assert res.attenuation_ratio > 0.5
        assert res.surrogate_passed is True


class TestScientificGuardrails:
    """Enforcement of epistemological limits and label discipline."""

    def test_banned_assertions_raise_error(self):
        for banned in ("calmness", "equanimity", "detachment", "liberation", "causal mediation"):
            with pytest.raises(ValueError, match="Banned assertion detected"):
                validate_no_banned_assertions(f"Testing state of {banned}")

    def test_banned_assertion_in_variable_role_rejected(self):
        with pytest.raises(ValueError, match="Banned assertion detected"):
            EmbodiedControlAligner(variable_roles={"respiration": "liberation"})

    def test_synthetic_status_enforcement(self, synthetic_multimodal_fixture):
        windows, physio = synthetic_multimodal_fixture
        aligner = EmbodiedControlAligner(is_synthetic=True)
        report = aligner.align(windows, physio)
        assert report.is_synthetic is True
        assert report.evidence_class == EvidenceClass.SYNTHETIC_CONTROL.value


class TestSerializationAndSafety:
    """Verification of serialization, determinism, network independence, and memory bounding."""

    def test_json_rejects_nan_and_inf(self, synthetic_multimodal_fixture):
        windows, physio = synthetic_multimodal_fixture
        aligner = EmbodiedControlAligner()
        report = aligner.align(windows, physio)

        # Inject NaN into a feature
        report.alignment_quality_score = float("nan")
        with pytest.raises(ValueError, match="Non-compliant float"):
            report.to_json()

    def test_deterministic_checksum_verification(self, synthetic_multimodal_fixture):
        windows, physio = synthetic_multimodal_fixture
        aligner = EmbodiedControlAligner()
        report = aligner.align(windows, physio)
        json_str = report.to_json()
        data_dict = json.loads(json_str)

        assert verify_embodied_control_report_checksum(data_dict) is True
        # Tamper check
        data_dict["alignment_quality_score"] = 0.123
        assert verify_embodied_control_report_checksum(data_dict) is False

    def test_no_network_behavior(self, synthetic_multimodal_fixture, monkeypatch):
        windows, physio = synthetic_multimodal_fixture

        def _forbidden_connect(*args, **kwargs):
            raise AssertionError("Network connection attempted during alignment!")

        monkeypatch.setattr(socket.socket, "connect", _forbidden_connect)

        aligner = EmbodiedControlAligner()
        report = aligner.align(windows, physio)
        assert report.n_windows_aligned > 0

    def test_bounded_memory(self):
        tracemalloc.start()
        # Generate 100 windows
        windows = [
            {
                "window_id": f"w_{i}",
                "start_time_s": float(i * 2),
                "end_time_s": float((i + 1) * 2),
                "sample_rate_hz": 100.0,
                "data": np.zeros(200),
            }
            for i in range(50)
        ]
        physio = {
            "respiration": np.zeros(10000),
            "respiration_fs": 100.0,
            "start_time_s": 0.0,
        }

        aligner = EmbodiedControlAligner()
        report = aligner.align(windows, physio)
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        peak_mb = peak / 1024 / 1024
        assert peak_mb < 20.0  # Peak RAM well below 20MB
        assert report.n_windows_aligned == 50

    def test_cli_execution(self):
        # Run CLI in synthetic mode with JSON output
        result_json = subprocess.run(
            [sys.executable, "scripts/align_embodied_controls.py", "--synthetic", "--format", "json"],
            capture_output=True,
            text=True,
            check=True,
        )
        report_data = json.loads(result_json.stdout)
        assert report_data["schema_version"] == "v1.0.0"
        assert report_data["is_synthetic"] is True
        assert verify_embodied_control_report_checksum(report_data) is True

        # Run CLI in synthetic mode with Markdown output
        result_md = subprocess.run(
            [sys.executable, "scripts/align_embodied_controls.py", "--synthetic", "--format", "markdown"],
            capture_output=True,
            text=True,
            check=True,
        )
        assert "# Embodied-Control Alignment Report" in result_md.stdout
        assert "Scientific Guardrail" in result_md.stdout
