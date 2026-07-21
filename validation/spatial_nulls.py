"""Spatial null-hypothesis testing (the "spin test") for sensor-space maps.

The temporal surrogates in ``validation/nulls.py`` and
``validation/surrogate_testing.py`` destroy *temporal* / cross-channel phase
structure but leave a spatial map's regional alignment untouched. They cannot
answer the distinct question a signed-charge or defect-cluster **spatial** map
raises: *is this map's alignment to a regional partition (e.g. anterior vs
posterior, DMN vs CEN) stronger than expected from spatial autocorrelation
alone?* A per-sensor value vector is spatially smooth (neighbouring sensors
carry similar values), so even a randomly-oriented map will, by chance, load
onto some region — and a naive permutation that shuffles sensor labels
independently destroys that smoothness and therefore tests too weak a null,
inflating significance.

The standard fix in the neuroimaging literature is the **spin test**
(Alexander-Bloch et al., 2018, *NeuroImage*): generate null maps by *rigidly
rotating* the sensor geometry and reassigning each original sensor's value to
the nearest rotated position. A rigid rotation moves the whole configuration
together, so spatial autocorrelation is preserved exactly (it is an isometry —
pairwise sensor distances are invariant), while the map's alignment to any
fixed regional partition is randomized. Váša et al. (2018) refined the
reassignment to be **bijective** (each original sensor receives exactly one
rotated sensor, via greedy nearest-available matching) to avoid the
value-duplication/dropout of independent nearest-neighbour assignment; that
bijective variant is the default here.

This is the 2D sensor-space form (rotations in the montage plane). It is a
hand-rolled, dependency-free implementation — the same design choice this
project already makes for LEiDA — covering the common EEG/MEG montage case
without pulling in the full spherical-surface machinery (``neuromaps``), which
remains the tool to reach for once true cortical-surface geometry is wired in.

All public functions are deterministic given ``seed``, perform no I/O, and
validate finiteness.
"""
from __future__ import annotations

from typing import Callable, Dict

import numpy as np

EPS = 1e-12


def _validate_xy(xy: np.ndarray) -> np.ndarray:
    arr = np.asarray(xy, dtype=float)
    if arr.ndim != 2 or arr.shape[1] != 2:
        raise ValueError(f"xy must be shape (n_sensors, 2), got {arr.shape}")
    if arr.shape[0] < 3:
        raise ValueError(f"need at least 3 sensors for a spatial spin test, got {arr.shape[0]}")
    if not np.all(np.isfinite(arr)):
        raise ValueError("xy contains non-finite values")
    return arr


def _random_rotation_2d(rng: np.random.Generator, reflect: bool) -> np.ndarray:
    """A uniformly-random 2x2 orthogonal matrix.

    Rotation by an angle drawn uniformly on [0, 2*pi); with ``reflect`` a fair
    coin additionally flips handedness (det -1). Reflections are included by
    default because a montage has no privileged chirality — excluding them
    would sample only half of the isometry group and bias the null.
    """
    theta = rng.uniform(0.0, 2.0 * np.pi)
    c, s = np.cos(theta), np.sin(theta)
    R = np.array([[c, -s], [s, c]], dtype=float)
    if reflect and rng.random() < 0.5:
        R = R @ np.array([[1.0, 0.0], [0.0, -1.0]], dtype=float)
    return R


def _greedy_bijective_assignment(dist2: np.ndarray) -> np.ndarray:
    """Greedy nearest-available bijective assignment from a squared-distance
    matrix ``dist2[i, j]`` = |original_i - rotated_j|^2.

    Returns ``perm`` of length n where ``perm[i]`` is the rotated-sensor index
    assigned to original sensor i, each rotated index used exactly once. Ties
    are broken deterministically by index order (``argsort`` is stable), so the
    result depends only on the geometry and the rotation, not on iteration
    accidents. This is the Váša et al. (2018) matching, greedy variant: process
    original sensors in ascending order of their *initial* nearest-target
    distance (computed once, not refreshed as targets are consumed) so the
    most-constrained assignments are made first. It is a greedy approximation to
    the optimal (Hungarian) assignment, not the optimum itself.
    """
    if not np.all(np.isfinite(dist2)):
        raise ValueError("dist2 must be finite (masking below assumes finite input)")
    n = dist2.shape[0]
    perm = np.full(n, -1, dtype=int)
    taken = np.zeros(n, dtype=bool)
    # Order originals by how close their single nearest target is (initial value,
    # not refreshed): the sensor with the tightest match is least free to be
    # displaced, so assign it first.
    nearest_d = dist2.min(axis=1)
    order = np.argsort(nearest_d, kind="stable")
    for i in order:
        row = dist2[i]
        # mask already-taken targets with +inf, then take the closest remaining
        masked = np.where(taken, np.inf, row)
        j = int(np.argmin(masked))
        perm[i] = j
        taken[j] = True
    return perm


def spin_permutation_2d(
    xy: np.ndarray,
    rng: np.random.Generator,
    reflect: bool = True,
    bijective: bool = True,
) -> np.ndarray:
    """One spin permutation of sensor indices.

    Rotate the sensor coordinates rigidly about their centroid, then map each
    original sensor to a rotated sensor. Returns ``perm`` such that
    ``values[perm]`` is the spun map (original value at rotated location moved
    back to the nearest original location).

    bijective=True  (default): greedy nearest-available matching, each value
                    used exactly once (Váša et al. 2018). Preserves the exact
                    multiset of values.
    bijective=False : independent nearest-neighbour (Alexander-Bloch et al.
                    2018 original) — faster, but a value may be duplicated or
                    dropped; documented, not the default.
    """
    arr = _validate_xy(xy)
    centroid = arr.mean(axis=0, keepdims=True)
    R = _random_rotation_2d(rng, reflect)
    rotated = (arr - centroid) @ R.T + centroid
    # squared distances between every original (row) and rotated (col) position
    diff = arr[:, None, :] - rotated[None, :, :]
    dist2 = np.einsum("ijk,ijk->ij", diff, diff)
    if bijective:
        return _greedy_bijective_assignment(dist2)
    return np.argmin(dist2, axis=1)


def spin_null_distribution(
    values: np.ndarray,
    xy: np.ndarray,
    statistic_fn: Callable[[np.ndarray], float],
    n_rotations: int = 1000,
    seed: int = 0,
    reflect: bool = True,
    bijective: bool = True,
) -> np.ndarray:
    """Null distribution of ``statistic_fn`` under rigid spins of the map.

    ``values`` is a per-sensor scalar vector aligned to ``xy``. For each of
    ``n_rotations`` random spins, the values are spun (``values[perm]``) and
    ``statistic_fn`` is recomputed. The regional/hypothesis structure the
    statistic tests against must live *inside* ``statistic_fn`` (a closure over
    fixed region labels), so that the spin moves the data relative to fixed
    regions — never the regions relative to the data.

    Spins on which ``statistic_fn`` raises or returns non-finite are skipped;
    the returned array contains only usable null values.
    """
    vals = np.asarray(values, dtype=float)
    arr = _validate_xy(xy)
    if vals.ndim != 1 or vals.shape[0] != arr.shape[0]:
        raise ValueError(f"values must be 1D length n_sensors ({arr.shape[0]}), got {vals.shape}")
    if not np.all(np.isfinite(vals)):
        raise ValueError("values contains non-finite entries")
    if n_rotations < 1:
        raise ValueError(f"n_rotations must be >= 1, got {n_rotations}")

    rng = np.random.default_rng(seed)
    out = []
    for _ in range(n_rotations):
        perm = spin_permutation_2d(arr, rng, reflect=reflect, bijective=bijective)
        try:
            v = float(statistic_fn(vals[perm]))
        except Exception:
            continue
        if np.isfinite(v):
            out.append(v)
    return np.asarray(out, dtype=float)


def spatial_spin_test(
    values: np.ndarray,
    xy: np.ndarray,
    statistic_fn: Callable[[np.ndarray], float],
    n_rotations: int = 1000,
    seed: int = 0,
    two_sided: bool = True,
    reflect: bool = True,
    bijective: bool = True,
) -> Dict[str, object]:
    """Spin-test a scalar spatial statistic against a spatial-autocorrelation null.

    Computes ``statistic_fn(values)`` on the observed map and against a null of
    rigidly-spun maps (see ``spin_null_distribution``). p-value convention
    matches ``validation/surrogate_testing`` — ``(#null at least as extreme + 1)
    / (n_used + 1)``:

      * two_sided=True (default here): ``|stat - null_mean|`` based. A spatial
        map has no intrinsic "larger is real" direction the way a directional
        temporal hypothesis does, so two-sided is the safer default.
      * two_sided=False: one-sided in the direction the observed statistic
        points; use only with a genuine prior directional hypothesis.

    Returns ``{observed, null_mean, null_std, z, p_value, n_rotations,
    n_used, two_sided, bijective, passes_gate_p05, metric_kind}``.
    """
    vals = np.asarray(values, dtype=float)
    observed = float(statistic_fn(vals))
    if not np.isfinite(observed):
        raise ValueError("statistic_fn returned a non-finite value on the observed map")

    null = spin_null_distribution(
        vals, xy, statistic_fn, n_rotations=n_rotations, seed=seed,
        reflect=reflect, bijective=bijective,
    )
    n_used = int(null.size)
    n_failed = int(n_rotations) - n_used  # spins on which statistic_fn raised/non-finite
    if n_used < 2:
        raise ValueError(f"too few usable spins ({n_used}); cannot form a null distribution")

    null_mean = float(null.mean())
    null_std = float(null.std(ddof=1))
    z = 0.0 if null_std < EPS else float((observed - null_mean) / null_std)

    if two_sided:
        as_extreme = int(np.sum(np.abs(null - null_mean) >= abs(observed - null_mean)))
    elif observed >= null_mean:
        as_extreme = int(np.sum(null >= observed))
    else:
        as_extreme = int(np.sum(null <= observed))
    p_value = float((as_extreme + 1) / (n_used + 1))

    out = {
        "observed": observed,
        "null_mean": null_mean,
        "null_std": null_std,
        "z": z,
        "p_value": p_value,
        "n_rotations": int(n_rotations),
        "n_used": n_used,
        "n_failed": n_failed,
        "two_sided": bool(two_sided),
        "bijective": bool(bijective),
        "passes_gate_p05": bool(p_value < 0.05),
        "metric_kind": "spatial_spin_null_test",
    }
    for k, v in out.items():
        if isinstance(v, float) and not np.isfinite(v):
            raise ValueError(f"non-finite spin-test output: {k}={v}")
    return out


def region_contrast_statistic(
    region_labels: np.ndarray,
    region_a,
    region_b,
    agg: str = "mean",
) -> Callable[[np.ndarray], float]:
    """Build a ``statistic_fn`` = agg(values in region_a) - agg(values in region_b).

    The canonical spin-test target for a signed-charge / net-defect map with a
    two-region hypothesis (e.g. anterior vs posterior, DMN vs CEN). The returned
    closure holds the *fixed* region labels, so the spin test moves the values
    relative to these fixed regions — exactly the alignment question a temporal
    surrogate cannot pose. Pass it to ``spatial_spin_test``/``spin_null_distribution``.

    agg="mean" (default): difference of region means — normalizes for region
        size, the safer choice when regions have unequal element counts.
    agg="sum" : difference of region sums — this is literally the *net charge*
        contrast (``net_charge_by_region``'s ``region_net_charge`` is a per-region
        sum), so the integration wrapper uses it.
    """
    if agg not in ("mean", "sum"):
        raise ValueError(f"agg must be 'mean' or 'sum', got {agg!r}")
    labels = np.asarray(region_labels)
    mask_a = labels == region_a
    mask_b = labels == region_b
    if not mask_a.any():
        raise ValueError(f"region_a={region_a!r} matches no element")
    if not mask_b.any():
        raise ValueError(f"region_b={region_b!r} matches no element")
    reduce = np.mean if agg == "mean" else np.sum

    def _stat(values: np.ndarray) -> float:
        v = np.asarray(values, dtype=float)
        if v.shape[0] != labels.shape[0]:
            raise ValueError("values length must match region_labels length")
        return float(reduce(v[mask_a]) - reduce(v[mask_b]))

    return _stat


def spin_test_signed_defect_region_contrast(
    defect_map: dict,
    region_labels: dict,
    channel_names: list,
    region_a,
    region_b,
    agg: str = "sum",
    n_rotations: int = 1000,
    seed: int = 0,
    two_sided: bool = True,
    reflect: bool = True,
    bijective: bool = True,
) -> Dict[str, object]:
    """Turnkey spin test of the net-charge contrast between two regions on a
    ``signed_defect_map`` — the bridge that actually closes the spatial-null gap
    for the montage_topology signed spatial outputs.

    The spatial map here is *per triangle*: values are the triangle signed
    windings and the point cloud is the triangle centroids. Each triangle is
    assigned to a region with the SAME majority-vote rule ``net_charge_by_region``
    uses (via ``montage_topology.assign_triangles_to_regions``), unassigned
    triangles are dropped so values/coords/labels stay index-aligned, and the
    contrast (default ``agg="sum"`` — the net-charge quantity) is spin-tested by
    rigidly rotating the centroid cloud. Returns the ``spatial_spin_test`` dict
    plus ``n_triangles_used`` / ``n_triangles_unassigned``.

    Requires a ``signed_defect_map`` (``validation.montage_topology.signed_defect_map``)
    and its ``channel_names`` ordering; ``region_labels`` follows the same
    name-or-index keying as ``net_charge_by_region``.
    """
    from validation.montage_topology import assign_triangles_to_regions

    signed = np.asarray(defect_map["signed_winding"], dtype=float)
    centroids = np.asarray(defect_map["centroid_xy"], dtype=float)
    tri_region = assign_triangles_to_regions(defect_map, region_labels, channel_names)

    assigned = np.array([r is not None for r in tri_region], dtype=bool)
    n_unassigned = int((~assigned).sum())
    values = signed[assigned]
    xy = centroids[assigned]
    labels = np.asarray([r for r in tri_region if r is not None], dtype=object)

    if values.shape[0] < 3:
        raise ValueError(
            f"only {values.shape[0]} region-assigned triangles; need >=3 for a spatial spin test"
        )

    stat = region_contrast_statistic(labels, region_a, region_b, agg=agg)
    result = spatial_spin_test(
        values, xy, stat, n_rotations=n_rotations, seed=seed,
        two_sided=two_sided, reflect=reflect, bijective=bijective,
    )
    result["n_triangles_used"] = int(values.shape[0])
    result["n_triangles_unassigned"] = n_unassigned
    result["agg"] = agg
    result["metric_kind"] = "spatial_spin_net_charge_contrast"
    return result
