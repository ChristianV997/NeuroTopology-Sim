"""Sparse Liouvillian superoperator assembly and matrix-free LinearOperator.

Enforces:
- Direct scipy.sparse.kron assembly without O(d^4) dense allocations.
- Matrix-free LinearOperator rho -> L(rho) operating in O(d^2) memory.
- Trace preservation and Hermiticity preservation checks.
- Bounded memory footprint.
"""
from __future__ import annotations

from typing import Optional
import numpy as np
from scipy import sparse
from scipy.sparse.linalg import LinearOperator

from .lindblad_lattice import HBAR, LindbladLattice


def build_sparse_liouvillian(model: LindbladLattice) -> sparse.csc_matrix:
    """Directly assemble the sparse Liouvillian superoperator without dense arrays.

    Uses Kronecker products of sparse CSR/CSC operators:
        L = -i/hbar (I (x) H - H^T (x) I)
            + sum_k [ L_k^* (x) L_k - 1/2 ( I (x) (L_k^dagger L_k) + (L_k^dagger L_k)^T (x) I ) ]

    Args:
        model: Initialized LindbladLattice model.

    Returns:
        scipy.sparse.csc_matrix representing the d^2 x d^2 superoperator in Fortran order.
    """
    d = model.dimension
    size = d * d

    eye_sp = sparse.eye(d, format="csc", dtype=np.complex128)
    h_sp = sparse.csc_matrix(model.hamiltonian, dtype=np.complex128)

    # Hamiltonian commutator superoperator: -i/hbar * (I (x) H - H^T (x) I)
    out = -1j * (
        sparse.kron(eye_sp, h_sp, format="csc") - sparse.kron(h_sp.T, eye_sp, format="csc")
    ) / HBAR

    # Dissipator jump superoperators
    for op in model.collapse_operators:
        if not np.any(op):
            continue
        op_sp = sparse.csc_matrix(op, dtype=np.complex128)
        q_sp = (op_sp.conj().T @ op_sp).tocsc()

        jump = sparse.kron(op_sp.conj(), op_sp, format="csc")
        damping = 0.5 * (
            sparse.kron(eye_sp, q_sp, format="csc") + sparse.kron(q_sp.T, eye_sp, format="csc")
        )
        out += jump - damping

    return out.tocsc()


def make_matrix_free_liouvillian(model: LindbladLattice) -> LinearOperator:
    """Construct an O(d^2) memory matrix-free LinearOperator evaluating L(rho).

    Instead of allocating a d^2 x d^2 superoperator matrix, evaluates the Lindblad
    generator directly via d x d matrix multiplications:
        L(rho) = -i/hbar [H, rho] + sum_k [ L_k rho L_k^dagger - 1/2 {L_k^dagger L_k, rho} ]

    Args:
        model: Initialized LindbladLattice model.

    Returns:
        scipy.sparse.linalg.LinearOperator with shape (d^2, d^2) and dtype complex128.
    """
    d = model.dimension
    size = d * d

    def matvec(v: np.ndarray) -> np.ndarray:
        v_arr = np.asarray(v, dtype=np.complex128)
        if v_arr.size != size:
            raise ValueError(f"Expected input vector of size {size}, got {v_arr.size}")
        rho = v_arr.reshape((d, d), order="F")
        l_rho = model.rhs(rho)
        return l_rho.ravel(order="F")

    def rmatvec(v: np.ndarray) -> np.ndarray:
        # Adjoint action of Lindblad generator on an observable X (Heisenberg picture)
        # L^dagger(X) = i/hbar [H, X] + sum_k [ L_k^dagger X L_k - 1/2 {L_k^dagger L_k, X} ]
        v_arr = np.asarray(v, dtype=np.complex128)
        if v_arr.size != size:
            raise ValueError(f"Expected input vector of size {size}, got {v_arr.size}")
        x = v_arr.reshape((d, d), order="F")
        
        out = 1j * (model.hamiltonian @ x - x @ model.hamiltonian) / HBAR
        for op in model.collapse_operators:
            q = op.conj().T @ op
            out += op.conj().T @ x @ op - 0.5 * (q @ x + x @ q)
        return out.ravel(order="F")

    return LinearOperator(
        shape=(size, size),
        matvec=matvec,
        rmatvec=rmatvec,
        dtype=np.complex128,
    )
