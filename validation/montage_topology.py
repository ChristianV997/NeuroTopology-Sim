from __future__ import annotations

from typing import Optional

import numpy as np
from scipy.spatial import Delaunay

EPS = 1e-12


def get_channel_xy(raw, montage: str | None = "standard_1020") -> tuple[list[str], np.ndarray]:
    """Return EEG channel names and 2D xy coordinates from montage geometry."""
    try:
        import mne
    except Exception as exc:  # pragma: no cover - depends on optional dependency
        raise ValueError("MNE is required for montage-aware coordinate extraction") from exc

    eeg_chs = [ch for ch in raw.ch_names if ch in raw.copy().pick_types(eeg=True, exclude=[]).ch_names]
    if not eeg_chs:
        raise ValueError("No EEG channels found")

    pos3d = {}
    montage_obj = raw.get_montage()
    if montage_obj is not None:
        pos3d.update({k.lower(): np.asarray(v, dtype=float) for k, v in montage_obj.get_positions()["ch_pos"].items()})

    if not pos3d and montage is not None:
        std = mne.channels.make_standard_montage(montage)
        std_pos = {k.lower(): np.asarray(v, dtype=float) for k, v in std.get_positions()["ch_pos"].items()}
        for ch in eeg_chs:
            key = ch.lower()
            if key in std_pos:
                pos3d[key] = std_pos[key]

    names: list[str] = []
    xy = []
    for ch in eeg_chs:
        key = ch.lower()
        if key not in pos3d:
            continue
        p = pos3d[key]
        if p.shape[0] < 2 or not np.all(np.isfinite(p[:2])):
            continue
        names.append(ch)
        xy.append(p[:2])

    if len(names) < 3:
        raise ValueError(f"Need at least 3 valid EEG channel positions, got {len(names)}")
    return names, np.asarray(xy, dtype=float)


def triangulate_xy(xy: np.ndarray) -> np.ndarray:
    arr = np.asarray(xy, dtype=float)
    if arr.ndim != 2 or arr.shape[1] != 2:
        raise ValueError(f"xy must be shape (n_channels, 2), got {arr.shape}")
    if arr.shape[0] < 3:
        raise ValueError("Need at least 3 points for triangulation")
    tri = Delaunay(arr)
    simplices = np.asarray(tri.simplices, dtype=int)
    if simplices.ndim != 2 or simplices.shape[1] != 3:
        raise ValueError(f"Invalid triangulation shape {simplices.shape}")
    return simplices


def triangle_winding(phi0, phi1, phi2) -> float:
    wrapped_diff = lambda a, b: np.angle(np.exp(1j * (b - a)))
    total = wrapped_diff(phi0, phi1) + wrapped_diff(phi1, phi2) + wrapped_diff(phi2, phi0)
    return float(total / (2.0 * np.pi))


def sensor_phase_topology_metrics(
    phase_vec: np.ndarray,
    xy: np.ndarray,
    triangles: np.ndarray,
    amp_vec: np.ndarray | None = None,
    amp_quantile: float | None = 0.1,
) -> dict:
    phase_arr = np.asarray(phase_vec, dtype=float)
    xy_arr = np.asarray(xy, dtype=float)
    tri_arr = np.asarray(triangles, dtype=int)

    if phase_arr.ndim != 1:
        raise ValueError(f"phase_vec must be 1D, got {phase_arr.shape}")
    if xy_arr.ndim != 2 or xy_arr.shape[1] != 2:
        raise ValueError(f"xy must be shape (n_channels, 2), got {xy_arr.shape}")
    if tri_arr.ndim != 2 or tri_arr.shape[1] != 3:
        raise ValueError(f"triangles must be shape (n_triangles, 3), got {tri_arr.shape}")
    if phase_arr.shape[0] < 3 or xy_arr.shape[0] < 3:
        raise ValueError("Need at least 3 channels")
    if phase_arr.shape[0] != xy_arr.shape[0]:
        raise ValueError("phase_vec and xy must share channel length")

    amp_arr = None if amp_vec is None else np.asarray(amp_vec, dtype=float)
    if amp_arr is not None and (amp_arr.ndim != 1 or amp_arr.shape[0] != phase_arr.shape[0]):
        raise ValueError("amp_vec must be 1D with same channel length as phase_vec")

    valid = np.ones(tri_arr.shape[0], dtype=bool)
    if amp_arr is not None and amp_quantile is not None:
        thr = np.quantile(amp_arr, amp_quantile)
        valid = np.all(amp_arr[tri_arr] > thr, axis=1)

    if not np.any(valid):
        raise ValueError("No valid triangles remain")

    local_w = np.array([triangle_winding(*phase_arr[t]) for t in tri_arr[valid]], dtype=float)

    edge_diffs = []
    for t in tri_arr[valid]:
        i, j, k = t
        edge_diffs.extend([
            np.angle(np.exp(1j * (phase_arr[j] - phase_arr[i]))),
            np.angle(np.exp(1j * (phase_arr[k] - phase_arr[j]))),
            np.angle(np.exp(1j * (phase_arr[i] - phase_arr[k]))),
        ])

    Q_sum = float(np.sum(local_w))
    Q = float(np.round(Q_sum))
    Qabs = float(np.sum(np.abs(local_w)))
    f_dress = float((Qabs - abs(Q)) / (abs(Q) + EPS))
    n_valid = int(np.sum(valid))

    out = {
        "Q": Q,
        "Qabs": Qabs,
        "f_dress": f_dress,
        "phase_grad": float(np.mean(np.abs(edge_diffs))),
        "n_triangles": int(tri_arr.shape[0]),
        "n_valid_triangles": n_valid,
        "defect_density": float(Qabs / max(n_valid, 1)),
        "metric_kind": "phase_grid_topology",
    }
    if not all(np.isfinite(v) for k, v in out.items() if isinstance(v, float)):
        raise ValueError("Non-finite topology metrics")
    return out


def phase_grid_topology_from_band(
    phase: np.ndarray,
    xy: np.ndarray,
    triangles: np.ndarray,
    amplitude: np.ndarray | None = None,
    amp_quantile: float | None = 0.1,
) -> dict:
    phase_arr = np.asarray(phase, dtype=float)
    if phase_arr.ndim != 2:
        raise ValueError(f"phase must be shape (channels, samples), got {phase_arr.shape}")
    n_ch, n_t = phase_arr.shape
    if n_ch < 3 or n_t < 1:
        raise ValueError("phase requires at least 3 channels and 1 sample")

    amp_arr = None if amplitude is None else np.asarray(amplitude, dtype=float)
    if amp_arr is not None and amp_arr.shape != phase_arr.shape:
        raise ValueError("amplitude must match phase shape")

    per_sample = []
    for t in range(n_t):
        amp_vec = amp_arr[:, t] if amp_arr is not None else None
        per_sample.append(sensor_phase_topology_metrics(phase_arr[:, t], xy, triangles, amp_vec=amp_vec, amp_quantile=amp_quantile))

    numeric_keys = ["Q", "Qabs", "f_dress", "phase_grad", "n_triangles", "n_valid_triangles", "defect_density"]
    agg = {}
    for k in numeric_keys:
        vals = np.array([m[k] for m in per_sample], dtype=float)
        if k == "Q":
            agg[k] = float(np.round(np.median(vals)))
        else:
            agg[k] = float(np.mean(vals))
    agg["metric_kind"] = "phase_grid_topology"

    if not all(np.isfinite(v) for k, v in agg.items() if isinstance(v, float)):
        raise ValueError("Non-finite aggregate topology metrics")
    return agg
