"""Wires `analysis/eeg_topology/the_well_active_matter_validation.py`'s
offline schema-faithful ground-truth check into pytest/CI.

Found during a repo-wide audit: `_synthetic_schema_faithful_check` is a real,
well-constructed planted-defect-pair ground-truth check (net charge should
recover to ~0 for a known +/- defect pair), but before this file it was only
reachable by manually running
`python -m analysis.eeg_topology.the_well_active_matter_validation --synthetic-check`
-- no test imported it and no CI workflow ran it, so a regression in the
director-angle formula or charge-summation logic would go undetected.
"""
from __future__ import annotations

import pytest

from analysis.eeg_topology.the_well_active_matter_validation import (
    _synthetic_schema_faithful_check,
    defect_charges_over_time,
    director_from_D_tensor,
)


def test_synthetic_schema_faithful_check_recovers_zero_net_charge():
    """A planted +1/2, -1/2 defect pair must net to ~0 total charge -- the
    documented, physically-expected case for a closed/periodic domain."""
    result = _synthetic_schema_faithful_check(n_frames=4, grid=128)
    assert result["provenance"] == "synthetic_proxy"
    assert result["mean_abs_net_charge"] < 0.5


def test_synthetic_schema_faithful_check_output_shape():
    result = _synthetic_schema_faithful_check(n_frames=5, grid=64)
    assert len(result["net_charges_per_frame"]) == 5
    assert result["n_frames"] == 5
    assert result["grid"] == 64


def test_synthetic_schema_faithful_check_deterministic_given_seed():
    r1 = _synthetic_schema_faithful_check(n_frames=3, grid=64, seed=1)
    r2 = _synthetic_schema_faithful_check(n_frames=3, grid=64, seed=1)
    assert r1["net_charges_per_frame"] == r2["net_charges_per_frame"]


def test_director_from_D_tensor_matches_standard_formula():
    import numpy as np

    D_xx = np.array([[1.0, 0.0]])
    D_xy = np.array([[0.0, 1.0]])
    D_yy = np.array([[-1.0, 0.0]])
    theta = director_from_D_tensor(D_xx, D_xy, D_yy)
    expected = 0.5 * np.arctan2(2.0 * D_xy, D_xx - D_yy)
    np.testing.assert_array_equal(theta, expected)


def test_defect_charges_over_time_matches_frame_count():
    import numpy as np

    T, H, W = 3, 8, 8
    D_xx = np.ones((T, H, W))
    D_xy = np.zeros((T, H, W))
    D_yy = np.zeros((T, H, W))
    charges = defect_charges_over_time(D_xx, D_xy, D_yy)
    assert len(charges) == T
