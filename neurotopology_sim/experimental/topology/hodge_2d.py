r"""Production weighted Hodge-Helmholtz decomposition for oriented 2D cochain complexes.

HOLD / SYNTHETIC_ONLY
=====================
This module computes the weighted discrete Hodge-Helmholtz decomposition of an
oriented 1-cochain on a 2-dimensional cell/simplicial complex. It is an
algebraic and numerical operator: it does NOT provide evidence of cortical
propagation, biological vortices, consciousness, or any clinical claim.
Gemini Revision 8 and related theoretical proposals are unverified working notes;
this implementation enforces only the discrete algebraic and metric identities.

Algebraic Setup and Coboundaries
--------------------------------
Let $C_0, C_1, C_2$ denote the chains of vertices $V$, oriented edges $E$, and
oriented faces $F$. The coboundary operators are:
- $d_0: C^0 \to C^1$ (shape $|E| \times |V|$), mapping vertex 0-cochains to
  oriented edge differences: $(d_0 \alpha)_e = \alpha(v_j) - \alpha(v_i)$.
- $d_1: C^1 \to C^2$ (shape $|F| \times |E|$), mapping edge 1-cochains to
  oriented face circulations: $(d_1 \omega)_f = \sum_{e \in \partial f} \pm \omega_e$.
- Exactness condition: $d_1 @ d_0 = 0$ identically. The module verifies this
  identity and fails closed if violated.

Metric on 1-Cochains ($W_1$) and Metric Classification
------------------------------------------------------
The inner product on 1-cochains is induced by a symmetric positive-definite
metric matrix $W_1$ (shape $|E| \times |E|$) or positive diagonal weights
$w_e > 0$:
    $\langle u, v \rangle_{W_1} = u^T W_1 v$
    $\|u\|_{W_1}^2 = u^T W_1 u$

METRIC TYPE DISCLOSURE:
Ad hoc diagonal edge weights or arbitrary SPD matrices represent a weighted
$L_2$ cochain metric (`MetricType.DIAGONAL_L2` or `MetricType.GENERAL_SPD`).
They must NOT be termed the "canonical DEC Hodge star" $*_1$. In Discrete
Exterior Calculus (DEC), the canonical Hodge star $*_1$ requires a well-centered
primal-dual cell complex (such as a Delaunay-Voronoi mesh) where diagonal entries
equal the ratio of dual edge length to primal edge length ($|e^*| / |e|$).

Decomposition Components
------------------------
For any 1-cochain $\omega \in \mathbb{R}^{|E|}$, the orthogonal decomposition is:
    $\omega = \omega_{\text{exact}} + \omega_{\text{coexact}} + \omega_{\text{harm}}$

1. Exact component: $\omega_{\text{exact}} = d_0 \alpha$, where $\alpha \in \mathbb{R}^{|V|}$
   satisfies the normal equation $(d_0^T W_1 d_0) \alpha = d_0^T W_1 \omega$.
2. Coexact component: $\omega_{\text{coexact}} = W_1^{-1} d_1^T \gamma$, where $\gamma \in \mathbb{R}^{|F|}$
   satisfies $(d_1 W_1^{-1} d_1^T) \gamma = d_1 \omega$. If face weights $W_2$ are
   specified, stream function $\beta = W_2^{-1} \gamma$.
3. Harmonic component: $\omega_{\text{harm}} = \omega - \omega_{\text{exact}} - \omega_{\text{coexact}}$.
   Satisfies $d_1 \omega_{\text{harm}} = 0$ and $d_0^T W_1 \omega_{\text{harm}} = 0$.

Orthogonality and Energy Closure
--------------------------------
Because $d_1 @ d_0 = 0$ identically:
    $\langle \omega_{\text{exact}}, \omega_{\text{coexact}} \rangle_{W_1} = \alpha^T (d_1 d_0)^T \gamma = 0$ (algebraically exact).
    $\langle \omega_{\text{exact}}, \omega_{\text{harm}} \rangle_{W_1} = 0$.
    $\langle \omega_{\text{coexact}}, \omega_{\text{harm}} \rangle_{W_1} = 0$.
The total energy partitions exactly:
    $\|\omega\|_{W_1}^2 = \|\omega_{\text{exact}}\|_{W_1}^2 + \|\omega_{\text{coexact}}\|_{W_1}^2 + \|\omega_{\text{harm}}\|_{W_1}^2$.

Boundary Conditions and Zero-Interior-Node Handling
---------------------------------------------------
- `NATURAL` (or `ABSOLUTE` / `FREE`): standard unconstrained decomposition;
  $\alpha$ satisfies natural Neumann boundary conditions on the graph.
- `DIRICHLET_POTENTIAL`: potential $\alpha$ is constrained to zero on boundary
  vertices. In zero-interior-node cases (e.g. single triangle or open fan where
  all vertices touch the boundary), interior nodes count is zero, so $\alpha \equiv 0$
  and $\omega_{\text{exact}} \equiv 0$. This condition is detected and reported.

Complexes with Dependent Face Rows
----------------------------------
Closed 2-manifolds (e.g. sphere, torus) have $\sum_f d_{1, f} = 0$, making
$M = d_1 W_1^{-1} d_1^T$ rank-deficient. The solver applies minimum-norm
pseudoinverse solutions to handle dependent face rows cleanly without divergence.

Planar Embedding and Geometry Caveat
------------------------------------
$d_1 @ d_0 = 0$ is a purely combinatorial/algebraic incidence property of the
cochain complex. It does NOT prove that vertex coordinates form a valid planar
or surface embedding, nor does it guarantee Delaunay triangulation quality or
absence of self-intersections. Validated geometry is strictly required before
attributing any geometric or physical meaning. Outputs represent a sensor-space
algebraic decomposition and do NOT establish cortical sources, traveling
waves, or biological mechanisms.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import math
from typing import Any, Dict, Optional, Sequence, Tuple, Union

import numpy as np


ArrayLike = Union[Sequence[float], np.ndarray]


class BoundaryCondition(str, Enum):
    """Boundary condition policy for 2D cochain Hodge decomposition."""

    NATURAL = "natural"
    ABSOLUTE = "absolute"
    FREE = "free"
    DIRICHLET_POTENTIAL = "dirichlet_potential"
    RELATIVE = "relative"


class GaugePolicy(str, Enum):
    """Gauge fixing policy for the potential 0-cochain alpha."""

    MINIMUM_NORM = "minimum_norm"
    PINNED_VERTEX = "pinned_vertex"
    ZERO_MEAN = "zero_mean"


class MetricType(str, Enum):
    """Classification of the 1-cochain metric / Hodge star representation.

    DISCLOSURE:
    - DIAGONAL_L2: Ad hoc positive diagonal weights. NOT the canonical DEC star.
    - GENERAL_SPD: Full symmetric positive-definite metric matrix.
    - BARYCENTRIC_LUMPED: Dual-to-primal ratio from barycentric dual.
    - CIRCUMCENTRIC_DEC: True circumcentric DEC Hodge star (*_1 = |e*|/|e|),
      strictly requiring well-centered Delaunay dual geometry.
    """

    DIAGONAL_L2 = "diagonal_l2"
    GENERAL_SPD = "general_spd"
    BARYCENTRIC_LUMPED = "barycentric_lumped"
    CIRCUMCENTRIC_DEC = "circumcentric_dec"


class HodgeError(ValueError):
    """Base exception for Hodge decomposition errors."""


class CochainComplexError(HodgeError):
    """Raised when coboundary operators violate complex identities or dimensions."""


class MetricError(HodgeError):
    """Raised when metric weights or matrices are non-positive, non-finite, or non-SPD."""


class IllConditionedMetricError(MetricError):
    """Raised when normal matrices or metric weights exceed conditioning rejection thresholds."""


class BoundaryConditionError(HodgeError):
    """Raised when boundary condition parameters or configurations are invalid."""


@dataclass(frozen=True)
class HodgeResult:
    """Result of weighted 2D discrete Hodge-Helmholtz decomposition.

    Attributes:
        exact: Exact 1-cochain component omega_exact = d0 @ alpha, shape (|E|,).
        coexact: Coexact 1-cochain component omega_coexact = W1^{-1} d1^T gamma, shape (|E|,).
        harmonic: Harmonic 1-cochain component omega_harm, shape (|E|,).
        potential: Potential 0-cochain alpha on vertices, shape (|V|,).
        stream_function: Stream function 2-cochain beta on faces, shape (|F|,).
        energy_total: Total weighted energy ||omega||_{W1}^2.
        energy_exact: Exact component energy ||omega_exact||_{W1}^2.
        energy_coexact: Coexact component energy ||omega_coexact||_{W1}^2.
        energy_harmonic: Harmonic component energy ||omega_harm||_{W1}^2.
        orthogonality_exact_coexact: <omega_exact, omega_coexact>_{W1}.
        orthogonality_exact_harmonic: <omega_exact, omega_harm>_{W1}.
        orthogonality_coexact_harmonic: <omega_coexact, omega_harm>_{W1}.
        reconstruction_residual_norm: ||omega - (exact + coexact + harm)||_{W1}.
        relative_reconstruction_error: residual_norm / (||omega||_{W1} + eps).
        relative_energy_error: |E_total - sum(E_k)| / (E_total + eps).
        cond_L0: Effective condition number of L0 = d0^T W1 d0 on non-gauge subspace.
        cond_M: Effective condition number of M = d1 W1^{-1} d1^T, or None if |F| == 0.
        boundary_condition: Boundary condition applied.
        gauge: Gauge fixing policy applied.
        metric_type: Classification of the 1-cochain metric.
        diagnostics: Detailed numerical and topological diagnostics dictionary.
    """

    exact: np.ndarray
    coexact: np.ndarray
    harmonic: np.ndarray
    potential: np.ndarray
    stream_function: np.ndarray
    energy_total: float
    energy_exact: float
    energy_coexact: float
    energy_harmonic: float
    orthogonality_exact_coexact: float
    orthogonality_exact_harmonic: float
    orthogonality_coexact_harmonic: float
    reconstruction_residual_norm: float
    relative_reconstruction_error: float
    relative_energy_error: float
    cond_L0: float
    cond_M: Optional[float]
    boundary_condition: str
    gauge: str
    metric_type: str
    diagnostics: Dict[str, Any]

    # Interoperability properties aligning with audit and reference conventions
    @property
    def ortho_exact_coexact(self) -> float:
        """Alias for orthogonality_exact_coexact."""
        return self.orthogonality_exact_coexact

    @property
    def ortho_exact_harmonic(self) -> float:
        """Alias for orthogonality_exact_harmonic."""
        return self.orthogonality_exact_harmonic

    @property
    def ortho_coexact_harmonic(self) -> float:
        """Alias for orthogonality_coexact_harmonic."""
        return self.orthogonality_coexact_harmonic

    @property
    def stream_gamma(self) -> np.ndarray:
        """Alias for stream_function (unweighted face potential gamma)."""
        return self.stream_function

    @property
    def reconstruction_residual_w1(self) -> float:
        """Alias for reconstruction_residual_norm."""
        return self.reconstruction_residual_norm

    @property
    def accepted(self) -> bool:
        """Whether the numerical conditioning passed acceptance criteria."""
        return bool(self.diagnostics.get("accepted", True))

    @property
    def verdict(self) -> str:
        """Audit status verdict string (e.g. 'PASS_SYNTHETIC' or 'REJECTED_ILL_CONDITIONED')."""
        return str(self.diagnostics.get("verdict", "PASS_SYNTHETIC"))

    def as_dict(self) -> Dict[str, Any]:
        """Convert result to a serializable dictionary."""
        d = asdict(self)
        # Convert arrays to lists for serialization
        d["exact"] = self.exact.tolist()
        d["coexact"] = self.coexact.tolist()
        d["harmonic"] = self.harmonic.tolist()
        d["potential"] = self.potential.tolist()
        d["stream_function"] = self.stream_function.tolist()
        return d


def effective_condition_number(
    matrix: np.ndarray,
    *,
    relative_floor: float = 1e-14,
) -> Tuple[float, int]:
    r"""Compute condition number of a matrix restricted to its non-zero singular subspace.

    Graph Laplacians $L_0 = d_0^T W_1 d_0$ and boundary normal operators $M$
    often possess an exact algebraic kernel (e.g. constant potentials on connected
    components, or closed surface 2-cycles). Absolute singular value zero is
    therefore expected. This helper evaluates the effective condition number
    $\sigma_{\max} / \sigma_{\min, > 0}$.

    Args:
        matrix: 2D array, shape (M, N).
        relative_floor: Relative threshold relative to sigma_max below which
            singular values are treated as structural kernel.

    Returns:
        (effective_cond, effective_rank)
    """
    if matrix.size == 0 or matrix.shape[0] == 0 or matrix.shape[1] == 0:
        return 0.0, 0
    s = np.linalg.svd(matrix, compute_uv=False)
    if s.size == 0:
        return 0.0, 0
    s_max = float(np.max(s))
    if s_max == 0.0:
        return float("inf"), 0
    floor = s_max * relative_floor
    pos = s[s > floor]
    if pos.size == 0:
        return float("inf"), 0
    s_min_pos = float(np.min(pos))
    return float(s_max / s_min_pos), int(pos.size)


def validate_cochain_complex(
    d0: ArrayLike,
    d1: ArrayLike,
    *,
    atol: float = 0.0,
) -> float:
    """Validate shapes and the exact coboundary identity d1 @ d0 == 0.

    Args:
        d0: Edge-by-vertex incidence matrix, shape (|E|, |V|).
        d1: Face-by-edge incidence matrix, shape (|F|, |E|).
        atol: Maximum allowed absolute elementwise entry in d1 @ d0.

    Returns:
        Maximum absolute residual in d1 @ d0.

    Raises:
        CochainComplexError: If dimensions mismatch, non-finite entries exist,
            or the cochain identity d1 @ d0 == 0 is violated.
    """
    d0_arr = np.asarray(d0, dtype=float)
    d1_arr = np.asarray(d1, dtype=float)

    if d0_arr.ndim != 2:
        raise CochainComplexError(f"d0 must be 2D, got shape {d0_arr.shape}")
    if d1_arr.ndim != 2:
        raise CochainComplexError(f"d1 must be 2D, got shape {d1_arr.shape}")

    n_edges_d0, n_verts = d0_arr.shape
    n_faces, n_edges_d1 = d1_arr.shape

    if n_edges_d0 != n_edges_d1:
        raise CochainComplexError(
            f"Edge dimension mismatch: d0 has {n_edges_d0} edges, "
            f"d1 has {n_edges_d1} edges."
        )

    if not np.all(np.isfinite(d0_arr)):
        raise CochainComplexError("d0 contains non-finite entries.")
    if not np.all(np.isfinite(d1_arr)):
        raise CochainComplexError("d1 contains non-finite entries.")

    if n_faces == 0 or n_edges_d0 == 0 or n_verts == 0:
        return 0.0

    prod = d1_arr @ d0_arr
    max_res = float(np.max(np.abs(prod)))
    if max_res > atol:
        raise CochainComplexError(
            f"Cochain identity d1 @ d0 == 0 violated: max|d1 @ d0| = {max_res:.6e} > tol {atol}"
        )
    return max_res


def validate_edge_metric(
    edge_metric: Optional[ArrayLike],
    num_edges: int,
    *,
    atol: float = 1e-12,
) -> Tuple[np.ndarray, np.ndarray, bool]:
    """Validate 1-cochain metric W1 and compute its inverse.

    Args:
        edge_metric: None (uniform identity), 1D array of positive weights (shape (|E|,)),
            or 2D symmetric positive-definite matrix (shape (|E|, |E|)).
        num_edges: Number of edges |E|.
        atol: Tolerance for symmetry check.

    Returns:
        (W1, W1_inv, is_diagonal)
        - If is_diagonal: W1 and W1_inv are 1D arrays of length |E|.
        - If not is_diagonal: W1 and W1_inv are 2D arrays of shape (|E|, |E|).

    Raises:
        MetricError: If metric is non-positive, non-finite, non-symmetric, or non-SPD.
    """
    if num_edges == 0:
        return np.zeros(0, dtype=float), np.zeros(0, dtype=float), True

    if edge_metric is None:
        w = np.ones(num_edges, dtype=float)
        return w, w.copy(), True

    arr = np.asarray(edge_metric, dtype=float)
    if not np.all(np.isfinite(arr)):
        raise MetricError("edge_metric contains non-finite values (NaN or Inf).")

    if arr.ndim == 1:
        if arr.shape != (num_edges,):
            raise MetricError(
                f"1D edge_metric length {arr.shape[0]} does not match num_edges {num_edges}."
            )
        if np.any(arr <= 0.0):
            raise MetricError("Diagonal edge metric elements must be strictly positive.")
        return arr, 1.0 / arr, True

    elif arr.ndim == 2:
        if arr.shape != (num_edges, num_edges):
            raise MetricError(
                f"2D edge_metric shape {arr.shape} does not match ({num_edges}, {num_edges})."
            )
        # Symmetry check
        sym_diff = np.max(np.abs(arr - arr.T))
        if sym_diff > atol:
            raise MetricError(f"2D edge_metric is not symmetric: max|W - W^T| = {sym_diff:.6e}")
        # Positive definiteness check via Cholesky or eigenvalues
        try:
            chol = np.linalg.cholesky(arr)
            # Invert via Cholesky factor
            chol_inv = np.linalg.inv(chol)
            w1_inv = chol_inv.T @ chol_inv
        except np.linalg.LinAlgError as exc:
            # Check eigenvalues to provide exact reason
            eigvals = np.linalg.eigvalsh(arr)
            min_eig = float(np.min(eigvals))
            raise MetricError(
                f"2D edge_metric is not positive definite: min eigenvalue = {min_eig:.6e}"
            ) from exc
        return arr, w1_inv, False

    else:
        raise MetricError(f"edge_metric must be 1D or 2D, got {arr.ndim}D array.")


def detect_boundary_elements(
    d0: np.ndarray,
    d1: np.ndarray,
) -> Tuple[np.ndarray, np.ndarray]:
    """Detect boundary edges and boundary vertices from coboundary operators.

    In an oriented 2-complex:
    - An edge is a boundary edge if it appears in the boundary of exactly ONE face
      (i.e. the corresponding column in d1 has exactly 1 non-zero entry).
    - A vertex is a boundary vertex if it is an endpoint of at least one boundary edge
      (i.e. d0 has a non-zero entry at that vertex for a boundary edge).

    Args:
        d0: Edge-by-vertex incidence matrix, shape (|E|, |V|).
        d1: Face-by-edge incidence matrix, shape (|F|, |E|).

    Returns:
        (boundary_edges_mask, boundary_vertices_mask) as boolean 1D arrays.
    """
    n_edges, n_verts = d0.shape
    n_faces = d1.shape[0]

    if n_edges == 0:
        return np.zeros(0, dtype=bool), np.zeros(n_verts, dtype=bool)

    if n_faces == 0:
        # 1-skeleton graph: all edges and vertices are boundary
        return np.ones(n_edges, dtype=bool), np.ones(n_verts, dtype=bool)

    # Count faces incident to each edge
    face_counts = np.sum(d1 != 0, axis=0)
    boundary_edges_mask = face_counts == 1

    # Find vertices attached to boundary edges
    boundary_vertices_mask = np.zeros(n_verts, dtype=bool)
    if np.any(boundary_edges_mask):
        sub_d0 = d0[boundary_edges_mask, :]
        attached = np.any(sub_d0 != 0, axis=0)
        boundary_vertices_mask = attached

    return boundary_edges_mask, boundary_vertices_mask


def weighted_inner_product(
    metric: np.ndarray,
    u: np.ndarray,
    v: np.ndarray,
    *,
    is_diagonal: Optional[bool] = None,
) -> float:
    """Compute inner product <u, v>_{W1} = u^T W1 v."""
    if is_diagonal is None:
        is_diagonal = metric.ndim == 1
    if is_diagonal:
        return float(np.sum(metric * u * v))
    return float(u.T @ metric @ v)


def weighted_norm_sq(
    metric: np.ndarray,
    u: np.ndarray,
    *,
    is_diagonal: Optional[bool] = None,
) -> float:
    """Compute squared norm ||u||_{W1}^2 = u^T W1 u."""
    return weighted_inner_product(metric, u, u, is_diagonal=is_diagonal)


def _as_vertex_boundary_mask(boundary_vertices: ArrayLike, num_verts: int) -> np.ndarray:
    """Interpret ``boundary_vertices`` as a boolean mask or integer index list.

    Rules (fail-closed):
    - bool dtype / boolean array of shape ``(|V|,)`` → used as mask.
    - integer/float array of shape ``(|V|,)`` with only {0,1} values → 0/1 mask.
    - any other 1-D integer index array (including length ``|V|`` with values
      outside {0,1}, e.g. ``[0,1,2]``) → index list (those vertices True).
    - duplicate indices allowed; out-of-range indices raise.
    """
    arr = np.asarray(boundary_vertices)
    if arr.ndim != 1:
        raise BoundaryConditionError(
            f"boundary_vertices must be 1-D; got shape {arr.shape}"
        )
    if arr.dtype == bool or arr.dtype == np.bool_:
        if arr.shape != (num_verts,):
            raise BoundaryConditionError(
                f"boundary_vertices mask shape {arr.shape} != ({num_verts},)"
            )
        return arr.astype(bool, copy=False)

    if not np.issubdtype(arr.dtype, np.number) or not np.all(np.isfinite(arr)):
        raise BoundaryConditionError("boundary_vertices must be finite numeric or bool")

    # Same-length {0,1}-only arrays are treated as explicit 0/1 masks.
    if arr.shape == (num_verts,) and np.all((arr == 0) | (arr == 1)):
        return arr.astype(bool)

    # Otherwise interpret as vertex indices.
    if not np.allclose(arr, np.rint(arr), rtol=0.0, atol=0.0):
        raise BoundaryConditionError(
            "boundary_vertices index list must be integer-valued"
        )
    idx = np.rint(arr).astype(np.int64, copy=False)
    if idx.size and (np.any(idx < 0) or np.any(idx >= num_verts)):
        raise BoundaryConditionError(
            f"boundary_vertices indices out of range for num_verts={num_verts}"
        )
    mask = np.zeros(num_verts, dtype=bool)
    if idx.size:
        mask[idx] = True
    return mask


def _apply_metric_w1(
    w1: np.ndarray,
    is_diagonal: bool,
    vec: np.ndarray,
) -> np.ndarray:
    """Compute W1 @ vec."""
    if is_diagonal:
        return w1 * vec
    return w1 @ vec


def _apply_metric_inv_w1(
    w1_inv: np.ndarray,
    is_diagonal: bool,
    vec: np.ndarray,
) -> np.ndarray:
    """Compute W1^{-1} @ vec."""
    if is_diagonal:
        return w1_inv * vec
    return w1_inv @ vec


def hodge_decompose(
    edge_cochain: ArrayLike,
    d0: ArrayLike,
    d1: ArrayLike,
    edge_metric: Optional[ArrayLike] = None,
    *,
    boundary_condition: Union[BoundaryCondition, str] = BoundaryCondition.NATURAL,
    gauge: Union[GaugePolicy, str] = GaugePolicy.MINIMUM_NORM,
    face_metric: Optional[ArrayLike] = None,
    vertex_metric: Optional[ArrayLike] = None,
    boundary_vertices: Optional[ArrayLike] = None,
    cond_reject: float = 1e12,
    fail_on_ill_conditioned: bool = False,
    metric_type: Optional[Union[MetricType, str]] = None,
    atol: float = 1e-8,
    eps: float = 1e-12,
) -> HodgeResult:
    """Compute the weighted discrete Hodge-Helmholtz decomposition of a 1-cochain.

    Mathematical Formulation:
        Let W1 be the symmetric positive-definite metric on 1-cochains.
        omega = omega_exact + omega_coexact + omega_harm

        1. Exact component:
           omega_exact = d0 @ alpha
           (d0^T W1 d0) alpha = d0^T W1 omega
        2. Coexact component:
           omega_coexact = W1^{-1} d1^T gamma
           (d1 W1^{-1} d1^T) gamma = d1 @ omega
           stream_function beta = W2^{-1} gamma (if face_metric W2 provided, else gamma)
        3. Harmonic component:
           omega_harm = omega - omega_exact - omega_coexact

    Args:
        edge_cochain: 1-cochain omega on oriented edges, shape (|E|,).
        d0: Coboundary operator d0, shape (|E|, |V|).
        d1: Coboundary operator d1, shape (|F|, |E|).
        edge_metric: Optional edge metric W1. Can be None (uniform weights 1.0),
            a 1D array of positive weights (shape (|E|,)), or a 2D SPD matrix
            (shape (|E|, |E|)).
        boundary_condition: Boundary condition policy. Supports:
            - `BoundaryCondition.NATURAL` / `"natural"` / `"absolute"` / `"free"`:
              Standard unconstrained decomposition with natural boundary conditions.
            - `BoundaryCondition.DIRICHLET_POTENTIAL` / `"dirichlet_potential"`:
              Constrains alpha = 0 on boundary vertices. Handles zero interior
              node cases gracefully (alpha = 0).
            - `BoundaryCondition.RELATIVE` / `"relative"`:
              Relative cohomology formulation.
        gauge: Gauge fixing policy for potential alpha. Supports:
            - `GaugePolicy.MINIMUM_NORM` / `"minimum_norm"`: Minimum Euclidean norm alpha.
            - `GaugePolicy.PINNED_VERTEX` / `"pinned_vertex"`: Pinned reference vertex (alpha[0]=0).
            - `GaugePolicy.ZERO_MEAN` / `"zero_mean"`: Shifts alpha to zero mean.
        face_metric: Optional positive diagonal weights on 2-cells (faces), shape (|F|,).
        vertex_metric: Optional positive diagonal weights on 0-cells (vertices),
            shape (|V|,). Validated when provided. Used for weighted ZERO_MEAN
            gauge. Note: the W1 exact normal equation
            ``(d0.T W1 d0) α = d0.T W1 ω`` is independent of a diagonal ``*0``
            (it cancels), so NATURAL / PINNED_VERTEX exact components are
            unchanged by ``vertex_metric``; this is recorded in diagnostics
            rather than silently dropped.
        boundary_vertices: Optional boolean mask (shape ``(|V|,)``) **or** a
            1-D list/array of integer vertex indices to constrain under
            ``DIRICHLET_POTENTIAL``. Same-length integer index vectors are
            interpreted as indices, not as 0/1 masks. If None, automatically
            detected from d0 and d1.
        cond_reject: Rejection threshold for condition numbers of normal operators.
        fail_on_ill_conditioned: If True, raises IllConditionedMetricError when
            conditioning exceeds cond_reject; if False, flags diagnostics.
        metric_type: Explicit classification of metric (e.g. DIAGONAL_L2, GENERAL_SPD,
            CIRCUMCENTRIC_DEC). If None, automatically inferred.
        atol: Tolerance for cochain complex identity and zero residuals.
        eps: Small epsilon for relative error denominators.

    Returns:
        HodgeResult dataclass with components, energies, orthogonalities, and diagnostics.

    Raises:
        CochainComplexError: If d0/d1 shapes mismatch or d1 @ d0 != 0.
        MetricError: If edge_metric is non-positive, non-finite, or non-SPD.
        IllConditionedMetricError: If fail_on_ill_conditioned is True and conditioning is poor.
        BoundaryConditionError: If boundary parameters are invalid.
    """
    # 1. Parse and validate boundary condition
    if isinstance(boundary_condition, str):
        bc_str = boundary_condition.lower()
        if bc_str in ("natural", "absolute", "free"):
            bc = BoundaryCondition.NATURAL
        elif bc_str in ("dirichlet_potential", "dirichlet"):
            bc = BoundaryCondition.DIRICHLET_POTENTIAL
        elif bc_str in ("relative",):
            bc = BoundaryCondition.RELATIVE
        else:
            raise BoundaryConditionError(f"Unsupported boundary condition: {boundary_condition}")
    elif isinstance(boundary_condition, BoundaryCondition):
        bc = boundary_condition
    else:
        raise BoundaryConditionError(f"Invalid boundary condition type: {type(boundary_condition)}")

    # 2. Parse and validate gauge policy
    if isinstance(gauge, str):
        gauge_str = gauge.lower()
        if gauge_str in ("minimum_norm", "pinv", "min_norm"):
            gp = GaugePolicy.MINIMUM_NORM
        elif gauge_str in ("pinned_vertex", "pinned", "reference_node"):
            gp = GaugePolicy.PINNED_VERTEX
        elif gauge_str in ("zero_mean", "mean_zero"):
            gp = GaugePolicy.ZERO_MEAN
        else:
            raise HodgeError(f"Unsupported gauge policy: {gauge}")
    elif isinstance(gauge, GaugePolicy):
        gp = gauge
    else:
        raise HodgeError(f"Invalid gauge policy type: {type(gauge)}")

    # 3. Validate cochain complex and dimensions
    d0_arr = np.asarray(d0, dtype=float)
    d1_arr = np.asarray(d1, dtype=float)
    validate_cochain_complex(d0_arr, d1_arr, atol=atol)

    num_edges, num_verts = d0_arr.shape
    num_faces = d1_arr.shape[0]

    omega_arr = np.asarray(edge_cochain, dtype=float)
    if omega_arr.ndim != 1 or omega_arr.shape != (num_edges,):
        raise CochainComplexError(
            f"edge_cochain shape {omega_arr.shape} does not match num_edges {num_edges}."
        )
    if not np.all(np.isfinite(omega_arr)):
        raise CochainComplexError("edge_cochain contains non-finite entries (NaN or Inf).")

    # 4. Validate and prepare edge metric W1
    w1, w1_inv, is_diag = validate_edge_metric(edge_metric, num_edges, atol=atol)

    # Inferred or user-specified metric type
    if metric_type is None:
        m_type = MetricType.DIAGONAL_L2 if is_diag else MetricType.GENERAL_SPD
    elif isinstance(metric_type, str):
        m_type = MetricType(metric_type.lower())
    else:
        m_type = metric_type

    # Validate face weights if provided
    if face_metric is not None:
        w_faces = np.asarray(face_metric, dtype=float)
        if w_faces.shape != (num_faces,):
            raise MetricError(f"face_metric shape {w_faces.shape} != ({num_faces},)")
        if not np.all(np.isfinite(w_faces)) or np.any(w_faces <= 0.0):
            raise MetricError("face_metric must contain strictly positive finite values.")
    else:
        w_faces = np.ones(num_faces, dtype=float)

    # Validate vertex metric (*0 diagonal). Not silently ignored.
    w_verts: Optional[np.ndarray]
    if vertex_metric is not None:
        w_verts = np.asarray(vertex_metric, dtype=float)
        if w_verts.ndim != 1 or w_verts.shape != (num_verts,):
            raise MetricError(f"vertex_metric shape {w_verts.shape} != ({num_verts},)")
        if not np.all(np.isfinite(w_verts)) or np.any(w_verts <= 0.0):
            raise MetricError("vertex_metric must contain strictly positive finite values.")
    else:
        w_verts = None

    # Base diagnostics
    diagnostics: Dict[str, Any] = {
        "num_vertices": num_verts,
        "num_edges": num_edges,
        "num_faces": num_faces,
        "boundary_condition": bc.value,
        "gauge": gp.value,
        "metric_type": m_type.value,
        "is_diagonal_metric": is_diag,
        "vertex_metric_provided": w_verts is not None,
        "vertex_metric_used_for_zero_mean_gauge": False,
        "vertex_metric_alters_W1_exact_normal_equations": False,
        "hold_posture": "HOLD / SYNTHETIC_ONLY",
        "scientific_claim_disclaimer": "Algebraic 2D Hodge decomposition; no biological or clinical claims.",
        "planar_embedding_proven": False,
        "sensor_space_algebraic_only": True,
    }

    # Handle empty edge case
    if num_edges == 0:
        zeros_v = np.zeros(num_verts, dtype=float)
        zeros_e = np.zeros(0, dtype=float)
        zeros_f = np.zeros(num_faces, dtype=float)
        diagnostics["accepted"] = True
        diagnostics["verdict"] = "PASS_SYNTHETIC"
        return HodgeResult(
            exact=zeros_e,
            coexact=zeros_e,
            harmonic=zeros_e,
            potential=zeros_v,
            stream_function=zeros_f,
            energy_total=0.0,
            energy_exact=0.0,
            energy_coexact=0.0,
            energy_harmonic=0.0,
            orthogonality_exact_coexact=0.0,
            orthogonality_exact_harmonic=0.0,
            orthogonality_coexact_harmonic=0.0,
            reconstruction_residual_norm=0.0,
            relative_reconstruction_error=0.0,
            relative_energy_error=0.0,
            cond_L0=0.0,
            cond_M=None,
            boundary_condition=bc.value,
            gauge=gp.value,
            metric_type=m_type.value,
            diagnostics=diagnostics,
        )

    # Detect boundary elements
    b_edges_mask, b_verts_mask = detect_boundary_elements(d0_arr, d1_arr)
    num_boundary_edges = int(np.sum(b_edges_mask))
    num_boundary_verts = int(np.sum(b_verts_mask))
    num_interior_verts = num_verts - num_boundary_verts

    diagnostics["num_boundary_edges"] = num_boundary_edges
    diagnostics["num_boundary_vertices"] = num_boundary_verts
    diagnostics["num_interior_vertices"] = num_interior_verts
    diagnostics["zero_interior_nodes"] = (num_interior_verts == 0)

    # 5. Normal operators
    # L0 = d0^T @ W1 @ d0
    if is_diag:
        # Vectorized diagonal formulation
        L0 = d0_arr.T @ (w1[:, None] * d0_arr)
        rhs_alpha = d0_arr.T @ (w1 * omega_arr)
        weight_ratio = float(np.max(w1) / np.min(w1))
    else:
        L0 = d0_arr.T @ w1 @ d0_arr
        rhs_alpha = d0_arr.T @ (w1 @ omega_arr)
        eigvals_w1 = np.linalg.eigvalsh(w1)
        weight_ratio = float(np.max(eigvals_w1) / np.min(eigvals_w1))

    cond_L0, rank_L0 = effective_condition_number(L0)
    diagnostics["cond_L0"] = cond_L0
    diagnostics["rank_L0_effective"] = rank_L0
    diagnostics["weight_ratio"] = weight_ratio

    # M = d1 @ W1^{-1} @ d1^T
    cond_M: Optional[float] = None
    rank_M = 0
    if num_faces > 0:
        if is_diag:
            M = d1_arr @ (w1_inv[:, None] * d1_arr.T)
        else:
            M = d1_arr @ w1_inv @ d1_arr.T
        cond_M, rank_M = effective_condition_number(M)
        diagnostics["cond_M"] = cond_M
        diagnostics["rank_M_effective"] = rank_M
        diagnostics["dependent_face_rows"] = (rank_M < num_faces)
    else:
        M = np.zeros((0, 0), dtype=float)
        diagnostics["cond_M"] = None
        diagnostics["rank_M_effective"] = 0
        diagnostics["dependent_face_rows"] = False

    # Check conditioning rejection criteria
    weight_ratio_thresh = math.sqrt(cond_reject)
    reject_reason = None
    if weight_ratio > weight_ratio_thresh:
        reject_reason = f"weight_ratio {weight_ratio:.2e} > threshold {weight_ratio_thresh:.2e}"
    elif cond_L0 > cond_reject:
        reject_reason = f"cond_L0 {cond_L0:.2e} > threshold {cond_reject:.2e}"
    elif cond_M is not None and cond_M > cond_reject:
        reject_reason = f"cond_M {cond_M:.2e} > threshold {cond_reject:.2e}"

    if reject_reason is not None:
        diagnostics["accepted"] = False
        diagnostics["verdict"] = "REJECTED_ILL_CONDITIONED"
        diagnostics["reject_reason"] = reject_reason
        if fail_on_ill_conditioned:
            raise IllConditionedMetricError(
                f"Metric conditioning rejected: {reject_reason}"
            )
    else:
        diagnostics["accepted"] = True
        diagnostics["verdict"] = "PASS_SYNTHETIC"

    # 6. Solve for exact component alpha
    alpha = np.zeros(num_verts, dtype=float)

    if bc == BoundaryCondition.DIRICHLET_POTENTIAL:
        # Dirichlet potential: alpha = 0 on boundary vertices
        if boundary_vertices is not None:
            dirichlet_mask = _as_vertex_boundary_mask(boundary_vertices, num_verts)
        else:
            dirichlet_mask = b_verts_mask

        interior_indices = np.where(~dirichlet_mask)[0]
        if interior_indices.size == 0:
            # Zero-interior-node case: all vertices are Dirichlet boundary vertices!
            # Exact component alpha is constrained to 0 everywhere.
            alpha = np.zeros(num_verts, dtype=float)
            diagnostics["dirichlet_all_boundary"] = True
        else:
            # Solve reduced system on interior vertices
            L0_sub = L0[np.ix_(interior_indices, interior_indices)]
            rhs_sub = rhs_alpha[interior_indices]
            alpha_sub, _, _, _ = np.linalg.lstsq(L0_sub, rhs_sub, rcond=None)
            alpha[interior_indices] = alpha_sub

    elif bc == BoundaryCondition.RELATIVE:
        raise NotImplementedError(
            "BoundaryCondition.RELATIVE is reserved for future cell-complex releases; "
            "use BoundaryCondition.NATURAL or BoundaryCondition.DIRICHLET_POTENTIAL."
        )

    else:
        # Natural / Absolute boundary conditions: solve on all vertices
        if gp == GaugePolicy.MINIMUM_NORM:
            alpha, _, _, _ = np.linalg.lstsq(L0, rhs_alpha, rcond=None)
        elif gp == GaugePolicy.PINNED_VERTEX:
            # Pin vertex 0 to 0 (or solve on 1..V-1)
            if num_verts > 1:
                idx = np.arange(1, num_verts)
                L0_sub = L0[np.ix_(idx, idx)]
                rhs_sub = rhs_alpha[idx]
                alpha_sub, _, _, _ = np.linalg.lstsq(L0_sub, rhs_sub, rcond=None)
                alpha[idx] = alpha_sub
                alpha[0] = 0.0
            else:
                alpha = np.zeros(1, dtype=float)
        elif gp == GaugePolicy.ZERO_MEAN:
            # Solve minimum-norm and then center mean to 0 (optionally mass-weighted)
            alpha, _, _, _ = np.linalg.lstsq(L0, rhs_alpha, rcond=None)
            if w_verts is not None:
                mass = float(np.sum(w_verts))
                alpha = alpha - float(np.sum(w_verts * alpha) / mass)
                diagnostics["vertex_metric_used_for_zero_mean_gauge"] = True
            else:
                alpha = alpha - float(np.mean(alpha))

    omega_exact = d0_arr @ alpha

    # 7. Solve for coexact component gamma and stream function beta
    if num_faces > 0:
        rhs_gamma = d1_arr @ omega_arr
        # M is symmetric positive semidefinite; lstsq provides the minimum-norm gamma
        # even when face rows are linearly dependent (closed surfaces, 2-cycles)
        gamma, _, _, _ = np.linalg.lstsq(M, rhs_gamma, rcond=None)
        d1_t_gamma = d1_arr.T @ gamma
        omega_coexact = _apply_metric_inv_w1(w1_inv, is_diag, d1_t_gamma)
        beta = gamma / w_faces
    else:
        gamma = np.zeros(0, dtype=float)
        omega_coexact = np.zeros(num_edges, dtype=float)
        beta = np.zeros(0, dtype=float)

    # 8. Harmonic component
    omega_harm = omega_arr - omega_exact - omega_coexact

    # 9. Energies and Inner Products
    e_tot = weighted_norm_sq(w1, omega_arr, is_diagonal=is_diag)
    e_ex = weighted_norm_sq(w1, omega_exact, is_diagonal=is_diag)
    e_co = weighted_norm_sq(w1, omega_coexact, is_diagonal=is_diag)
    e_harm = weighted_norm_sq(w1, omega_harm, is_diagonal=is_diag)

    o_ex_co = weighted_inner_product(w1, omega_exact, omega_coexact, is_diagonal=is_diag)
    o_ex_harm = weighted_inner_product(w1, omega_exact, omega_harm, is_diagonal=is_diag)
    o_co_harm = weighted_inner_product(w1, omega_coexact, omega_harm, is_diagonal=is_diag)

    reconstruction_residual = omega_arr - (omega_exact + omega_coexact + omega_harm)
    res_norm = math.sqrt(max(weighted_norm_sq(w1, reconstruction_residual, is_diagonal=is_diag), 0.0))
    tot_norm = math.sqrt(max(e_tot, 0.0))

    rel_rec_err = res_norm / (tot_norm + eps)
    sum_energies = e_ex + e_co + e_harm
    rel_energy_err = abs(e_tot - sum_energies) / (e_tot + eps)

    # Check cochain exactness and coclosedness residuals of harmonic component
    if num_faces > 0:
        d1_harm = d1_arr @ omega_harm
        max_d1_harm = float(np.max(np.abs(d1_harm)))
    else:
        max_d1_harm = 0.0

    delta0_harm = d0_arr.T @ _apply_metric_w1(w1, is_diag, omega_harm)
    max_delta0_harm = float(np.max(np.abs(delta0_harm)))
    interior_indices_diag = np.where(~b_verts_mask)[0]
    if interior_indices_diag.size > 0:
        max_delta0_harm_interior = float(np.max(np.abs(delta0_harm[interior_indices_diag])))
    else:
        max_delta0_harm_interior = 0.0

    diagnostics["max_abs_d1_harmonic"] = max_d1_harm
    diagnostics["max_abs_delta0_harmonic"] = max_delta0_harm
    diagnostics["max_abs_delta0_harmonic_interior"] = max_delta0_harm_interior
    diagnostics["harmonic_is_closed"] = (max_d1_harm <= atol)
    if bc == BoundaryCondition.DIRICHLET_POTENTIAL:
        diagnostics["harmonic_is_coclosed"] = (max_delta0_harm_interior <= atol)
    else:
        diagnostics["harmonic_is_coclosed"] = (max_delta0_harm <= atol)

    return HodgeResult(
        exact=omega_exact,
        coexact=omega_coexact,
        harmonic=omega_harm,
        potential=alpha,
        stream_function=beta,
        energy_total=e_tot,
        energy_exact=e_ex,
        energy_coexact=e_co,
        energy_harmonic=e_harm,
        orthogonality_exact_coexact=o_ex_co,
        orthogonality_exact_harmonic=o_ex_harm,
        orthogonality_coexact_harmonic=o_co_harm,
        reconstruction_residual_norm=res_norm,
        relative_reconstruction_error=rel_rec_err,
        relative_energy_error=rel_energy_err,
        cond_L0=cond_L0,
        cond_M=cond_M,
        boundary_condition=bc.value,
        gauge=gp.value,
        metric_type=m_type.value,
        diagnostics=diagnostics,
    )


__all__ = [
    "BoundaryCondition",
    "GaugePolicy",
    "MetricType",
    "HodgeError",
    "CochainComplexError",
    "MetricError",
    "IllConditionedMetricError",
    "BoundaryConditionError",
    "HodgeResult",
    "effective_condition_number",
    "validate_cochain_complex",
    "validate_edge_metric",
    "detect_boundary_elements",
    "weighted_inner_product",
    "weighted_norm_sq",
    "hodge_decompose",
]
