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
