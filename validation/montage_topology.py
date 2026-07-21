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


def get_channel_xy_templateflow(
    raw,
    montage: str | None = "standard_1020",
    template: str = "fsaverage",
) -> tuple[list[str], np.ndarray]:
    """Return EEG channel names and 2D xy coordinates from real cortical surface geometry via TemplateFlow.

    Fetches the specified cortical template (fsaverage, fsLR, etc.) from TemplateFlow,
    maps each EEG channel to the nearest surface vertex, and returns 2D coordinates
    sampled from the surface.

    Parameters
    ----------
    raw : mne.io.BaseRaw
        MNE raw data object with EEG channel information.
    montage : str or None
        Standard montage name (e.g., 'standard_1020') to use if raw has no montage.
    template : str
        TemplateFlow template name ('fsaverage', 'fsLR', etc.). Default 'fsaverage'.

    Returns
    -------
    names : list of str
        Channel names that mapped to the surface.
    xy : ndarray, shape (n_channels, 2)
        2D coordinates (azimuth, elevation) from the surface template.
    """
    try:
        import templateflow.api as tflow
        import mne
    except Exception as exc:  # pragma: no cover
        raise ValueError("TemplateFlow and MNE are required for surface-based coordinate extraction") from exc

    try:
        from scipy.spatial import cKDTree
    except Exception as exc:  # pragma: no cover
        raise ValueError("SciPy is required for TemplateFlow integration") from exc

    # Get 3D channel positions from standard montage
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

    # Fetch template surface coordinates
    try:
        surf_file = tflow.get(template, desc="sphere", suffix="surf", extension=".gii")
    except Exception:  # pragma: no cover
        raise ValueError(f"Could not fetch {template} sphere from TemplateFlow")

    try:
        import nibabel as nib
    except Exception as exc:  # pragma: no cover
        raise ValueError("Nibabel is required to read TemplateFlow surfaces") from exc

    surf = nib.load(surf_file)
    surf_coords = np.asarray(surf.darrays[0].data, dtype=float)

    if surf_coords.shape[1] != 3:
        raise ValueError(f"Expected 3D surface coords, got shape {surf_coords.shape}")

    # Normalize channel positions to unit sphere for matching
    names: list[str] = []
    xyz_matched = []
    tree = cKDTree(surf_coords)

    for ch in eeg_chs:
        key = ch.lower()
        if key not in pos3d:
            continue
        p3d = pos3d[key]
        if p3d.shape[0] < 3 or not np.all(np.isfinite(p3d)):
            continue
        # Normalize to unit sphere to match surface
        p_norm = p3d / np.linalg.norm(p3d)
        # Find nearest surface vertex
        _, idx = tree.query(p_norm)
        names.append(ch)
        xyz_matched.append(surf_coords[idx])

    if len(names) < 3:
        raise ValueError(f"Need at least 3 valid surface-mapped channels, got {len(names)}")

    # Convert 3D coords to 2D azimuth/elevation
    xyz = np.asarray(xyz_matched, dtype=float)
    azimuth = np.arctan2(xyz[:, 1], xyz[:, 0])
    elevation = np.arccos(np.clip(xyz[:, 2], -1.0, 1.0))
    xy = np.column_stack([azimuth, elevation])

    return names, xy


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


def _wrapped_diff(a: np.ndarray, b: np.ndarray) -> np.ndarray:
    return np.angle(np.exp(1j * (b - a)))


def triangle_winding(phi0, phi1, phi2) -> float:
    total = _wrapped_diff(phi0, phi1) + _wrapped_diff(phi1, phi2) + _wrapped_diff(phi2, phi0)
    return float(total / (2.0 * np.pi))


def triangle_winding_batch(phase_arr: np.ndarray, tri_arr: np.ndarray) -> np.ndarray:
    """Vectorized winding for every triangle at once (elementwise identical to
    calling ``triangle_winding`` in a Python loop over ``tri_arr``, just without
    the loop).

    ``phase_arr`` may be 1D ``(n_channels,)`` (single sample) or 2D
    ``(n_channels, n_t)`` (batch across time). ``tri_arr`` is ``(n_tri, 3)`` int
    vertex indices. Returns ``(n_tri,)`` or ``(n_tri, n_t)`` respectively,
    replacing the per-triangle Python list comprehensions in
    ``sensor_phase_topology_metrics``/``signed_defect_map`` with a single gather
    + vectorized wrapped-difference sum (the same pattern
    ``core.topology.compute_Qz`` already uses on the regular grid).
    """
    phi = np.asarray(phase_arr, dtype=float)[np.asarray(tri_arr, dtype=int)]  # (n_tri, 3, ...)
    phi0, phi1, phi2 = phi[:, 0, ...], phi[:, 1, ...], phi[:, 2, ...]
    total = _wrapped_diff(phi0, phi1) + _wrapped_diff(phi1, phi2) + _wrapped_diff(phi2, phi0)
    return total / (2.0 * np.pi)


def _edge_diffs_batch(phase_arr: np.ndarray, tri_arr: np.ndarray) -> np.ndarray:
    """All three wrapped edge differences for every triangle, flattened.

    Same value set as the ``edge_diffs`` Python-loop accumulation in
    ``sensor_phase_topology_metrics`` (order differs, irrelevant since only
    ``mean(abs(.))`` is ever taken downstream).
    """
    phi = np.asarray(phase_arr, dtype=float)[np.asarray(tri_arr, dtype=int)]
    d01 = _wrapped_diff(phi[:, 0, ...], phi[:, 1, ...])
    d12 = _wrapped_diff(phi[:, 1, ...], phi[:, 2, ...])
    d20 = _wrapped_diff(phi[:, 2, ...], phi[:, 0, ...])
    return np.concatenate([d01.ravel(), d12.ravel(), d20.ravel()])


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

    local_w = triangle_winding_batch(phase_arr, tri_arr[valid])
    edge_diffs = _edge_diffs_batch(phase_arr, tri_arr[valid])

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

    xy_arr = np.asarray(xy, dtype=float)
    tri_arr = np.asarray(triangles, dtype=int)

    # Batch compute triangle windings for all timepoints at once
    per_sample = []
    for t in range(n_t):
        # Per-sample validity: compute dynamically per timepoint (simple and correct)
        valid_t = np.ones(tri_arr.shape[0], dtype=bool)
        if amp_arr is not None and amp_quantile is not None:
            thr = np.quantile(amp_arr[:, t], amp_quantile)
            amp_tri = amp_arr[tri_arr, t]  # (n_tri, 3) - vertices of each triangle at timepoint t
            valid_t = np.all(amp_tri > thr, axis=1)  # (n_tri,)

        if not np.any(valid_t):
            raise ValueError(f"No valid triangles remain at timepoint {t}")

        local_w = triangle_winding_batch(phase_arr[:, t], tri_arr[valid_t])
        edge_diffs = _edge_diffs_batch(phase_arr[:, t], tri_arr[valid_t])

        Q_sum = float(np.sum(local_w))
        Q = float(np.round(Q_sum))
        Qabs = float(np.sum(np.abs(local_w)))
        f_dress = float((Qabs - abs(Q)) / (abs(Q) + EPS))
        n_valid = int(np.sum(valid_t))

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
        per_sample.append(out)

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


# ─────────────────────────────────────────────────────────────────────────────
# Signed / localized phase-defect metrics.
#
# The unsigned scalars above (`Qabs`, `defect_density`) sum |winding| over the
# whole montage, discarding two physically meaningful pieces of information that
# are available at the point of computation: the sign (chirality) of each defect
# and its location. Xu, Long, Feng & Gong (2023, Nat. Hum. Behav.) show that for
# cortical phase singularities ("brain spirals") it is exactly the location
# (clustering at network boundaries) and rotational direction that carry the
# task-relevant signal, not the raw unsigned count. The functions below preserve
# both. They are strictly additive: the unsigned path is untouched, and
# `np.sum(np.abs(signed_defect_map(...)["signed_winding"]))` reproduces the old
# `Qabs` on the same inputs, so the new path is a refinement, not a different
# computation.
# ─────────────────────────────────────────────────────────────────────────────


def _validate_topology_inputs(
    phase_vec: np.ndarray,
    xy: np.ndarray,
    triangles: np.ndarray,
    amp_vec: np.ndarray | None,
    amp_quantile: float | None,
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Shared input validation + amplitude masking.

    Mirrors `sensor_phase_topology_metrics` exactly (same checks, same messages,
    same per-triangle amplitude mask ``np.all(amp[tri] > thr, axis=1)``) so the
    signed metrics are directly comparable triangle-for-triangle with the unsigned
    ones on identical inputs. Returns ``(phase_arr, xy_arr, tri_arr, valid_mask)``.
    """
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
    return phase_arr, xy_arr, tri_arr, valid


def signed_defect_map(
    phase_vec: np.ndarray,
    xy: np.ndarray,
    triangles: np.ndarray,
    amp_vec: np.ndarray | None = None,
    amp_quantile: float | None = 0.1,
) -> dict:
    """Per-triangle signed winding with location — the atomic signed metric.

    Unlike `sensor_phase_topology_metrics`, which collapses to unsigned scalars,
    this keeps every valid triangle's signed winding, chirality, and centroid.
    Validity masking is identical to the unsigned path, so the returned triangles
    are the same subset (same order) it would score. In particular
    ``np.sum(np.abs(result["signed_winding"]))`` equals the old ``Qabs`` and
    ``np.round(np.sum(result["signed_winding"]))`` equals the old ``Q``.
    """
    phase_arr, xy_arr, tri_arr, valid = _validate_topology_inputs(
        phase_vec, xy, triangles, amp_vec, amp_quantile
    )
    valid_tri = tri_arr[valid]
    signed_winding = triangle_winding_batch(phase_arr, valid_tri)
    # centroid of each valid triangle in the input xy coordinate space
    centroid_xy = xy_arr[valid_tri].mean(axis=1)
    chirality = np.sign(signed_winding).astype(int)
    n_valid = int(valid_tri.shape[0])

    if not np.all(np.isfinite(signed_winding)) or not np.all(np.isfinite(centroid_xy)):
        raise ValueError("Non-finite signed defect map values")

    return {
        "triangle_indices": valid_tri,
        "signed_winding": signed_winding,
        "centroid_xy": centroid_xy,
        "chirality": chirality,
        "n_valid_triangles": n_valid,
        "metric_kind": "signed_defect_map",
    }


def _require_defect_map(defect_map: dict) -> None:
    required = {"triangle_indices", "signed_winding", "centroid_xy", "chirality", "n_valid_triangles"}
    missing = required - set(defect_map)
    if missing:
        raise ValueError(f"defect_map missing required keys: {sorted(missing)}")


def assign_triangles_to_regions(
    defect_map: dict,
    region_labels: dict,
    channel_names: list[str],
) -> np.ndarray:
    """Per-triangle region label by majority vote of the triangle's 3 vertices.

    Returns an ``object`` array of length ``n_valid_triangles`` aligned to
    ``defect_map["signed_winding"]`` / ``["centroid_xy"]``: each entry is the
    region label, or ``None`` when any vertex is unlabeled or the three vertex
    labels have no majority (the exact rule ``net_charge_by_region`` aggregates
    with — that function calls this one, and spatial-null callers
    (``validation/spatial_nulls``) reuse it instead of re-deriving the labeling).

    ``region_labels`` may be keyed by channel *name* (``dict[str, str]``) or by
    channel *index* (``dict[int, str]``); ``channel_names`` is the ordered
    channel list that resolves a vertex index to its name.
    """
    _require_defect_map(defect_map)
    tri_idx = np.asarray(defect_map["triangle_indices"], dtype=int)
    if not isinstance(channel_names, (list, tuple)) or len(channel_names) == 0:
        raise ValueError("channel_names must be a non-empty list of channel names")

    keys = list(region_labels.keys())
    by_index = len(keys) > 0 and all(isinstance(k, (int, np.integer)) for k in keys)

    def label_of(ch_index: int):
        if by_index:
            return region_labels.get(int(ch_index))
        if ch_index < 0 or ch_index >= len(channel_names):
            raise ValueError(
                f"triangle references channel index {ch_index} outside channel_names "
                f"(len {len(channel_names)}); defect_map and channel_names are inconsistent"
            )
        return region_labels.get(channel_names[ch_index])

    out = np.empty(tri_idx.shape[0], dtype=object)
    for r, row in enumerate(tri_idx):
        labs = [label_of(v) for v in row]
        if any(l is None for l in labs):
            out[r] = None
            continue
        uniq, counts = np.unique(np.asarray(labs, dtype=object), return_counts=True)
        if counts.max() < 2:  # all three different -> no majority
            out[r] = None
            continue
        out[r] = uniq[int(np.argmax(counts))]
    return out


def net_charge_by_region(
    defect_map: dict,
    region_labels: dict,
    channel_names: list[str],
) -> dict:
    """Aggregate signed winding per caller-supplied region/network label.

    ``region_labels`` maps a channel to a region and may be keyed either by
    channel *name* (``dict[str, str]``) or by channel *index* (``dict[int, str]``);
    indices must match the channel ordering used to build ``xy``/``triangles``
    upstream. ``channel_names`` is that same ordered channel list (index i -> name),
    used to resolve each triangle's three vertices to region labels.

    Each triangle is assigned to a region by **majority vote among its 3 vertices'
    labels**. A triangle is left *unassigned* (counted in ``n_unassigned``, never
    guessed) when (a) any vertex has no label in ``region_labels`` — partial
    coverage is an expected real-world case, e.g. bad-channel interpolation — or
    (b) all three vertex labels differ (no majority). Only regions that receive at
    least one triangle appear as keys, so an absent region means "not sampled"
    rather than a fabricated zero.
    """
    _require_defect_map(defect_map)
    signed = np.asarray(defect_map["signed_winding"], dtype=float)
    chir = np.asarray(defect_map["chirality"], dtype=float)

    # Per-triangle region via majority vote (shared with spatial-null callers).
    tri_region = assign_triangles_to_regions(defect_map, region_labels, channel_names)

    region_net: dict[str, float] = {}
    region_abs: dict[str, float] = {}
    region_n: dict[str, int] = {}
    region_chir_sum: dict[str, float] = {}
    n_unassigned = 0

    for region, w, c in zip(tri_region, signed, chir):
        if region is None:  # unlabeled vertex or no majority -> never guessed
            n_unassigned += 1
            continue
        region_net[region] = region_net.get(region, 0.0) + float(w)
        region_abs[region] = region_abs.get(region, 0.0) + abs(float(w))
        region_n[region] = region_n.get(region, 0) + 1
        region_chir_sum[region] = region_chir_sum.get(region, 0.0) + float(c)

    region_mean_chirality = {r: region_chir_sum[r] / region_n[r] for r in region_n}

    for d in (region_net, region_abs, region_mean_chirality):
        if not all(np.isfinite(v) for v in d.values()):
            raise ValueError("Non-finite region charge metrics")

    return {
        "region_net_charge": region_net,
        "region_abs_charge": region_abs,
        "region_n_triangles": region_n,
        "region_mean_chirality": region_mean_chirality,
        "n_unassigned": int(n_unassigned),
        # per-triangle region label (aligned to defect_map signed_winding/centroid_xy;
        # None where unassigned) so spatial-null callers reuse this exact labeling.
        "triangle_region": tri_region,
        "metric_kind": "net_charge_by_region",
    }


def _median_nn_distance(points: np.ndarray) -> float:
    """Median nearest-neighbor distance among points (a scale-free eps default)."""
    try:
        from scipy.spatial.distance import pdist, squareform
    except ImportError:
        # Fallback if scipy.spatial.distance unavailable (scipy already imported above)
        diffs = points[:, None, :] - points[None, :, :]
        d = np.sqrt((diffs ** 2).sum(axis=-1))
        np.fill_diagonal(d, np.inf)
        nn = d.min(axis=1)
        med = float(np.median(nn[np.isfinite(nn)]))
        return med if med > 0 else EPS

    # Vectorized pairwise distance computation via scipy
    if points.shape[0] < 2:
        return EPS
    d = squareform(pdist(points))
    np.fill_diagonal(d, np.inf)
    nn = d.min(axis=1)
    med = float(np.median(nn[np.isfinite(nn)]))
    return med if med > 0 else EPS


def defect_spatial_clustering(
    defect_map: dict,
    eps: float | None = None,
    min_samples: int = 3,
    min_winding_abs: float = 0.1,
) -> dict:
    """Do defects pile up in specific zones, or scatter uniformly?

    DBSCAN over the centroids of *non-trivial* defect triangles (those with
    ``abs(signed_winding) > min_winding_abs`` — an explicit parameter, not a hidden
    magic number). When ``eps`` is None it is set to the median nearest-neighbor
    distance among the candidate centroids, so the function adapts to any montage
    coordinate scale rather than assuming one. With fewer than ``min_samples``
    candidate centroids no clustering is attempted (returns ``n_clusters == 0``
    with a note) instead of feeding DBSCAN too little data.
    """
    _require_defect_map(defect_map)
    from sklearn.cluster import DBSCAN

    centroids = np.asarray(defect_map["centroid_xy"], dtype=float)
    signed = np.asarray(defect_map["signed_winding"], dtype=float)
    cand_mask = np.abs(signed) > min_winding_abs
    cand = centroids[cand_mask]
    cand_w = signed[cand_mask]

    if cand.shape[0] < min_samples:
        return {
            "n_clusters": 0,
            "n_noise": 0,
            "cluster_centroids": np.empty((0, 2), dtype=float),
            "cluster_net_charge": np.empty((0,), dtype=float),
            "cluster_sizes": np.empty((0,), dtype=int),
            "eps_used": float(eps) if eps is not None else 0.0,
            "min_samples": int(min_samples),
            "note": "insufficient candidate defects for clustering",
            "metric_kind": "defect_spatial_clustering",
        }

    eps_used = float(eps) if eps is not None else _median_nn_distance(cand)
    labels = DBSCAN(eps=eps_used, min_samples=min_samples).fit_predict(cand)

    cluster_ids = sorted(l for l in set(labels.tolist()) if l != -1)
    cluster_centroids = []
    cluster_net_charge = []
    cluster_sizes = []
    for cid in cluster_ids:
        m = labels == cid
        cluster_centroids.append(cand[m].mean(axis=0))
        cluster_net_charge.append(float(cand_w[m].sum()))
        cluster_sizes.append(int(m.sum()))

    cluster_centroids = (
        np.asarray(cluster_centroids, dtype=float) if cluster_centroids else np.empty((0, 2), dtype=float)
    )
    cluster_net_charge = np.asarray(cluster_net_charge, dtype=float)
    cluster_sizes = np.asarray(cluster_sizes, dtype=int)

    if not (np.all(np.isfinite(cluster_centroids)) and np.all(np.isfinite(cluster_net_charge))
            and np.isfinite(eps_used)):
        raise ValueError("Non-finite spatial clustering metrics")

    return {
        "n_clusters": int(len(cluster_ids)),
        "n_noise": int(np.sum(labels == -1)),
        "cluster_centroids": cluster_centroids,
        "cluster_net_charge": cluster_net_charge,
        "cluster_sizes": cluster_sizes,
        "eps_used": float(eps_used),
        "min_samples": int(min_samples),
        "metric_kind": "defect_spatial_clustering",
    }


def _cluster_persistence_proxy(cluster_results: list[dict]) -> float:
    """Mean survival (in consecutive samples) of defect-cluster lineages.

    Greedy nearest-centroid matching between the clusters at sample t and t+1,
    accepting a match only within ``2 * eps_used`` of the clustering call at
    sample t; an unmatched cluster ends its lineage. This is deliberately a simple
    first-pass proxy, NOT a globally optimal tracker: a low value means defect
    clusters are transient, a high value means they persist and migrate (as in
    Gong et al.'s traveling brain spirals). Returns 0.0 for fewer than 2 samples.
    """
    T = len(cluster_results)
    if T < 2:
        return 0.0

    cents = [np.asarray(cr.get("cluster_centroids"), dtype=float).reshape(-1, 2)
             for cr in cluster_results]
    eps = [float(cr.get("eps_used", 0.0)) for cr in cluster_results]

    lengths: list[int] = []
    # each ongoing lineage: [current_centroid (2,), length_so_far]
    ongoing = [[c, 1] for c in cents[0]]

    try:
        from scipy.spatial.distance import cdist
    except ImportError:
        # Fallback: scalar loop version if cdist unavailable
        for t in range(1, T):
            nxt = cents[t]
            thr = 2.0 * eps[t - 1]
            used: set[int] = set()
            new_ongoing: list = []
            for cent, length in ongoing:
                best, best_d = -1, np.inf
                for j in range(nxt.shape[0]):
                    if j in used:
                        continue
                    d = float(np.linalg.norm(nxt[j] - cent))
                    if d < best_d:
                        best_d, best = d, j
                if best >= 0 and thr > 0 and best_d <= thr:
                    used.add(best)
                    new_ongoing.append([nxt[best], length + 1])
                else:
                    lengths.append(length)
            for j in range(nxt.shape[0]):
                if j not in used:
                    new_ongoing.append([nxt[j], 1])
            ongoing = new_ongoing
        for _cent, length in ongoing:
            lengths.append(length)
        return float(np.mean(lengths)) if lengths else 0.0

    # Vectorized matching using cdist: all distances at once
    for t in range(1, T):
        nxt = cents[t]
        thr = 2.0 * eps[t - 1]
        used: set[int] = set()
        new_ongoing: list = []

        # For each ongoing cluster, find nearest cluster in nxt
        if ongoing and nxt.shape[0] > 0:
            ongoing_cents = np.array([cent for cent, _len in ongoing])
            D = cdist(ongoing_cents, nxt)  # (n_ongoing, n_nxt)

            for i, (_cent, length) in enumerate(ongoing):
                row = D[i]
                min_idx = int(np.argmin(row))
                best_d = float(row[min_idx])
                if min_idx not in used and thr > 0 and best_d <= thr:
                    used.add(min_idx)
                    new_ongoing.append([nxt[min_idx], length + 1])
                else:
                    lengths.append(length)
        else:
            # No ongoing lineages
            for _cent, length in ongoing:
                lengths.append(length)

        for j in range(nxt.shape[0]):
            if j not in used:
                new_ongoing.append([nxt[j], 1])
        ongoing = new_ongoing

    for _cent, length in ongoing:
        lengths.append(length)

    return float(np.mean(lengths)) if lengths else 0.0


def signed_defect_topology_from_band(
    phase: np.ndarray,
    xy: np.ndarray,
    triangles: np.ndarray,
    channel_names: list[str],
    region_labels: dict | None = None,
    amplitude: np.ndarray | None = None,
    amp_quantile: float | None = 0.1,
    cluster_min_winding_abs: float = 0.1,
) -> dict:
    """Time-series wrapper for the signed/localized metrics (parallel to
    `phase_grid_topology_from_band`, but sign- and location-preserving).

    For each time sample computes `signed_defect_map`; if ``region_labels`` is
    given, also `net_charge_by_region`; and always `defect_spatial_clustering`.
    Aggregation deliberately does NOT collapse back to a single unsigned scalar:
    region charges/chirality are averaged per region over time (net & abs charge
    treat a region absent in a sample as 0, since an empty set of defects nets to
    zero; chirality averages only over samples where the region actually appears,
    to avoid reading "unsampled" as "balanced"), and cluster counts/persistence
    summarize the spatial structure. ``region_labels=None`` is supported and
    yields ``None`` for every ``*_by_region`` field.
    """
    phase_arr = np.asarray(phase, dtype=float)
    if phase_arr.ndim != 2:
        raise ValueError(f"phase must be shape (channels, samples), got {phase_arr.shape}")
    n_ch, n_t = phase_arr.shape
    if n_ch < 3 or n_t < 1:
        raise ValueError("phase requires at least 3 channels and 1 sample")
    if not isinstance(channel_names, (list, tuple)) or len(channel_names) != n_ch:
        raise ValueError(
            f"channel_names must have one entry per channel (expected {n_ch}, "
            f"got {len(channel_names) if isinstance(channel_names, (list, tuple)) else type(channel_names)})"
        )

    amp_arr = None if amplitude is None else np.asarray(amplitude, dtype=float)
    if amp_arr is not None and amp_arr.shape != phase_arr.shape:
        raise ValueError("amplitude must match phase shape")

    per_region_net: list[dict] = []
    per_region_abs: list[dict] = []
    per_region_chir: list[dict] = []
    per_sample_clusters: list[dict] = []
    n_clusters_list: list[int] = []

    for t in range(n_t):
        amp_vec = amp_arr[:, t] if amp_arr is not None else None
        dm = signed_defect_map(phase_arr[:, t], xy, triangles, amp_vec=amp_vec, amp_quantile=amp_quantile)
        if region_labels is not None:
            nc = net_charge_by_region(dm, region_labels, list(channel_names))
            per_region_net.append(nc["region_net_charge"])
            per_region_abs.append(nc["region_abs_charge"])
            per_region_chir.append(nc["region_mean_chirality"])
        cl = defect_spatial_clustering(dm, min_winding_abs=cluster_min_winding_abs)
        per_sample_clusters.append(cl)
        n_clusters_list.append(int(cl["n_clusters"]))

    if region_labels is not None:
        regions = set().union(*[set(d) for d in per_region_net]) if per_region_net else set()
        mean_net = {r: float(np.mean([d.get(r, 0.0) for d in per_region_net])) for r in regions}
        mean_abs = {r: float(np.mean([d.get(r, 0.0) for d in per_region_abs])) for r in regions}
        mean_chir = {}
        for r in regions:
            present = [d[r] for d in per_region_chir if r in d]
            mean_chir[r] = float(np.mean(present)) if present else 0.0
        for d in (mean_net, mean_abs, mean_chir):
            if not all(np.isfinite(v) for v in d.values()):
                raise ValueError("Non-finite aggregate region metrics")
    else:
        mean_net = mean_abs = mean_chir = None

    mean_n_clusters = float(np.mean(n_clusters_list)) if n_clusters_list else 0.0
    persistence = _cluster_persistence_proxy(per_sample_clusters)

    if not (np.isfinite(mean_n_clusters) and np.isfinite(persistence)):
        raise ValueError("Non-finite aggregate signed-defect metrics")

    return {
        "mean_net_charge_by_region": mean_net,
        "mean_abs_charge_by_region": mean_abs,
        "mean_region_chirality": mean_chir,
        "time_resolved_n_clusters": n_clusters_list,
        "mean_n_clusters": mean_n_clusters,
        "mean_cluster_persistence_proxy": persistence,
        "n_timepoints": int(n_t),
        "metric_kind": "signed_defect_topology",
    }
