"""BOLD-adapted signed/localized phase-topology for resting-state fMRI (ds005237).

The signed-winding metrics in validation/montage_topology.py were built for EEG's
fast analytic phase. BOLD has no comparable fast oscillation; its dominant
fluctuations are ~0.01-0.1 Hz. This module adapts the approach to BOLD *honestly*:

PHASE CHOICE (see task Step 2). Primary = Hilbert analytic phase of the BOLD
signal band-passed to the standard resting-state band (0.01-0.1 Hz). BOLD
phase-coupling / phase-locking is an established (if debated) fMRI technique
(Glerean et al. 2012, Mapp. Hum. Brain; Cabral et al. LEiDA 2017; Ponce-Alvarez
et al.). This is the closer analog to the EEG-side method. A SINGLE band is used
-- the delta/theta/alpha/beta/gamma boundaries are physiological to EEG and do
NOT transfer to hemodynamics, so no multi-band split is invented.

GEOMETRY. Parcels are projected top-down (axial x-y of their MNI centroids) and
Delaunay-triangulated -- *exactly* how the EEG sensor montage is treated
(3D electrode positions -> 2D projection -> triangulation). Documented limitation:
the axial projection collapses the dorsal-ventral (z) axis, so the winding is over
an axial 2D projection, NOT the folded cortical manifold. It is a pragmatic 2D
analog, not a true cortical-surface phase field.

Reuses signed_defect_topology_from_band / net_charge_by_region / signed_defect_map
from validation.montage_topology (unchanged). The standard amplitude-correlation
network-connectivity comparator is implemented here for a like-for-like head-to-head.
"""
from __future__ import annotations

import numpy as np
from scipy.signal import butter, filtfilt, hilbert

EPS = 1e-12


def bold_analytic_phase(ts: np.ndarray, tr: float, lo: float = 0.01, hi: float = 0.1
                        ) -> tuple[np.ndarray, np.ndarray]:
    """Band-pass BOLD to the resting band and return (phase, amplitude) via Hilbert.

    ts: (n_parcels, n_timepoints). tr: repetition time in seconds. Returns analytic
    phase and envelope, both (n_parcels, n_timepoints).
    """
    ts = np.asarray(ts, dtype=float)
    if ts.ndim != 2:
        raise ValueError(f"ts must be 2D (n_parcels, n_timepoints), got {ts.shape}")
    if ts.shape[0] < 3 or ts.shape[1] < 16:
        raise ValueError(f"need >=3 parcels and >=16 timepoints, got {ts.shape}")
    if tr <= 0:
        raise ValueError(f"tr must be positive, got {tr}")
    fs = 1.0 / tr
    nyq = fs / 2.0
    hi_eff = min(hi, 0.99 * nyq)
    if not (0 < lo < hi_eff):
        raise ValueError(f"invalid band {lo}-{hi} Hz for fs={fs:.3f} (nyq={nyq:.3f})")
    b, a = butter(2, [lo / nyq, hi_eff / nyq], btype="band")
    x = filtfilt(b, a, ts, axis=1)
    an = hilbert(x, axis=1)
    phase, amp = np.angle(an), np.abs(an)
    if not (np.all(np.isfinite(phase)) and np.all(np.isfinite(amp))):
        raise ValueError("non-finite BOLD analytic phase/amplitude")
    return phase, amp


def mean_network_connectivity(ts: np.ndarray, mask_a: np.ndarray, mask_b: np.ndarray
                              ) -> float:
    """Standard comparator: mean pairwise Pearson correlation between two parcel sets
    (the amplitude-correlation FC the DMN-CEN hyperconnectivity literature uses).
    For a within-network call pass mask_a == mask_b (off-diagonal mean)."""
    ts = np.asarray(ts, dtype=float)
    C = np.corrcoef(ts)
    ia = np.where(mask_a)[0]
    ib = np.where(mask_b)[0]
    if ia.size == 0 or ib.size == 0:
        raise ValueError("empty network mask")
    block = C[np.ix_(ia, ib)]
    if np.array_equal(ia, ib):
        vals = block[np.triu_indices(ia.size, 1)]
    else:
        vals = block.ravel()
    m = float(np.nanmean(vals))
    if not np.isfinite(m):
        raise ValueError("non-finite network connectivity")
    return m


def axial_xy_tri(coords_mni: np.ndarray):
    """Top-down (axial x-y) projection + Delaunay triangulation of parcel centroids,
    analogous to the EEG montage projection."""
    from scipy.spatial import Delaunay
    xy = np.asarray(coords_mni, dtype=float)[:, :2]
    tri = Delaunay(xy).simplices
    return xy, tri


def signed_network_topology(ts, tr, coords_mni, parcel_labels, region_labels,
                            n_topo_samples=120, amp_quantile=0.1,
                            cluster_min_winding_abs=0.1) -> dict:
    """Signed/localized phase-defect topology on the cortical BOLD phase field,
    aggregated per network via region_labels. Returns the montage-topology signed
    summary (mean_net/abs_charge_by_region, mean_region_chirality, cluster stats)."""
    from validation.montage_topology import signed_defect_topology_from_band
    phase, amp = bold_analytic_phase(ts, tr)
    xy, tri = axial_xy_tri(coords_mni)
    n_t = phase.shape[1]
    idx = np.linspace(0, n_t - 1, min(n_topo_samples, n_t)).astype(int)
    return signed_defect_topology_from_band(
        phase[:, idx], xy, tri, list(parcel_labels), region_labels=region_labels,
        amplitude=amp[:, idx], amp_quantile=amp_quantile,
        cluster_min_winding_abs=cluster_min_winding_abs)


def region_abscharge_metric(ts, region, tr, coords_mni, parcel_labels, region_labels,
                            n_topo_samples=80, amp_quantile=0.1) -> float:
    """Scalar metric_fn for surrogate gating: the ENTIRE BOLD-phase ->
    signed_defect_map -> per-network aggregation runs inside, returning one
    region's time-averaged |charge|. (Takes raw ts so the gate phase-randomizes
    the source BOLD, not a downstream summary.)"""
    from validation.montage_topology import signed_defect_map, net_charge_by_region
    phase, amp = bold_analytic_phase(ts, tr)
    xy, tri = axial_xy_tri(coords_mni)
    n_t = phase.shape[1]
    idx = np.linspace(0, n_t - 1, min(n_topo_samples, n_t)).astype(int)
    vals = []
    for t in idx:
        dm = signed_defect_map(phase[:, t], xy, tri, amp_vec=amp[:, t], amp_quantile=amp_quantile)
        nc = net_charge_by_region(dm, region_labels, list(parcel_labels))
        vals.append(nc["region_abs_charge"].get(region, 0.0))
    v = float(np.mean(vals))
    if not np.isfinite(v):
        raise ValueError("non-finite region abscharge metric")
    return v
