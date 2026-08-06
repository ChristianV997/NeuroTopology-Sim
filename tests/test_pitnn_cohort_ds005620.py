"""Offline tests for the ds005620 PITNN cohort streaming tool.

Every test here runs without network or MNE: they cover the pure decision logic
(recording pairing, byte-range arithmetic, PLV identity, summary aggregation) that
determines whether the cohort run fetches the right bytes and compares the right
recordings.
"""
from __future__ import annotations

import numpy as np
import pytest

from tools.stream_pitnn_cohort_ds005620 import (
    _condition_summary,
    _eeg_prefix_bytes,
    _plv_matrix,
    h1_cycle_channel_locations,
    list_recording_keys,
    spatial_defect_snapshot,
)

_HEADER = (
    "Brain Vision Data Exchange Header File Version 1.0\n"
    "[Common Infos]\n"
    "DataFormat=BINARY\n"
    "DataOrientation=MULTIPLEXED\n"
    "NumberOfChannels=65\n"
    "SamplingInterval=200.0\n"
    "[Binary Infos]\n"
    "BinaryFormat=IEEE_FLOAT_32\n"
)


class _FakePaginator:
    def __init__(self, keys: list[str]) -> None:
        self._keys = keys

    def paginate(self, **_kwargs):
        yield {"Contents": [{"Key": k, "Size": 1} for k in self._keys]}


class _FakeClient:
    def __init__(self, keys: list[str]) -> None:
        self._keys = keys

    def get_paginator(self, _name: str) -> _FakePaginator:
        return _FakePaginator(self._keys)


def _keys(subject: str) -> list[str]:
    base = f"ds005620/{subject}/eeg/{subject}"
    return [
        f"{base}_task-awake_acq-EC_eeg.vhdr",
        f"{base}_task-awake_acq-EO_eeg.vhdr",
        f"{base}_task-awake_acq-tms_eeg.vhdr",
        f"{base}_task-sed_acq-rest_run-2_eeg.vhdr",
        f"{base}_task-sed_acq-rest_run-1_eeg.vhdr",
        f"{base}_task-sed2_acq-rest_run-1_eeg.vhdr",
    ]


def test_pairing_prefers_eyes_closed_awake_and_lowest_sed_run() -> None:
    """Eyes-closed rest is the awake counterpart; sedation uses the first run."""
    pairs = list_recording_keys(_FakeClient(_keys("sub-1010")))
    assert set(pairs) == {"sub-1010"}
    assert pairs["sub-1010"]["awake"].endswith("task-awake_acq-EC_eeg.vhdr")
    assert pairs["sub-1010"]["sedated"].endswith("task-sed_acq-rest_run-1_eeg.vhdr")


def test_pairing_excludes_tms_acquisition() -> None:
    """TMS-evoked recordings are a different regime and must never be the awake side."""
    pairs = list_recording_keys(_FakeClient(_keys("sub-1010")))
    assert "acq-tms" not in pairs["sub-1010"]["awake"]


def test_pairing_falls_back_to_sed2_when_sed_absent() -> None:
    keys = [k for k in _keys("sub-1016") if "task-sed_acq" not in k]
    pairs = list_recording_keys(_FakeClient(keys))
    assert pairs["sub-1016"]["sedated"].endswith("task-sed2_acq-rest_run-1_eeg.vhdr")


def test_subject_without_sedation_is_dropped_not_substituted() -> None:
    """sub-1037 really has zero sedation recordings; the cohort must lose it, not fake it."""
    keys = [k for k in _keys("sub-1037") if "task-sed" not in k]
    assert list_recording_keys(_FakeClient(keys)) == {}


def test_subject_without_awake_is_dropped() -> None:
    keys = [k for k in _keys("sub-9999") if "task-awake" not in k]
    assert list_recording_keys(_FakeClient(keys)) == {}


def test_eeg_prefix_bytes_lands_on_whole_sample_boundary() -> None:
    """A truncated .eeg is only a valid recording if it holds whole samples."""
    want = _eeg_prefix_bytes(_HEADER, duration_seconds=40.0, full_size=10**9)
    # 40 s at 200 us interval = 200_000 samples; 65 channels x 4 bytes each.
    assert want == 200_000 * 65 * 4
    assert want % (65 * 4) == 0


def test_eeg_prefix_bytes_never_exceeds_object_size() -> None:
    small = 1234 * 65 * 4
    assert _eeg_prefix_bytes(_HEADER, duration_seconds=10**6, full_size=small) == small


def test_eeg_prefix_bytes_handles_int16_format() -> None:
    header = _HEADER.replace("IEEE_FLOAT_32", "INT_16")
    assert _eeg_prefix_bytes(header, duration_seconds=1.0, full_size=10**9) == 5000 * 65 * 2


def test_plv_matrix_matches_naive_definition() -> None:
    """The (z @ z^H)/N identity must equal the explicit pairwise-difference mean."""
    rng = np.random.default_rng(0)
    phase = rng.uniform(-np.pi, np.pi, size=(9, 400))
    naive = np.abs(np.mean(np.exp(1j * (phase[:, None, :] - phase[None, :, :])), axis=2))
    np.fill_diagonal(naive, 0.0)
    np.testing.assert_allclose(_plv_matrix(phase), (naive + naive.T) / 2, atol=1e-12)


def test_plv_matrix_is_symmetric_and_bounded() -> None:
    rng = np.random.default_rng(1)
    plv = _plv_matrix(rng.uniform(-np.pi, np.pi, size=(12, 256)))
    np.testing.assert_allclose(plv, plv.T, atol=1e-12)
    assert plv.min() >= 0.0 and plv.max() <= 1.0
    assert np.allclose(np.diag(plv), 0.0)


def test_plv_of_identical_phases_is_one_offdiagonal() -> None:
    phase = np.tile(np.linspace(0.0, 8.0, 300), (5, 1))
    plv = _plv_matrix(phase)
    off = ~np.eye(5, dtype=bool)
    np.testing.assert_allclose(plv[off], 1.0, atol=1e-12)


def test_condition_summary_ignores_missing_spatial_charge() -> None:
    rows = [
        {"filtration_beta1_max": 2, "integrated_landscape_area": 0.5, "mean_plv": 0.4, "q_spatial": None},
        {"filtration_beta1_max": 4, "integrated_landscape_area": 1.5, "mean_plv": 0.6, "q_spatial": 3.0},
    ]
    summary = _condition_summary(rows)
    assert summary["windows"] == 2
    assert summary["mean_beta1"] == pytest.approx(3.0)
    assert summary["mean_landscape_area"] == pytest.approx(1.0)
    assert summary["mean_q_spatial"] == pytest.approx(3.0)  # the null is skipped, not counted as 0


def test_condition_summary_empty_is_null_not_zero() -> None:
    summary = _condition_summary([])
    assert summary["windows"] == 0
    assert summary["mean_landscape_area"] is None
    assert summary["mean_q_spatial"] is None


def _vortex_montage_and_phase(charge: int = 1):
    """8 sensors on a circle + a center, phase = charge * polar angle: a genuine
    integer-winding vortex with a known answer to check the defect map against."""
    angles = np.linspace(0.0, 2.0 * np.pi, 8, endpoint=False)
    xy = np.stack([np.cos(angles), np.sin(angles)], axis=1)
    xy = np.vstack([xy, [0.0, 0.0]])
    montage = np.hstack([xy, np.zeros((9, 1))])
    phase_values = np.concatenate([charge * angles, [0.0]])
    phase = np.tile(phase_values[:, None], (1, 5))  # (channels, samples)
    return montage, phase


def test_spatial_defect_snapshot_recovers_known_vortex_charge() -> None:
    """Total signed winding over all triangles must equal the field's real charge."""
    montage, phase = _vortex_montage_and_phase(charge=1)
    snapshot = spatial_defect_snapshot(phase, montage, beta1=4)
    assert snapshot is not None
    assert snapshot["beta1"] == 4
    assert snapshot["defects"]["n_valid_triangles"] > 0
    assert sum(snapshot["defects"]["signed_winding"]) == pytest.approx(1.0, abs=1e-6)
    assert snapshot["coordinate_frame"] == "sensor_2d_projection_of_standard_1020_montage"
    assert len(snapshot["channel_coordinates"]) == 9
    assert len(snapshot["phase"]) == 9
    assert snapshot["wave_vectors"] is None  # not implemented; must not be fabricated
    assert snapshot["quality_control"]["all_finite"] is True


def test_spatial_defect_snapshot_negative_charge_flips_sign() -> None:
    montage, phase = _vortex_montage_and_phase(charge=-1)
    snapshot = spatial_defect_snapshot(phase, montage)
    assert sum(snapshot["defects"]["signed_winding"]) == pytest.approx(-1.0, abs=1e-6)


def test_spatial_defect_snapshot_none_montage_returns_none() -> None:
    _, phase = _vortex_montage_and_phase()
    assert spatial_defect_snapshot(phase, None) is None


def test_spatial_defect_snapshot_too_few_channels_returns_none() -> None:
    montage, phase = _vortex_montage_and_phase()
    assert spatial_defect_snapshot(phase[:2], montage[:2]) is None


def test_spatial_defect_snapshot_drops_non_finite_positions_not_fabricates() -> None:
    montage, phase = _vortex_montage_and_phase()
    montage = montage.copy()
    montage[3, :2] = np.nan  # one bad sensor position
    snapshot = spatial_defect_snapshot(phase, montage)
    assert snapshot is not None
    assert snapshot["quality_control"]["n_channels_finite_position"] == 8
    assert len(snapshot["channel_coordinates"]) == 8


def test_spatial_defect_snapshot_h1_cycles_none_without_last_plv() -> None:
    """No last_plv passed -> h1_cycles must be null, never a fabricated empty list."""
    montage, phase = _vortex_montage_and_phase()
    snapshot = spatial_defect_snapshot(phase, montage)
    assert snapshot["h1_cycles"] is None


def test_spatial_defect_snapshot_h1_cycles_indices_valid_in_finite_channel_space() -> None:
    """When last_plv is given, h1_cycles' channel indices must be valid indices into
    the SAME channel_coordinates array this snapshot returns -- the whole point of
    computing them from a submatrix restricted to the identical finite mask."""
    montage, phase = _vortex_montage_and_phase()
    rng = np.random.default_rng(0)
    # a real-shaped PLV matrix (symmetric, unit diagonal, off-diagonal in [0,1])
    raw = rng.random((9, 9))
    plv = np.clip((raw + raw.T) / 2.0, 0.0, 1.0)
    np.fill_diagonal(plv, 1.0)
    snapshot = spatial_defect_snapshot(phase, montage, last_plv=plv)
    assert snapshot is not None
    assert snapshot["h1_cycles"] is not None
    n_finite = len(snapshot["channel_coordinates"])
    for cycle in snapshot["h1_cycles"]:
        for r, c in (cycle["birth_cell"], cycle["death_cell"]):
            assert 0 <= r < n_finite and 0 <= c < n_finite


def test_spatial_defect_snapshot_h1_cycles_restricted_to_finite_submatrix() -> None:
    """A channel with a non-finite position must never appear in h1_cycles --
    last_plv is the FULL (unfiltered) matrix, so this checks the function actually
    restricts to the finite submatrix rather than indexing the raw one."""
    montage, phase = _vortex_montage_and_phase()
    montage = montage.copy()
    montage[3, :2] = np.nan
    rng = np.random.default_rng(1)
    raw = rng.random((9, 9))
    plv = np.clip((raw + raw.T) / 2.0, 0.0, 1.0)
    np.fill_diagonal(plv, 1.0)
    snapshot = spatial_defect_snapshot(phase, montage, last_plv=plv)
    assert snapshot is not None
    n_finite = len(snapshot["channel_coordinates"])
    assert n_finite == 8
    for cycle in (snapshot["h1_cycles"] or []):
        for r, c in (cycle["birth_cell"], cycle["death_cell"]):
            assert 0 <= r < n_finite and 0 <= c < n_finite


def test_h1_cycle_channel_locations_too_few_channels_returns_empty() -> None:
    plv = np.eye(2)
    mask = np.array([True, True])
    assert h1_cycle_channel_locations(plv, mask) == []


def test_h1_cycle_channel_locations_deduplicates_symmetric_mirror_pairs() -> None:
    """A real symmetric PLV matrix must not report the mirror-image (c, r) cell
    as a second, distinct feature from (r, c) -- exercises the actual bug found
    when this was first run on real data (368 raw features collapsing to far
    fewer real distinct channel-pair features)."""
    rng = np.random.default_rng(3)
    raw = rng.random((7, 7))
    plv = np.clip((raw + raw.T) / 2.0, 0.0, 1.0)
    np.fill_diagonal(plv, 1.0)
    mask = np.ones(7, dtype=bool)
    cycles = h1_cycle_channel_locations(plv, mask)
    keys = set()
    for cycle in cycles:
        br, bc = cycle["birth_cell"]
        dr, dc = cycle["death_cell"]
        key = (tuple(sorted((br, bc))), tuple(sorted((dr, dc))))
        assert key not in keys  # no duplicate (up to channel-pair symmetry) survives
        keys.add(key)


def test_h1_cycle_channel_locations_restricts_before_extracting() -> None:
    """Directly verify the submatrix restriction: a 5x5 PLV with only 3 channels
    finite must only ever return indices in [0, 3)."""
    rng = np.random.default_rng(2)
    raw = rng.random((5, 5))
    plv = np.clip((raw + raw.T) / 2.0, 0.0, 1.0)
    np.fill_diagonal(plv, 1.0)
    mask = np.array([True, True, True, False, False])
    cycles = h1_cycle_channel_locations(plv, mask)
    for cycle in cycles:
        for r, c in (cycle["birth_cell"], cycle["death_cell"]):
            assert 0 <= r < 3 and 0 <= c < 3
