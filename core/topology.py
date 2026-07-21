from __future__ import annotations
import numpy as np

def wrap_phase(x: np.ndarray) -> np.ndarray:
    """Wrap phase differences into (-pi, pi]."""
    return (x + np.pi) % (2 * np.pi) - np.pi

def plaquette_charge(theta2d: np.ndarray) -> np.ndarray:
    """Compute local winding charge on each plaquette of a 2D phase field.

    Sign convention: the (i,j)->(i+1,j)->(i+1,j+1)->(i,j+1) loop used here traces
    clockwise when axis 0 is plotted as the vertical (y) axis increasing upward and
    axis 1 as horizontal (x). This gives the NEGATIVE of the standard counter-clockwise
    mathematical winding number: a true charge +k field yields Q=-k here. Validated
    against analytic ground-truth defects (integer charges -3..+3, half-integer nematic
    charges via the 2-theta convention) across resolutions 16-2048 and multiple
    non-degenerate core offsets -- see tests/test_topology_analytic_ground_truth.py.
    """
    if theta2d.ndim != 2:
        raise ValueError("theta2d must be 2D")
    a = wrap_phase(theta2d[1:, :-1] - theta2d[:-1, :-1])
    b = wrap_phase(theta2d[1:, 1:] - theta2d[1:, :-1])
    c = wrap_phase(theta2d[:-1, 1:] - theta2d[1:, 1:])
    d = wrap_phase(theta2d[:-1, :-1] - theta2d[:-1, 1:])
    return (a + b + c + d) / (2 * np.pi)

def compute_Q_slice(theta2d: np.ndarray) -> int:
    """Compute integer-like signed topological charge Q for one 2D slice."""
    q = plaquette_charge(theta2d)
    return int(np.rint(q.sum()))


def compute_nematic_defect_charge(director_theta2d: np.ndarray) -> float:
    """Topological charge of a nematic director field (head-tail symmetric, defined mod pi).

    Nematic defects are physically half-integer (+-1/2, +-1, +-3/2, ...) because the
    director n and -n are physically identical. Applying plaquette_charge directly to
    the raw director angle is WRONG for half-integer defects (it silently returns 0 for
    a true +-1/2 defect). The correct approach doubles the angle so the field becomes
    single-valued mod 2*pi, computes the integer winding of that, then halves the result.
    Sign-corrected to the standard counter-clockwise mathematical convention (opposite of
    plaquette_charge's raw sign -- see plaquette_charge docstring).
    """
    psi = wrap_phase(2.0 * director_theta2d)
    q_psi = compute_Q_slice(psi)
    return -q_psi / 2.0

def compute_Qabs_slice(theta2d: np.ndarray) -> float:
    """Compute absolute plaquette charge sum Qabs for one 2D slice."""
    q = plaquette_charge(theta2d)
    return float(np.sum(np.abs(q)))

def compute_Qz(psi3d: np.ndarray, axis: int = 2):
    """Compute Q and Qabs for each slice along a selected axis of a 3D field.

    Vectorised implementation: operates on all slices simultaneously instead
    of looping in Python, giving a substantial speed-up for large fields.
    """
    psi3d = np.asarray(psi3d)
    if psi3d.ndim != 3:
        raise ValueError("psi3d must be 3D")
    # Move the target axis to position 0 so shape is (nslices, nx, ny)
    sl = np.moveaxis(psi3d, axis, 0)
    theta = np.angle(sl)                         # (nslices, nx, ny)
    a = wrap_phase(theta[:, 1:, :-1] - theta[:, :-1, :-1])
    b = wrap_phase(theta[:, 1:, 1:]  - theta[:, 1:, :-1])
    c = wrap_phase(theta[:, :-1, 1:] - theta[:, 1:, 1:])
    d = wrap_phase(theta[:, :-1, :-1] - theta[:, :-1, 1:])
    q = (a + b + c + d) / (2 * np.pi)           # (nslices, nx-1, ny-1)
    Qz   = np.rint(q.sum(axis=(1, 2))).astype(int)
    Qabs = np.abs(q).sum(axis=(1, 2))
    return Qz, Qabs

def compute_f_dress(Qz: np.ndarray, Qabs: np.ndarray, eps: float = 1e-9) -> float:
    """Compute excess absolute winding relative to net winding.

    This ratio is near zero when local positive/negative winding mostly cancels
    to a coherent net topological charge, and increases when unsigned local
    winding dominates over the signed net charge.
    """
    return float((np.mean(Qabs) - abs(np.mean(Qz))) / (abs(np.mean(Qz)) + eps))


# ─────────────────────────────────────────────────────────────────────────────
# Cubical persistent homology (GUDHI backend, MIT license).
#
# `compute_Qz`/`plaquette_charge` above are a SINGLE-THRESHOLD summary: they sum
# winding at the field's own phase values only. Cubical persistence scans ALL
# sub-level-set thresholds of a real-valued grid at once, returning the full
# birth/death diagram per homology dimension -- H0 (amplitude basins/connected
# components), H1 (loops -- vortex/antivortex structure), and (3D fields) H2
# (voids). This is additive, not a replacement: run on `|psi|` (amplitude, e.g.
# from `validation.synthetic.cgl_defect_field`) or on a signed charge-density
# map to get a scale-resolved generalization of the current single-threshold
# `Qabs` count, and run separately on positive-/negative-charge density to
# preserve chirality information plain persistent homology otherwise discards.
#
# Requires the optional `gudhi` dependency (MIT; `pip install gudhi`) --
# guarded exactly like this repo's other optional deps (see
# `validation/montage_topology.get_channel_xy` for the MNE equivalent): a clear
# ImportError-derived message, not a silent no-op.
# ─────────────────────────────────────────────────────────────────────────────


def compute_cubical_persistence(field: np.ndarray, max_dimension: int = 2) -> dict:
    """Full sub-level cubical persistence diagrams of a real-valued 2D/3D grid.

    Returns ``{"diagrams": {dim: (n_pairs, 2) array of (birth, death)},
    "betti_numbers": [...], "metric_kind": "cubical_persistence"}``. Infinite
    death values (features that never die, e.g. the single connected component
    of a finite grid) are kept as ``np.inf`` -- callers doing finite-only
    summaries (e.g. `betti_curve`, `persistence_landscape` below) already
    filter these out.
    """
    try:
        import gudhi
    except ImportError as exc:
        raise ImportError(
            "compute_cubical_persistence requires the optional 'gudhi' dependency "
            "(pip install gudhi; MIT license)"
        ) from exc

    arr = np.asarray(field, dtype=float)
    if arr.ndim not in (2, 3):
        raise ValueError(f"field must be 2D or 3D, got shape {arr.shape}")
    if not np.all(np.isfinite(arr)):
        raise ValueError("field contains non-finite values")

    cc = gudhi.CubicalComplex(top_dimensional_cells=arr)
    cc.persistence()

    n_dims = min(max_dimension, arr.ndim) + 1
    diagrams = {}
    for dim in range(n_dims):
        intervals = cc.persistence_intervals_in_dimension(dim)
        diagrams[dim] = np.asarray(intervals, dtype=float) if len(intervals) else np.empty((0, 2))

    return {
        "diagrams": diagrams,
        "betti_numbers": [int(b) for b in cc.betti_numbers()],
        "metric_kind": "cubical_persistence",
    }


def betti_curve(diagram: np.ndarray, grid: np.ndarray) -> np.ndarray:
    """Betti curve: count of persistence pairs alive at each value in `grid`.

    A scale-resolved generalization of a single Betti number -- how many
    topological features (of the diagram's dimension) exist at each
    filtration threshold, not just at one. Infinite-death pairs are treated as
    alive from `birth` to the end of `grid`.
    """
    grid = np.asarray(grid, dtype=float)
    diagram = np.asarray(diagram, dtype=float)
    if diagram.size == 0:
        return np.zeros_like(grid)
    b = diagram[:, 0]
    d = np.where(np.isfinite(diagram[:, 1]), diagram[:, 1], grid.max() + 1.0)
    alive = (grid[None, :] >= b[:, None]) & (grid[None, :] < d[:, None])
    return alive.sum(axis=0).astype(float)


def persistence_landscape(diagram: np.ndarray, grid: np.ndarray, n_layers: int = 5) -> np.ndarray:
    """First `n_layers` persistence landscape functions (Bubenik 2015),
    sampled on `grid`, shape ``(n_layers, grid.size)``.

    Generalizes the single hand-rolled lambda_1-only landscape in
    `dual_engine/spectral_tda.py` to the full landscape hierarchy: layer k is
    the k-th largest tent function ``max(0, min(t-birth, death-t))`` at each
    grid point, over all (finite) persistence pairs. Layer 0 (lambda_1 in the
    usual 1-indexed notation) alone reproduces that module's existing
    landscape; the additional layers are new information this project did not
    previously extract. Infinite-death pairs are excluded (a landscape is a
    finite-persistence summary).
    """
    grid = np.asarray(grid, dtype=float)
    diagram = np.asarray(diagram, dtype=float)
    if diagram.size == 0:
        return np.zeros((n_layers, grid.size))
    finite = diagram[np.isfinite(diagram).all(axis=1)]
    if finite.size == 0:
        return np.zeros((n_layers, grid.size))
    b = finite[:, 0][:, None]
    d = finite[:, 1][:, None]
    tents = np.maximum(0.0, np.minimum(grid[None, :] - b, d - grid[None, :]))  # (m, grid)
    tents_sorted = -np.sort(-tents, axis=0)  # descending per grid point
    m = tents_sorted.shape[0]
    out = np.zeros((n_layers, grid.size))
    k = min(n_layers, m)
    out[:k] = tents_sorted[:k]
    return out


def diagram_bottleneck_distance(diagram_a: np.ndarray, diagram_b: np.ndarray) -> float:
    """Bottleneck distance between two persistence diagrams (via GUDHI), the
    principled way to ask "how much did this field's topology change" between
    two states/timepoints/conditions -- the topological analogue of the PCI
    comparison already used for EEG complexity, but for spatial topology.
    """
    try:
        import gudhi
    except ImportError as exc:
        raise ImportError(
            "diagram_bottleneck_distance requires the optional 'gudhi' dependency "
            "(pip install gudhi; MIT license)"
        ) from exc
    a = np.asarray(diagram_a, dtype=float)
    b = np.asarray(diagram_b, dtype=float)
    dist = float(gudhi.bottleneck_distance(a, b))
    if not np.isfinite(dist):
        raise ValueError("bottleneck distance is non-finite")
    return dist


def compute_cubical_persistence_cripser(
    field: np.ndarray,
    max_dimension: int = 2,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Cubical persistence via CubicalRipser (optional faster alternative to GUDHI).

    Computes full persistence diagrams for H0, H1, H2 on a cubical complex derived
    from the input field (e.g., 2D amplitude field, 3D charge density). Requires
    the optional 'cripser' dependency (LGPL license; install via pip install cripser).

    Faster than GUDHI's CubicalComplex for 3D/4D volumes; also returns birth/death
    voxel coordinates (``cripser``'s unique feature) for spatial localization.

    Parameters
    ----------
    field : array-like, shape (...,)
        Scalar field (2D, 3D, or higher) to compute persistence on.
    max_dimension : int
        Maximum homology dimension to compute (0, 1, 2, ...).

    Returns
    -------
    diagram_h0, diagram_h1, diagram_h2 : array, shape (n_pairs, 2)
        Persistence diagrams (birth, death) for H0, H1, H2 respectively.
        Empty array if no pairs exist for that dimension.
    """
    try:
        import cripser
    except ImportError as exc:
        raise ImportError(
            "compute_cubical_persistence_cripser requires the optional 'cripser' dependency "
            "(pip install cripser; LGPL license)"
        ) from exc

    field = np.asarray(field, dtype=float)
    if not np.all(np.isfinite(field)):
        raise ValueError("field contains non-finite values")

    # Negate so that low values (minima) come first in the persistence pipeline
    result = cripser.ripser(-field, maxdim=max_dimension)
    diagrams = result["dgms"]

    # Extract diagrams; pad to expected shape if dimension is missing
    diagram_h0 = np.asarray(diagrams[0], dtype=float) if len(diagrams) > 0 else np.empty((0, 2))
    diagram_h1 = np.asarray(diagrams[1], dtype=float) if len(diagrams) > 1 else np.empty((0, 2))
    diagram_h2 = np.asarray(diagrams[2], dtype=float) if len(diagrams) > 2 else np.empty((0, 2))

    return diagram_h0, diagram_h1, diagram_h2
