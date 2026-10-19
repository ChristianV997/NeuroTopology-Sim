"""Tests for negative replay cases: reordered channels, unit mismatches, missing timing, non-finite values, and dependency absence."""
from __future__ import annotations

import numpy as np
import pytest

from tools.synthetic_pipeline_replay.contracts import (
    BoundaryStatus,
    ReplayStatus,
)
from tools.synthetic_pipeline_replay.runner import (
    SyntheticPipelineReplayRunner,
)


class TestReplayNegativeCases:
    """Verify that inter-stage mismatches are detected without silent coercion."""

    def test_reordered_channels_fails_boundary(self):
        """Channels reordered between stages must be rejected; no silent permutation is permitted."""
        runner = SyntheticPipelineReplayRunner(seed=42)
        # Permute channel ordering at Stage 1 output: Fp2 before Fp1
        perturbations = {
            "stage_1": {
                "channel_ordering": ["Fp2", "Fp1", "C3", "C4"],
            }
        }
        report = runner.run_replay(stage_perturbations=perturbations)

        assert report.status == ReplayStatus.INCOMPATIBLE.value
        b1 = report.boundaries[0]
        assert b1.status == BoundaryStatus.INCOMPATIBLE.value
        assert any("permuting channels is forbidden" in m for m in b1.mismatches)

    def test_mismatched_units_fails_boundary(self):
        """Uncalibrated unit changes (e.g. 'V' instead of 'uV') must fail closed without implicit scaling."""
        runner = SyntheticPipelineReplayRunner(seed=42)
        perturbations = {
            "stage_1": {
                "observed_units": "V",
            }
        }
        report = runner.run_replay(stage_perturbations=perturbations)

        assert report.status == ReplayStatus.INCOMPATIBLE.value
        b1 = report.boundaries[0]
        assert b1.status == BoundaryStatus.INCOMPATIBLE.value
        assert any("Unit mismatch: expected 'uV', observed 'V'" in m for m in b1.mismatches)

    def test_missing_time_metadata_fails_boundary(self):
        """Missing sampling rate or timing metadata must yield missing_required_field, not implicit defaults."""
        runner = SyntheticPipelineReplayRunner(seed=42)
        perturbations = {
            "stage_1": {
                "sampling_rate_hz": None,
            }
        }
        report = runner.run_replay(stage_perturbations=perturbations)

        assert report.status == ReplayStatus.INCONCLUSIVE.value
        b1 = report.boundaries[0]
        assert b1.status == BoundaryStatus.MISSING_REQUIRED_FIELD.value
        assert "sampling_rate_hz" in b1.missing_fields

    def test_changed_feature_dimension_fails_boundary(self):
        """Unexpected array dimensions must be rejected without silent reshaping."""
        runner = SyntheticPipelineReplayRunner(seed=42)
        perturbations = {
            "stage_2": {
                "observed_shape": [4, 300],  # Expected 250
            }
        }
        report = runner.run_replay(stage_perturbations=perturbations)

        assert report.status == ReplayStatus.INCOMPATIBLE.value
        b2 = report.boundaries[1]
        assert b2.status == BoundaryStatus.INCOMPATIBLE.value
        assert any("Shape mismatch" in m for m in b2.mismatches)

    def test_non_finite_values_fails_boundary(self):
        """NaN or Inf in data payload must be rejected fail-closed; no silent zero-imputation."""
        runner = SyntheticPipelineReplayRunner(seed=42)
        corrupted = np.zeros((4, 500))
        corrupted[0, 50] = np.nan
        corrupted[1, 100] = np.inf

        perturbations = {
            "stage_1": {
                "data": corrupted,
            }
        }
        report = runner.run_replay(stage_perturbations=perturbations)

        assert report.status == ReplayStatus.INCOMPATIBLE.value
        b1 = report.boundaries[0]
        assert b1.status == BoundaryStatus.INCOMPATIBLE.value
        assert any("contains non-finite values" in m for m in b1.mismatches)

    def test_stale_schema_version_fails_boundary(self):
        """Stale or deprecated schema version must trigger incompatibility."""
        runner = SyntheticPipelineReplayRunner(seed=42)
        perturbations = {
            "stage_1": {
                "schema_version": "NeuroTopologySim.SignalChunk.v0_legacy_deprecated",
            }
        }
        report = runner.run_replay(stage_perturbations=perturbations)

        assert report.status == ReplayStatus.INCOMPATIBLE.value
        b1 = report.boundaries[0]
        assert b1.status == BoundaryStatus.INCOMPATIBLE.value
        assert any("Stale/deprecated schema version observed" in m for m in b1.mismatches)

    def test_unavailable_optional_dependency_blocks_replay(self):
        """When an optional backend dependency is missing, status must be not_comparable/blocked."""
        runner = SyntheticPipelineReplayRunner(seed=42)
        # Simulate ripser missing
        report = runner.run_replay(dependency_overrides={"ripser": False})

        assert report.status == ReplayStatus.BLOCKED.value
        b3 = report.boundaries[2]
        assert b3.status == BoundaryStatus.NOT_COMPARABLE.value
        assert any("Required optional dependency 'ripser' is not available" in m for m in b3.mismatches)
        # Downstream Stage 4 must NOT execute when Stage 3->4 boundary is not comparable
        assert "stage_4_topology_summary" not in report.stages_executed

    def test_incompatible_stages_fails_boundary(self):
        """Passing an unexpected artifact kind or feature family must fail closed."""
        runner = SyntheticPipelineReplayRunner(seed=42)
        perturbations = {
            "stage_3": {
                "feature_family": "directed_hypergraph",  # Expected pairwise_fc
            }
        }
        report = runner.run_replay(stage_perturbations=perturbations)

        assert report.status == ReplayStatus.INCOMPATIBLE.value
        b3 = report.boundaries[2]
        assert b3.status == BoundaryStatus.INCOMPATIBLE.value
        assert any("Incompatible feature family" in m for m in b3.mismatches)

    def test_contradictory_coordinates_fails_boundary(self):
        """Montage coordinate count conflicting with channel count must be rejected."""
        runner = SyntheticPipelineReplayRunner(seed=42)
        # 4 channels, but coordinate array only has 2 rows
        perturbations = {
            "stage_1": {
                "montage_coordinates": [[0.0, 1.0, 0.0], [0.0, 1.0, 0.0]],
            }
        }
        report = runner.run_replay(stage_perturbations=perturbations)

        assert report.status == ReplayStatus.INCOMPATIBLE.value
        b1 = report.boundaries[0]
        assert b1.status == BoundaryStatus.INCOMPATIBLE.value
        assert any("Coordinate channel count (2) does not match" in m for m in b1.mismatches)

    def test_absent_timestamps_fails_boundary(self):
        """Absent timestamps on a time-series contract must yield missing_required_field and halt downstream execution."""
        runner = SyntheticPipelineReplayRunner(seed=42)
        perturbations = {
            "stage_1": {
                "timestamps": None,
            }
        }
        report = runner.run_replay(stage_perturbations=perturbations)

        assert report.status == ReplayStatus.INCONCLUSIVE.value
        b1 = report.boundaries[0]
        assert b1.status == BoundaryStatus.MISSING_REQUIRED_FIELD.value
        assert "timestamps" in b1.missing_fields
        assert any("requires timestamps, but timestamps are absent" in m for m in b1.mismatches)
        # Downstream Stage 2 must not execute when timestamps are absent
        assert "stage_2_preprocessing" not in report.stages_executed

    def test_malformed_timestamps_non_monotonic_fails_boundary(self):
        """Timestamps that are not strictly monotonic must be rejected as incompatible."""
        runner = SyntheticPipelineReplayRunner(seed=42)
        bad_ts = np.linspace(0.0, 2.0, 500)
        bad_ts[250] = bad_ts[249]  # Flat non-increasing step
        perturbations = {
            "stage_1": {
                "timestamps": bad_ts,
            }
        }
        report = runner.run_replay(stage_perturbations=perturbations)

        assert report.status == ReplayStatus.INCOMPATIBLE.value
        b1 = report.boundaries[0]
        assert b1.status == BoundaryStatus.INCOMPATIBLE.value
        assert any("not strictly monotonically increasing" in m for m in b1.mismatches)

    def test_malformed_timestamps_non_finite_fails_boundary(self):
        """Timestamps with NaN or Inf must be rejected as incompatible."""
        runner = SyntheticPipelineReplayRunner(seed=42)
        bad_ts = np.linspace(0.0, 2.0, 500)
        bad_ts[10] = np.nan
        perturbations = {
            "stage_1": {
                "timestamps": bad_ts,
            }
        }
        report = runner.run_replay(stage_perturbations=perturbations)

        assert report.status == ReplayStatus.INCOMPATIBLE.value
        b1 = report.boundaries[0]
        assert b1.status == BoundaryStatus.INCOMPATIBLE.value
        assert any("contain non-finite values" in m for m in b1.mismatches)

    def test_malformed_timestamps_wrong_shape_fails_boundary(self):
        """Timestamps with ndim != 1 must be rejected as incompatible."""
        runner = SyntheticPipelineReplayRunner(seed=42)
        bad_ts = np.linspace(0.0, 2.0, 500).reshape((2, 250))
        perturbations = {
            "stage_1": {
                "timestamps": bad_ts,
            }
        }
        report = runner.run_replay(stage_perturbations=perturbations)

        assert report.status == ReplayStatus.INCOMPATIBLE.value
        b1 = report.boundaries[0]
        assert b1.status == BoundaryStatus.INCOMPATIBLE.value
        assert any("must be 1D" in m for m in b1.mismatches)

    def test_malformed_timestamps_count_mismatch_fails_boundary(self):
        """Timestamp length not matching sample_count must be rejected as incompatible."""
        runner = SyntheticPipelineReplayRunner(seed=42)
        # Sample count is 500, but supply 450 timestamps
        bad_ts = np.linspace(0.0, 1.8, 450)
        perturbations = {
            "stage_1": {
                "timestamps": bad_ts,
            }
        }
        report = runner.run_replay(stage_perturbations=perturbations)

        assert report.status == ReplayStatus.INCOMPATIBLE.value
        b1 = report.boundaries[0]
        assert b1.status == BoundaryStatus.INCOMPATIBLE.value
        assert any("timestamp count (450) does not match sample count (500)" in m for m in b1.mismatches)

    def test_serializer_rejects_nan_inf_fail_closed(self):
        """Serializer must strictly raise ValueError on NaN/Inf, never silently coerce to null."""
        from tools.synthetic_pipeline_replay.contracts import safe_json_dict

        # Dict with NaN
        with pytest.raises(ValueError, match="Non-finite float value"):
            safe_json_dict({"metric": float("nan")})

        # List with Inf
        with pytest.raises(ValueError, match="Non-finite float value"):
            safe_json_dict([1.0, 2.0, float("inf")])

        # Numpy array with NaN
        with pytest.raises(ValueError, match="Non-finite float value in numpy array"):
            safe_json_dict(np.array([1.0, np.nan, 3.0]))

        # Numpy scalar with Inf
        with pytest.raises(ValueError, match="Non-finite float value"):
            safe_json_dict(np.float64("inf"))
