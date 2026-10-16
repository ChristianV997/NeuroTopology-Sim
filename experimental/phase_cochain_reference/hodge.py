"""Weighted Hodge-Helmholtz decomposition on simplicial 1-cochains.

Decomposes a 1-cochain omega into mutually orthogonal components:
    omega = omega_exact + omega_coexact + omega_harmonic
          = d0(alpha) + delta2(beta) + h
under the weighted inner product <u, v>_{W1} = u.T @ W1 @ v.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence
import numpy as np

from .complex import SimplicialComplex


@dataclass(frozen=True)
class HodgeDecomposition:
    """Results of a weighted Hodge-Helmholtz decomposition on 1-cochains.

    Attributes:
        exact: Curl-free / gradient 1-cochain d0(alpha), shape (|E|,).
        coexact: Divergence-free / solenoidal 1-cochain delta2(beta), shape (|E|,).
        harmonic: Harmonic 1-cochain h in ker(delta1) cap ker(d1), shape (|E|,).
        potential: 0-cochain alpha, shape (|V|,).
        stream_function: 2-cochain beta, shape (|T|,).
        energy_total: ||omega||_{W1}^2.
        energy_exact: ||omega_exact||_{W1}^2.
        energy_coexact: ||omega_coexact||_{W1}^2.
        energy_harmonic: ||omega_harmonic||_{W1}^2.
        orthogonality_exact_coexact: <omega_exact, omega_coexact>_{W1}.
        orthogonality_exact_harmonic: <omega_exact, omega_harmonic>_{W1}.
        orthogonality_coexact_harmonic: <omega_coexact, omega_harmonic>_{W1}.
        reconstruction_residual_norm: ||omega - (exact + coexact + harmonic)||_{W1}.
        relative_reconstruction_error: residual / (||omega||_{W1} + eps).
        relative_energy_error: |E_total - sum(E_k)| / (E_total + eps).
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


def compute_weighted_hodge_decomposition(
    complex_: SimplicialComplex,
    omega: np.ndarray | Sequence[float],
    weights_edges: np.ndarray | Sequence[float] | None = None,
    weights_faces: np.ndarray | Sequence[float] | None = None,
    weights_vertices: np.ndarray | Sequence[float] | None = None,
    eps: float = 1e-12,
) -> HodgeDecomposition:
    """Compute the weighted discrete Hodge-Helmholtz decomposition of a 1-cochain.

    Mathematical Formulation:
        Let W0 = diag(w_v), W1 = diag(w_e), W2 = diag(w_t) be positive metric weights.
        The weighted inner product on 1-forms is <u, v>_{W1} = u^T W1 v.
        Adjoints (codifferentials):
            delta1 = W0^{-1} d0^T W1 : C^1 -> C^0
            delta2 = W1^{-1} d1^T W2 : C^2 -> C^1

        Decomposition:
            omega = d0(alpha) + W1^{-1} d1^T W2 beta + h

        Solving for exact component (alpha):
            (d0^T W1 d0) alpha = d0^T W1 omega
            omega_exact = d0 @ alpha

        Solving for coexact component (beta):
            Let gamma = W2 @ beta.
            (d1 W1^{-1} d1^T) gamma = d1 @ omega
            omega_coexact = W1^{-1} d1^T gamma
            beta = W2^{-1} @ gamma

        Harmonic component:
            h = omega - omega_exact - omega_coexact

        Orthogonality:
            <omega_exact, omega_coexact>_{W1} = alpha^T (d1 d0)^T gamma == 0
            because d1 @ d0 == 0 identically!

    Args:
        complex_: Simplicial complex.
        omega: 1-cochain values on edges, shape (|E|,).
        weights_edges: Positive weights on edges, shape (|E|,). Defaults to 1.0.
        weights_faces: Positive weights on faces, shape (|T|,). Defaults to 1.0.
        weights_vertices: Positive weights on vertices, shape (|V|,). Defaults to 1.0.
        eps: Small tolerance for relative metrics.

    Returns:
        HodgeDecomposition containing components, potentials, energies, and diagnostic errors.
    """
    w1_arr = np.asarray(omega, dtype=float)
    if w1_arr.shape != (complex_.num_edges,):
        raise ValueError(f"omega shape {w1_arr.shape} does not match complex num_edges {complex_.num_edges}")
    if not np.all(np.isfinite(w1_arr)):
        raise ValueError("omega must contain finite numerical values.")

    num_v = complex_.num_vertices
    num_e = complex_.num_edges
    num_t = complex_.num_triangles

    # Validate weights
    if weights_edges is None:
        w_e = np.ones(num_e, dtype=float)
    else:
        w_e = np.asarray(weights_edges, dtype=float)
        if w_e.shape != (num_e,):
            raise ValueError(f"weights_edges shape {w_e.shape} does not match num_edges {num_e}")
        if np.any(w_e <= 0.0) or not np.all(np.isfinite(w_e)):
            raise ValueError("Edge weights must be strictly positive and finite.")

    if weights_faces is None:
        w_t = np.ones(num_t, dtype=float)
    else:
        w_t = np.asarray(weights_faces, dtype=float)
        if w_t.shape != (num_t,):
            raise ValueError(f"weights_faces shape {w_t.shape} does not match num_triangles {num_t}")
        if np.any(w_t <= 0.0) or not np.all(np.isfinite(w_t)):
            raise ValueError("Face weights must be strictly positive and finite.")

    if weights_vertices is None:
        w_v = np.ones(num_v, dtype=float)
    else:
        w_v = np.asarray(weights_vertices, dtype=float)
        if w_v.shape != (num_v,):
            raise ValueError(f"weights_vertices shape {w_v.shape} does not match num_vertices {num_v}")
        if np.any(w_v <= 0.0) or not np.all(np.isfinite(w_v)):
            raise ValueError("Vertex weights must be strictly positive and finite.")

    # Handle edge case: empty complex
    if num_e == 0:
        zeros_0 = np.zeros(num_v, dtype=float)
        zeros_1 = np.zeros(0, dtype=float)
        zeros_2 = np.zeros(num_t, dtype=float)
        return HodgeDecomposition(
            exact=zeros_1,
            coexact=zeros_1,
            harmonic=zeros_1,
            potential=zeros_0,
            stream_function=zeros_2,
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
        )

    d0 = complex_.d0
    d1 = complex_.d1

    W1 = np.diag(w_e)
    W1_inv = np.diag(1.0 / w_e)

    # 1. Exact component: (d0^T W1 d0) alpha = d0^T W1 omega
    L0 = d0.T @ W1 @ d0  # Weighted graph Laplacian
    rhs_alpha = d0.T @ (w_e * w1_arr)
    # Solve via minimum-norm least-squares (handles rank deficiency from gauge invariance)
    alpha, _, _, _ = np.linalg.lstsq(L0, rhs_alpha, rcond=None)
    omega_exact = d0 @ alpha

    # 2. Coexact component: (d1 W1^{-1} d1^T) gamma = d1 @ omega
    if num_t > 0:
        M = d1 @ W1_inv @ d1.T  # Shape (|T|, |T|)
        rhs_gamma = d1 @ w1_arr
        gamma, _, _, _ = np.linalg.lstsq(M, rhs_gamma, rcond=None)
        omega_coexact = (1.0 / w_e) * (d1.T @ gamma)
        beta = gamma / w_t
    else:
        omega_coexact = np.zeros(num_e, dtype=float)
        beta = np.zeros(0, dtype=float)

    # 3. Harmonic component: h = omega - omega_exact - omega_coexact
    h = w1_arr - omega_exact - omega_coexact

    # Energies and inner products: <u, v>_{W1} = u.T @ (w_e * v)
    def w1_inner(u: np.ndarray, v: np.ndarray) -> float:
        return float(np.sum(w_e * u * v))

    def w1_norm_sq(u: np.ndarray) -> float:
        return float(np.sum(w_e * u * u))

    energy_tot = w1_norm_sq(w1_arr)
    energy_ex = w1_norm_sq(omega_exact)
    energy_co = w1_norm_sq(omega_coexact)
    energy_harm = w1_norm_sq(h)

    ortho_ex_co = w1_inner(omega_exact, omega_coexact)
    ortho_ex_harm = w1_inner(omega_exact, h)
    ortho_co_harm = w1_inner(omega_coexact, h)

    residual = w1_arr - (omega_exact + omega_coexact + h)
    res_norm = float(np.sqrt(w1_norm_sq(residual)))
    tot_norm = float(np.sqrt(energy_tot))

    rel_rec_err = res_norm / (tot_norm + eps)
    sum_energies = energy_ex + energy_co + energy_harm
    rel_energy_err = abs(energy_tot - sum_energies) / (energy_tot + eps)

    return HodgeDecomposition(
        exact=omega_exact,
        coexact=omega_coexact,
        harmonic=h,
        potential=alpha,
        stream_function=beta,
        energy_total=energy_tot,
        energy_exact=energy_ex,
        energy_coexact=energy_co,
        energy_harmonic=energy_harm,
        orthogonality_exact_coexact=ortho_ex_co,
        orthogonality_exact_harmonic=ortho_ex_harm,
        orthogonality_coexact_harmonic=ortho_co_harm,
        reconstruction_residual_norm=res_norm,
        relative_reconstruction_error=rel_rec_err,
        relative_energy_error=rel_energy_err,
    )
