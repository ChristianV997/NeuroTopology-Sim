"""Tests for synthetic pipeline replay harness: valid execution, determinism, and serialization."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.synthetic_pipeline_replay.contracts import (
    BoundaryStatus,
    ReplayStatus,
)
from tools.synthetic_pipeline_replay.runner import (
    SyntheticPipelineReplayRunner,
)


class TestSyntheticPipelineReplayHarness:
    """Test full pipeline replay on valid synthetic signals."""

    def test_valid_synthetic_replay_succeeds(self):
        """Verify that a valid synthetic pipeline runs through all 4 stages with compatible boundaries."""
        runner = SyntheticPipelineReplayRunner(
            channels=("Fp1", "Fp2", "C3", "C4"),
            sfreq_hz=250.0,
            duration_s=2.0,
            seed=42,
        )
        report = runner.run_replay()

        assert report.status == ReplayStatus.COMPATIBLE.value
        assert report.total_boundaries == 3
        assert report.compatible_boundaries == 3
        assert report.incompatible_boundaries == 0

        # Verify all boundaries are compatible
        for boundary in report.boundaries:
            assert boundary.status == BoundaryStatus.COMPATIBLE.value
            assert len(boundary.mismatches) == 0
            assert len(boundary.missing_fields) == 0

        # Verify all 4 stages executed
        assert report.stages_executed == [
            "stage_1_signal_generation",
            "stage_2_preprocessing",
            "stage_3_feature_extraction",
            "stage_4_topology_summary",
        ]

    def test_replay_is_strictly_deterministic(self):
        """Verify that two replay runs with identical seeds produce bit-for-bit identical boundary outputs."""
        runner1 = SyntheticPipelineReplayRunner(seed=12345)
        report1 = runner1.run_replay()

        runner2 = SyntheticPipelineReplayRunner(seed=12345)
        report2 = runner2.run_replay()

        assert report1.status == report2.status
        assert report1.compatible_boundaries == report2.compatible_boundaries
        assert len(report1.boundaries) == len(report2.boundaries)

        for b1, b2 in zip(report1.boundaries, report2.boundaries):
            assert b1.boundary_id == b2.boundary_id
            assert b1.status == b2.status
            assert b1.expected_contract == b2.expected_contract
            assert b1.observed_contract == b2.observed_contract

    def test_replay_report_json_serialization(self, tmp_path: Path):
        """Verify that replay report serializes to valid, finite JSON."""
        runner = SyntheticPipelineReplayRunner(seed=42)
        report = runner.run_replay()

        json_str = report.to_json()
        out_file = tmp_path / "test_report.json"
        out_file.write_text(json_str, encoding="utf-8")

        loaded = json.loads(out_file.read_text(encoding="utf-8"))
        assert loaded["status"] == ReplayStatus.COMPATIBLE.value
        assert "disclaimer" in loaded
        assert "engineering check and does not constitute scientific validity" in loaded["disclaimer"]
        assert len(loaded["boundaries"]) == 3

    def test_psd_one_sided_scaling_and_parseval_conservation(self):
        """Verify that one-sided PSD doubles interior bins and exactly conserves discrete Parseval power."""
        import numpy as np
        from tools.synthetic_pipeline_replay.stages import FeatureExtractionStage

        # Test both even and odd sample lengths
        for n_samples in (250, 251):
            sfreq = 250.0
            t = np.arange(n_samples) / sfreq
            # Synthetic multichannel test signal: carrier + harmonic + DC offset
            data = np.stack([
                15.0 * np.cos(2.0 * np.pi * 12.0 * t) + 5.0,
                8.0 * np.sin(2.0 * np.pi * 30.0 * t),
            ])
            stage_input = {
                "data": data,
                "sampling_rate_hz": sfreq,
                "channel_ordering": ["Ch1", "Ch2"],
                "duration_s": n_samples / sfreq,
                "coordinate_status": "missing",
            }

            stage = FeatureExtractionStage()
            output = stage.execute(stage_input)
            psd_record = output["psd_record"]
            psd_matrix = np.asarray(psd_record.values)
            delta_f = sfreq / n_samples

            # Discrete Parseval integral: sum(P[k]) * delta_f == (1 / N) * sum(x[n]^2)
            discrete_energy_integral = np.sum(psd_matrix, axis=1) * delta_f
            time_domain_power = np.mean(data ** 2, axis=1)

            np.testing.assert_allclose(
                discrete_energy_integral,
                time_domain_power,
                rtol=1e-10,
                atol=1e-12,
                err_msg=f"Parseval power conservation violated for n_samples={n_samples}",
            )

            # Verify unscaled DC bin vs expected (X[0]^2 / (fs * N))
            raw_fft = np.fft.rfft(data, axis=1)
            raw_dc = (np.abs(raw_fft[:, 0]) ** 2) / (sfreq * n_samples)
            np.testing.assert_allclose(psd_matrix[:, 0], raw_dc, rtol=1e-12)

            # If even, verify unscaled Nyquist bin
            if n_samples % 2 == 0:
                raw_nyq = (np.abs(raw_fft[:, -1]) ** 2) / (sfreq * n_samples)
                np.testing.assert_allclose(psd_matrix[:, -1], raw_nyq, rtol=1e-12)

            # Verify interior bins are scaled by exactly 2.0
            interior_end = (n_samples // 2) if n_samples % 2 == 0 else (n_samples + 1) // 2
            raw_interior = 2.0 * ((np.abs(raw_fft[:, 1:interior_end]) ** 2) / (sfreq * n_samples))
            np.testing.assert_allclose(
                psd_matrix[:, 1:interior_end],
                raw_interior,
                rtol=1e-12,
            )

    def test_topology_summary_persistence_intervals_and_thresholded_betti(self):
        """Verify persistence-interval counts and thresholded Betti number evaluation."""
        import numpy as np
        from tools.synthetic_pipeline_replay.stages import TopologySummaryStage

        # Symmetric mock connectivity
        plv = np.array([
            [0.0, 0.8, 0.2, 0.1],
            [0.8, 0.0, 0.7, 0.2],
            [0.2, 0.7, 0.0, 0.9],
            [0.1, 0.2, 0.9, 0.0],
        ])
        stage_input = {
            "pairwise_fc_matrix": plv,
            "channel_ordering": ["Fp1", "Fp2", "C3", "C4"],
        }

        # 1. Without threshold: reports persistence intervals, betti status is not_evaluated
        stage_no_thresh = TopologySummaryStage()
        out_no_thresh = stage_no_thresh.execute(stage_input)
        assert "persistence_interval_count_h0" in out_no_thresh
        assert "persistence_interval_count_h1" in out_no_thresh
        assert out_no_thresh["betti_numbers_at_threshold"] is None
        assert out_no_thresh["betti_number_status"] == "not_evaluated_no_declared_threshold"
        assert out_no_thresh["persistence_interval_count_h0"] == 4  # 4 vertices

        # 2. With threshold: evaluates genuine Betti numbers
        stage_thresh = TopologySummaryStage(filtration_threshold=0.25)
        out_thresh = stage_thresh.execute(stage_input)
        assert out_thresh["betti_number_status"] == "evaluated_at_declared_threshold"
        betti = out_thresh["betti_numbers_at_threshold"]
        assert betti is not None
        assert betti["threshold_epsilon"] == 0.25
        assert isinstance(betti["betti_0"], int)
        assert isinstance(betti["betti_1"], int)

    def test_seed_variation_produces_distinct_signals_deterministically(self):
        """Verify that different seeds produce differing synthetic data, but identical seeds match bit-for-bit."""
        import numpy as np

        runner_a = SyntheticPipelineReplayRunner(seed=100)
        report_a = runner_a.run_replay()

        runner_a_repeat = SyntheticPipelineReplayRunner(seed=100)
        report_a_repeat = runner_a_repeat.run_replay()

        runner_b = SyntheticPipelineReplayRunner(seed=200)
        report_b = runner_b.run_replay()

        # Both runs succeed
        assert report_a.status == ReplayStatus.COMPATIBLE.value
        assert report_b.status == ReplayStatus.COMPATIBLE.value

        # Observed contracts for seed 100 match bit-for-bit
        assert report_a.boundaries[0].observed_contract == report_a_repeat.boundaries[0].observed_contract

    def test_harness_is_strictly_offline_zero_socket_calls(self, monkeypatch):
        """Verify that the harness executes completely offline without opening network sockets or calling APIs."""
        import socket

        def forbidden_connect(*args, **kwargs):
            raise RuntimeError("CRITICAL: Network connection attempted in offline replay harness!")

        monkeypatch.setattr(socket.socket, "connect", forbidden_connect)

        runner = SyntheticPipelineReplayRunner(seed=42)
        report = runner.run_replay()

        assert report.status == ReplayStatus.COMPATIBLE.value
        assert report.compatible_boundaries == 3

    def test_cli_main_exit_codes_and_path_containment(self, tmp_path: Path):
        """Verify CLI execution via main(), output writing, and deterministic exit codes."""
        from tools.synthetic_pipeline_replay.contracts import ReplayExitCode
        from tools.synthetic_pipeline_replay.runner import main

        out_file = tmp_path / "cli_report.json"
        code = main([
            "--output", str(out_file),
            "--seed", "42",
            "--duration", "1.5",
            "--sfreq", "250.0",
            "--channels", "Fp1", "Fp2", "C3", "C4",
            "--quiet",
        ])

        assert code == ReplayExitCode.COMPATIBLE.value
        assert out_file.exists()

        loaded = json.loads(out_file.read_text(encoding="utf-8"))
        assert loaded["status"] == "compatible"
        assert loaded["compatible_boundaries"] == 3
