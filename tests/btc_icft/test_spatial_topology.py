"""Synthetic ground-truth tests for spatial_topology.py -- montage-aware real
winding-number topology on a genuine 2D phase field, the biggest scientific
upgrade in the "beyond topology" pass to what this repo's q_net/q_abs/f_dress
metrics have been named as if they meant all along.

The vortex-detection tests below caught a real bug during development: the
first implementation used `griddata(..., fill_value=0.0)` for grid cells
outside the sparse electrode array's convex hull (~picked up ~30% of the
grid for a typical 19-channel 10-20 layout) -- that blind fill silently
planted a fake "phase = 0 exactly" patch across the whole extrapolated
region, which collapsed a real +1 vortex's detected winding charge from -1
to 0 whenever the fake patch abutted the vortex core. Fixed by falling back
to nearest-neighbor extrapolation for exactly the NaN cells instead. These
tests are the regression test for that fix, not just a feature check.
"""
from __future__ import annotations

import numpy as np
import pytest

from core.topology import compute_Q_slice, compute_Qabs_slice
from sciencer_d.btc_icft.level_t.spatial_topology import (
    build_montage_phase_grid,
    build_spatial_topology_report,
    compute_spatial_topology_for_window,
    resolve_montage_positions,
)

_STANDARD_1020_SUBSET = [
    "Fp1", "Fp2", "F7", "F3", "Fz", "F4", "F8", "C3", "Cz",
    "C4", "T7", "T8", "P7", "P3", "Pz", "P4", "P8", "O1", "O2",
]


# ---------------------------------------------------------------------------
# resolve_montage_positions
# ---------------------------------------------------------------------------

def test_resolve_montage_positions_matches_standard_1020():
    positions, name = resolve_montage_positions(_STANDARD_1020_SUBSET)
    assert name == "standard_1020"
    assert set(positions.keys()) == set(_STANDARD_1020_SUBSET)


def test_resolve_montage_positions_case_insensitive():
    lower_names = [c.lower() for c in _STANDARD_1020_SUBSET]
    positions, name = resolve_montage_positions(lower_names)
    assert name == "standard_1020"
    assert set(positions.keys()) == set(lower_names)


def test_resolve_montage_positions_returns_none_for_unknown_names():
    positions, name = resolve_montage_positions(["NotARealChannel1", "NotARealChannel2"])
    assert positions is None
    assert name is None


# ---------------------------------------------------------------------------
# build_montage_phase_grid -- the vortex-detection ground-truth tests
# ---------------------------------------------------------------------------

def _channel_positions_and_center():
    positions, _ = resolve_montage_positions(_STANDARD_1020_SUBSET)
    xy = np.array([positions[ch][:2] for ch in _STANDARD_1020_SUBSET])
    center = xy.mean(axis=0)
    return positions, xy, center


def test_vortex_phase_grid_detects_known_winding_charge():
    """A genuine mathematical +1 (counter-clockwise) vortex centered at the
    electrode array's centroid must be detected with |Q|=1 -- sign per
    core.topology's own documented convention (plaquette_charge yields the
    NEGATIVE of the standard CCW winding number), so a true +1 field gives
    Q=-1 here."""
    positions, xy, center = _channel_positions_and_center()
    phase_values = np.arctan2(xy[:, 1] - center[1], xy[:, 0] - center[0])

    grid = build_montage_phase_grid(_STANDARD_1020_SUBSET, positions, phase_values, grid_size=24)
    assert compute_Q_slice(grid) == -1
    assert compute_Qabs_slice(grid) == pytest.approx(1.0, abs=1e-6)


def test_reversed_vortex_phase_grid_detects_opposite_charge():
    positions, xy, center = _channel_positions_and_center()
    phase_values = -np.arctan2(xy[:, 1] - center[1], xy[:, 0] - center[0])

    grid = build_montage_phase_grid(_STANDARD_1020_SUBSET, positions, phase_values, grid_size=24)
    assert compute_Q_slice(grid) == 1
    assert compute_Qabs_slice(grid) == pytest.approx(1.0, abs=1e-6)


def test_random_phase_grid_has_no_net_winding():
    positions, xy, _ = _channel_positions_and_center()
    rng = np.random.default_rng(0)
    random_phase = rng.uniform(-np.pi, np.pi, size=len(_STANDARD_1020_SUBSET))

    grid = build_montage_phase_grid(_STANDARD_1020_SUBSET, positions, random_phase, grid_size=24)
    assert compute_Q_slice(grid) == 0


def test_multi_sample_grid_shape():
    positions, xy, center = _channel_positions_and_center()
    phase_values = np.tile(
        np.arctan2(xy[:, 1] - center[1], xy[:, 0] - center[0])[:, None], (1, 5)
    )
    grids = build_montage_phase_grid(_STANDARD_1020_SUBSET, positions, phase_values, grid_size=16)
    assert grids.shape == (5, 16, 16)
    # every sample identical -> every sample's charge must match the single-sample case
    for t in range(5):
        assert compute_Q_slice(grids[t]) == -1


# ---------------------------------------------------------------------------
# compute_spatial_topology_for_window
# ---------------------------------------------------------------------------

def test_skips_missing_source_file():
    m_row = {"row_id": "r1", "source_file": "/does/not/exist.edf", "window_start_s": "0", "window_end_s": "1"}
    result = compute_spatial_topology_for_window(m_row)
    assert result["status"] == "skipped"
    assert "not found" in result["reason"]


def test_skips_unmatched_channel_names(tmp_path, monkeypatch):
    f = tmp_path / "fake.edf"
    f.write_bytes(b"x")
    monkeypatch.setattr("data.bids_ingest.get_sample_rate", lambda path: 250.0)
    monkeypatch.setattr("data.bids_ingest.get_channel_names", lambda path, max_channels=None: ["Weird1", "Weird2", "Weird3", "Weird4"])
    monkeypatch.setattr("data.bids_ingest.read_window_signal", lambda *a, **k: np.random.default_rng(0).standard_normal((4, 500)))

    m_row = {"row_id": "r1", "source_file": str(f), "window_start_s": "0", "window_end_s": "2"}
    result = compute_spatial_topology_for_window(m_row)
    assert result["status"] == "skipped"
    assert "no standard montage matched" in result["reason"]


def test_skips_too_few_channels(tmp_path, monkeypatch):
    f = tmp_path / "fake.edf"
    f.write_bytes(b"x")
    names = _STANDARD_1020_SUBSET[:3]
    monkeypatch.setattr("data.bids_ingest.get_sample_rate", lambda path: 250.0)
    monkeypatch.setattr("data.bids_ingest.get_channel_names", lambda path, max_channels=None: names)
    monkeypatch.setattr("data.bids_ingest.read_window_signal", lambda *a, **k: np.random.default_rng(0).standard_normal((3, 500)))

    m_row = {"row_id": "r1", "source_file": str(f), "window_start_s": "0", "window_end_s": "2"}
    result = compute_spatial_topology_for_window(m_row)
    assert result["status"] == "skipped"
    assert ">=4 channels" in result["reason"]


def test_computes_real_spatial_topology_from_signal(tmp_path, monkeypatch):
    f = tmp_path / "fake.edf"
    f.write_bytes(b"x")
    names = _STANDARD_1020_SUBSET
    sfreq = 250.0
    t = np.arange(0, 4, 1 / sfreq)

    positions, _ = resolve_montage_positions(names)
    xy = np.array([positions[ch][:2] for ch in names])
    center = xy.mean(axis=0)
    spatial_phase_offset = np.arctan2(xy[:, 1] - center[1], xy[:, 0] - center[0])
    # each channel: a shared 10 Hz alpha oscillation, offset by its own
    # position in a spatial vortex pattern -- genuine spatial phase structure
    signal = np.array([
        np.sin(2 * np.pi * 10 * t + spatial_phase_offset[i]) + 0.02 * np.random.default_rng(i).standard_normal(t.size)
        for i in range(len(names))
    ])

    monkeypatch.setattr("data.bids_ingest.get_sample_rate", lambda path: sfreq)
    monkeypatch.setattr("data.bids_ingest.get_channel_names", lambda path, max_channels=None: names)
    monkeypatch.setattr("data.bids_ingest.read_window_signal", lambda *a, **k: signal)

    m_row = {"row_id": "r1", "source_file": str(f), "window_start_s": "0", "window_end_s": "4"}
    result = compute_spatial_topology_for_window(m_row, band="alpha", n_time_samples=5, grid_size=16)
    assert result["status"] == "computed"
    assert result["montage"] == "standard_1020"
    assert result["n_channels"] == len(names)
    for key in ("Q", "Qabs", "phase_grad", "f_dress"):
        assert np.isfinite(result[key])
    # the constructed vortex pattern should show real net winding on average
    assert abs(result["Q"]) > 0.5


def test_deterministic(tmp_path, monkeypatch):
    f = tmp_path / "fake.edf"
    f.write_bytes(b"x")
    names = _STANDARD_1020_SUBSET
    sfreq = 250.0
    t = np.arange(0, 2, 1 / sfreq)
    signal = np.array([np.sin(2 * np.pi * 10 * t + i * 0.1) for i in range(len(names))])
    monkeypatch.setattr("data.bids_ingest.get_sample_rate", lambda path: sfreq)
    monkeypatch.setattr("data.bids_ingest.get_channel_names", lambda path, max_channels=None: names)
    monkeypatch.setattr("data.bids_ingest.read_window_signal", lambda *a, **k: signal)

    m_row = {"row_id": "r1", "source_file": str(f), "window_start_s": "0", "window_end_s": "2"}
    r1 = compute_spatial_topology_for_window(m_row, n_time_samples=5, grid_size=16)
    r2 = compute_spatial_topology_for_window(m_row, n_time_samples=5, grid_size=16)
    assert r1 == r2


# ---------------------------------------------------------------------------
# build_spatial_topology_report
# ---------------------------------------------------------------------------

def test_build_report_bounds_sample_size_by_default(tmp_path, monkeypatch):
    from sciencer_d.btc_icft.level_t.base_real_topology import LevelTRealTopologyRow

    def _make_t_row(row_id):
        return LevelTRealTopologyRow(
            row_id=row_id, subject_id="sub-001", session_id=None, run_id=None,
            window_id="win-0", task_label="x", q_net=0.1, q_abs=0.2, f_dress=0.05,
            defect_density=0.01, n_triangles=10, n_valid_triangles=10, topology_quality=1.0,
            null_method="real_none", null_seed=0, source_file="a", window_start_s=0.0,
            window_end_s=1.0, warnings=[],
        )

    f = tmp_path / "fake.edf"
    f.write_bytes(b"x")
    names = _STANDARD_1020_SUBSET
    sfreq = 250.0
    t = np.arange(0, 2, 1 / sfreq)
    signal = np.array([np.sin(2 * np.pi * 10 * t + i * 0.1) for i in range(len(names))])
    monkeypatch.setattr("data.bids_ingest.get_sample_rate", lambda path: sfreq)
    monkeypatch.setattr("data.bids_ingest.get_channel_names", lambda path, max_channels=None: names)
    monkeypatch.setattr("data.bids_ingest.read_window_signal", lambda *a, **k: signal)

    m_rows = [
        {"row_id": f"r{i}", "source_file": str(f), "window_start_s": "0", "window_end_s": "2"}
        for i in range(30)
    ]
    t_rows = [_make_t_row(f"r{i}") for i in range(30)]

    report = build_spatial_topology_report(t_rows, m_rows, sample_size=5, n_time_samples=3, grid_size=12)
    assert report["status"] == "spatial_topology_computed"
    assert report["n_windows_computed"] == 5  # bounded by default-style sample_size
    assert report["n_windows_total_candidates"] == 30
