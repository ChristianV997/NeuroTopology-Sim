"""Scalar weighted Hodge on a filled triangle; readout non-intertwining demo.

On an oriented graph with a single filled 2-cell, scalar 1-cochains decompose
(with edge weights w_e > 0 and face weight μ) into

    C¹ = im(B₀) ⊕ Harm ⊕ im(B₁*),

where Harm = ker(B₁) ∩ ker(B₀*) (weighted adjoints). An edgewise sheaf readout
Λ need not map sheaf-exact cochains into the scalar gradient subspace, so it
does not preserve this decomposition.
"""

from __future__ import annotations

from typing import Dict, Mapping, Sequence, Tuple

import numpy as np

from .sheaf import CellularSheaf, Edge, LinearReadout, sheaf_coboundary, scalarize_edge_cochain
from .triangle_example import build_canonical_triangle, first_coordinate_readout


def scalar_operators(
    edges: Sequence[Edge],
    face_cycle: Sequence[str],
    edge_weights: Mapping[str, float] | None = None,
) -> Tuple[np.ndarray, np.ndarray, Dict[str, int], Dict[str, int]]:
    """Build B₀ (n_e × n_v) and B₁ (1 × n_e) for a triangle with one face.

    B₁ ω = sum of ω along the oriented face boundary (cycle).
    """
    verts = sorted({e.src for e in edges} | {e.dst for e in edges})
    v_index = {v: i for i, v in enumerate(verts)}
    e_index = {e.name: i for i, e in enumerate(edges)}
    n_v, n_e = len(verts), len(edges)
    B0 = np.zeros((n_e, n_v))
    for e in edges:
        B0[e_index[e.name], v_index[e.src]] = -1.0
        B0[e_index[e.name], v_index[e.dst]] = 1.0
    B1 = np.zeros((1, n_e))
    for name in face_cycle:
        B1[0, e_index[name]] = 1.0
    if edge_weights is None:
        W = np.eye(n_e)
    else:
        W = np.diag([float(edge_weights[e.name]) for e in edges])
    return B0, B1, v_index, e_index


def weighted_hodge_project(
    a: np.ndarray,
    B0: np.ndarray,
    B1: np.ndarray,
    W: np.ndarray,
) -> Dict[str, np.ndarray]:
    """Project scalar edge vector a into gradient / harmonic / curl pieces.

    Uses W-inner product on edges: <x,y>_W = xᵀ W y.
    Gradient: a_g = B₀ φ with φ = (B₀ᵀ W B₀)⁺ B₀ᵀ W a
    Curl: for one face, a_c ∝ W^{-1} B₁ᵀ (component along weighted coboundary image)
    Harmonic: a − a_g − a_c
    """
    a = np.asarray(a, dtype=float).reshape(-1)
    # gradient projection
    L0 = B0.T @ W @ B0
    rhs = B0.T @ W @ a
    phi, *_ = np.linalg.lstsq(L0, rhs, rcond=None)
    a_g = B0 @ phi

    # curl: image of B₁* = W^{-1} B₁ᵀ (1D)
    Winv = np.linalg.inv(W)
    cvec = Winv @ B1.T  # shape (n_e, 1)
    cvec = cvec.reshape(-1)
    # orthonormalize in W-inner product against gradient? For triangle,
    # im B₁* is orthogonal to im B₀ in the unweighted case when B₁ B₀=0.
    # Project residual onto curl direction in W metric.
    resid = a - a_g
    denom = float(cvec @ W @ cvec)
    if denom < 1e-15:
        a_c = np.zeros_like(a)
    else:
        coeff = float(cvec @ W @ resid) / denom
        a_c = coeff * cvec
    a_h = a - a_g - a_c
    return {"gradient": a_g, "harmonic": a_h, "curl": a_c, "phi": phi}


def graph_hodge_no_faces(
    a: np.ndarray, B0: np.ndarray, W: np.ndarray
) -> Dict[str, np.ndarray]:
    """Hodge on the 1-skeleton only: C¹ = im(B₀) ⊕ ker(B₀*) (no curl slot)."""
    a = np.asarray(a, dtype=float).reshape(-1)
    L0 = B0.T @ W @ B0
    phi, *_ = np.linalg.lstsq(L0, B0.T @ W @ a, rcond=None)
    a_g = B0 @ phi
    a_h = a - a_g  # divergenceless = harmonic on a cycle graph
    return {"gradient": a_g, "harmonic": a_h, "phi": phi}


def readout_breaks_hodge_demo() -> Dict[str, object]:
    """Exact sheaf cochain → scalar outside the gradient subspace under incompatible Λ."""
    sheaf = build_canonical_triangle()
    readout = first_coordinate_readout(sheaf)
    z = {
        "1": np.array([1.0, 1.0]),
        "2": np.array([0.0, 0.0]),
        "3": np.array([0.0, 0.0]),
    }
    omega = sheaf_coboundary(sheaf, z)
    scalar = scalarize_edge_cochain(readout, omega)
    order = [e.name for e in sheaf.edges]
    a = np.array([scalar[n] for n in order])

    B0, B1, _, _ = scalar_operators(sheaf.edges, order)
    W = np.eye(len(order))
    filled = weighted_hodge_project(a, B0, B1, W)
    skeleton = graph_hodge_no_faces(a, B0, W)

    grad_f = float(np.linalg.norm(filled["gradient"]))
    harm_f = float(np.linalg.norm(filled["harmonic"]))
    curl_f = float(np.linalg.norm(filled["curl"]))
    grad_s = float(np.linalg.norm(skeleton["gradient"]))
    harm_s = float(np.linalg.norm(skeleton["harmonic"]))
    cycle = float(np.asarray(B1 @ a).reshape(-1)[0])
    return {
        "edge_order": order,
        "scalar_a": a.tolist(),
        "cycle_sum": cycle,
        "filled_2_complex": {
            "gradient_norm": grad_f,
            "harmonic_norm": harm_f,
            "curl_norm": curl_f,
            "curl_nonzero": curl_f > 1e-8,
            "note": "B₁a≠0 ⇒ curl slot occupied (not closed)",
        },
        "cycle_graph_1_skeleton": {
            "gradient_norm": grad_s,
            "harmonic_norm": harm_s,
            "harmonic_nonzero": harm_s > 1e-8,
            "note": "No faces: circulatory remainder is harmonic (ker B₀*)",
        },
        "hodge_not_preserved": True,
        "interpretation": (
            "ω = B₀^F z is sheaf-exact. After incompatible Λ, Λω has cycle sum ≠ 0: "
            "on the filled triangle it acquires a curl component; on the bare cycle "
            "graph the same remainder is harmonic. Either way Λω is not pure "
            "gradient, so edgewise Λ does not intertwine weighted Hodge projectors."
        ),
    }


def closedness_needs_degree_two_map() -> Dict[str, str]:
    """Explain why a degree-2 map is required to induce H¹ on a 2-complex."""
    return {
        "exactness_preservation": (
            "A readout preserves exactness of 0→1 cochains iff there exist vertex "
            "maps Λ₀ such that Λ₁ ∘ B₀^F = B₀ ∘ Λ₀ (endpoint compatibility). Then "
            "im(B₀^F) maps into im(B₀)."
        ),
        "closedness_on_2_complex": (
            "Closedness of a 1-cochain means B₁ ω = 0 (vanishing face integrals). "
            "Preserving closedness requires a face-level map Λ₂ (degree 2 in the "
            "cochain complex indexing) such that Λ₂ ∘ B₁^F = B₁ ∘ Λ₁. Without that "
            "commutative square, ker(B₁^F) need not map into ker(B₁)."
        ),
        "cohomology_map": (
            "A cochain map (Λ₀, Λ₁, Λ₂, …) commuting with all coboundaries induces "
            "maps on cohomology H^n = ker(B_n)/im(B_{n-1}). Endpoint-compatible "
            "edge readouts give a map on H⁰/H¹ of the 1-skeleton only in the "
            "exactness sense; a filled 2-complex needs Λ₂ to get a well-defined "
            "map on H¹ of the 2-complex."
        ),
        "distinction": (
            "Exactness preservation (im B₀) ≠ closedness preservation (ker B₁). "
            "On a tree they coincide; on a cycle/2-complex they differ. The "
            "canonical triangle shows incompatible Λ₁ can send exact sheaf "
            "cochains outside ker(B₁) of the scalar complex."
        ),
    }
