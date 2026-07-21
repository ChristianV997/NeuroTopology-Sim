from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest

_MOD = Path(__file__).resolve().parents[1] / "dual_engine" / "bold_phase_topology.py"
_spec = importlib.util.spec_from_file_location("bold_phase_topology", _MOD)
bpt = importlib.util.module_from_spec(_spec)
import sys as _sys
_sys.modules["bold_phase_topology"] = bpt
_spec.loader.exec_module(bpt)


def _bold(n_parcels=20, n_t=300, tr=1.0, seed=0):
    rng = np.random.default_rng(seed)
    t = np.arange(n_t) * tr
    # slow (~0.03 Hz) common oscillation + parcel noise -> resting-band structure
    common = np.sin(2 * np.pi * 0.03 * t)
    return np.array([common + 0.8 * rng.standard_normal(n_t) for _ in range(n_parcels)])


def test_bold_analytic_phase_shape_finite():
    ts = _bold()
    ph, amp = bpt.bold_analytic_phase(ts, tr=1.0, lo=0.01, hi=0.1)
    assert ph.shape == ts.shape and amp.shape == ts.shape
    assert np.all(np.isfinite(ph)) and np.all(np.isfinite(amp))


def test_bold_analytic_phase_validation():
    with pytest.raises(ValueError):
        bpt.bold_analytic_phase(np.zeros(100), tr=1.0)          # 1D
    with pytest.raises(ValueError):
        bpt.bold_analytic_phase(np.zeros((5, 300)), tr=-1.0)    # bad tr


def test_mean_network_connectivity_detects_coupling():
    rng = np.random.default_rng(1)
    n_t = 400
    a_drive = rng.standard_normal(n_t)
    b_drive = rng.standard_normal(n_t)
    # network A parcels share a_drive, network B share b_drive; A-B uncoupled
    A = np.array([a_drive + 0.3 * rng.standard_normal(n_t) for _ in range(6)])
    B = np.array([b_drive + 0.3 * rng.standard_normal(n_t) for _ in range(6)])
    ts = np.vstack([A, B])
    mask_a = np.array([True] * 6 + [False] * 6)
    mask_b = np.array([False] * 6 + [True] * 6)
    within_a = bpt.mean_network_connectivity(ts, mask_a, mask_a)
    between = bpt.mean_network_connectivity(ts, mask_a, mask_b)
    assert within_a > 0.5 and abs(between) < within_a  # within >> between


def test_signed_network_topology_runs_and_labels():
    rng = np.random.default_rng(2)
    n = 30
    coords = rng.uniform(-60, 60, size=(n, 3))
    ts = _bold(n_parcels=n, n_t=300, seed=3)
    labels = [f"p{i}" for i in range(n)]
    region_labels = {labels[i]: ("DMN" if i < 10 else "CEN" if i < 20 else "Other")
                     for i in range(n)}
    out = bpt.signed_network_topology(ts, tr=1.0, coords_mni=coords,
                                      parcel_labels=labels, region_labels=region_labels,
                                      n_topo_samples=40)
    ac = out["mean_abs_charge_by_region"]
    assert ac is not None
    assert set(ac).issubset({"DMN", "CEN", "Other"})
    assert all(np.isfinite(v) for v in ac.values())
    assert np.isfinite(out["mean_n_clusters"])


def test_region_abscharge_metric_scalar_finite():
    rng = np.random.default_rng(4)
    n = 24
    coords = rng.uniform(-60, 60, size=(n, 3))
    ts = _bold(n_parcels=n, n_t=280, seed=5)
    labels = [f"p{i}" for i in range(n)]
    region_labels = {labels[i]: ("DMN" if i < 12 else "CEN") for i in range(n)}
    v = bpt.region_abscharge_metric(ts, "DMN", tr=1.0, coords_mni=coords,
                                    parcel_labels=labels, region_labels=region_labels,
                                    n_topo_samples=30)
    assert np.isfinite(v) and v >= 0
