"""Non-Hermitian effective-Hamiltonian cross-check via QuTiP -- SPECULATIVE,
segregated track.

`analysis/itct/itct_cessation_protocol_v3_full_stack.py::build_effective_hamiltonian`
/ `loschmidt_echo` / `exceptional_point_discriminant` compute these quantities
by hand (`scipy.linalg.expm` on a small non-Hermitian matrix). This module
independently recomputes the same quantities using QuTiP -- a long-
maintained, scipy/Cython-backed quantum toolbox with explicit non-Hermitian-
Hamiltonian support -- as a cross-check that the hand-rolled version isn't
silently wrong, the same discipline this repo already applies elsewhere
(e.g. `mne-connectivity` cross-validating hand-rolled wPLI in
`analysis/connectivity_topology.py`).

Genuinely speculative: this module explores exceptional-point / non-
Hermitian quantum-dynamics constructs applied to a PLV-derived matrix. It is
NOT a validated model of biological neural dynamics -- see
`sim/speculative/__init__.py` for the segregation policy this module is
subject to. Importing from `analysis.itct` (not `sciencer_d.btc_icft`) is
permitted per the project plan's scoping: `analysis/itct/` already carries
this same speculative-adjacent content, and only its real, reusable PLV +
persistent-homology core was factored out into
`analysis/connectivity_topology.py` for reuse elsewhere.
"""
from __future__ import annotations

from typing import Dict

import numpy as np
import qutip as qt

from analysis.itct.itct_cessation_protocol_v3_full_stack import (
    build_effective_hamiltonian,
    exceptional_point_discriminant,
)
from analysis.itct.itct_cessation_protocol_v3_full_stack import (
    loschmidt_echo as loschmidt_echo_scipy,
)


def loschmidt_echo_qutip(plv: np.ndarray, t: float = 1.0, nonherm: float = 0.1) -> float:
    """QuTiP-based recomputation of the Loschmidt echo
    |<psi0|e^{-iHt}|psi0>|^2 for the same effective Hamiltonian ITCT's
    hand-rolled `loschmidt_echo` uses (same `build_effective_hamiltonian`
    call, same `nonherm` default)."""
    H = build_effective_hamiltonian(plv, nonherm=nonherm)
    C = H.shape[0]
    Hq = qt.Qobj(H)
    psi0 = qt.Qobj(np.ones((C, 1), dtype=complex) / np.sqrt(C))
    U = (-1j * Hq * t).expm()
    amp = psi0.dag() * U * psi0
    amp_scalar = amp.full()[0, 0] if isinstance(amp, qt.Qobj) else amp
    return float(np.abs(amp_scalar) ** 2)


def cross_validate_loschmidt_echo(
    plv: np.ndarray, t: float = 1.0, nonherm: float = 0.1, tol: float = 1e-6,
) -> Dict[str, float]:
    """Compare the hand-rolled scipy Loschmidt echo against the independent
    QuTiP recomputation on the same effective Hamiltonian. Returns both
    values plus an `agree` flag -- callers should treat `agree=False` as a
    real discrepancy to investigate, not something to silently paper over."""
    scipy_val = loschmidt_echo_scipy(plv, t=t)
    qutip_val = loschmidt_echo_qutip(plv, t=t, nonherm=nonherm)
    difference = abs(scipy_val - qutip_val)
    return {
        "scipy_value": scipy_val,
        "qutip_value": qutip_val,
        "difference": difference,
        "agree": bool(difference < tol),
    }


def eigenvalue_gap_qutip(kappa: float, g1: float, g2: float, w0: float = 1.0) -> float:
    """Eigenvalue gap |lambda1 - lambda2| of the same 2x2 non-Hermitian
    Hamiltonian `exceptional_point_discriminant` analyzes, computed via
    QuTiP's `eigenenergies()`. At an exceptional point (discriminant == 0),
    both eigenvalues AND eigenvectors coalesce -- unlike a generic
    degeneracy -- so this gap is the physically meaningful cross-check
    quantity for whether ITCT's discriminant formula actually locates one.
    """
    a = w0 - 1j * g1
    d = w0 - 1j * g2
    H = np.array([[a, kappa], [kappa, d]], dtype=complex)
    evals = qt.Qobj(H).eigenenergies()
    return float(np.abs(evals[0] - evals[1]))


def cross_validate_exceptional_point(g1: float, g2: float, w0: float = 1.0, tol: float = 1e-6) -> Dict[str, float]:
    """Analytically solve for the kappa at which
    `exceptional_point_discriminant(kappa, g1, g2, w0)` is exactly zero
    (discriminant = (a-d)^2 + 4*kappa^2 = 0), then verify via QuTiP that the
    Hamiltonian's eigenvalues genuinely coalesce there -- an independent
    confirmation that the hand-rolled discriminant formula identifies a real
    exceptional point, not just an algebraic zero."""
    a = w0 - 1j * g1
    d = w0 - 1j * g2
    kappa_ep = complex(np.sqrt(-((a - d) ** 2) / 4))
    discriminant_at_ep = exceptional_point_discriminant(kappa_ep, g1, g2, w0)
    gap_at_ep = eigenvalue_gap_qutip(kappa_ep, g1, g2, w0)
    return {
        "kappa_ep": kappa_ep,
        "discriminant_at_ep": discriminant_at_ep,
        "eigenvalue_gap_at_ep": gap_at_ep,
        "confirmed_exceptional_point": bool(gap_at_ep < tol),
    }
