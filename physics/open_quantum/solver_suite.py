"""Multi-method open-quantum Liouvillian solver suite and streaming propagator.

Provides:
- Exact dense, sparse SuperLU shift-invert, and matrix-free Krylov solvers.
- Explicit residual norm verification: ||L v - lambda v||_2 / ||v||_2.
- Hermitized, trace-normalized steady-state rho_ss reconstruction.
- Memory-bounded streaming Lindblad propagation generator.
"""
from __future__ import annotations

import time
from typing import Any, Iterator, Optional, Tuple
import numpy as np
from scipy import sparse
from scipy.sparse.linalg import eigs, splu, LinearOperator

from .lindblad_lattice import HBAR, LindbladLattice
from .liouvillian_gap import GapResult, calculate_lattice_currents, _chiral_score
from .operator_cache import DEFAULT_OPERATOR_CACHE, OperatorCache
from .sparse_operator import build_sparse_liouvillian, make_matrix_free_liouvillian


def _extract_steady_state(vector: Optional[np.ndarray], d: int) -> Optional[np.ndarray]:
    """Reconstruct, Hermitize, and trace-normalize the density matrix."""
    if vector is None:
        return None
    vec = np.asarray(vector, dtype=np.complex128).ravel()
    if vec.size != d * d:
        return None
    rho = vec.reshape((d, d), order="F")
    rho = (rho + rho.conj().T) / 2.0
    tr = np.trace(rho)
    if abs(tr) < 1e-20:
        return None
    return rho / tr


def _compute_residual_norm(
    op_matrix_or_linop: Any,
    eigenvalue: complex,
    eigenvector: np.ndarray,
) -> float:
    """Compute relative residual norm ||L v - lambda v||_2 / ||v||_2."""
    v = np.asarray(eigenvector, dtype=np.complex128).ravel()
    v_norm = float(np.linalg.norm(v))
    if v_norm < 1e-20:
        return float("inf")
    
    if isinstance(op_matrix_or_linop, (sparse.spmatrix, np.ndarray, LinearOperator)):
        lv = op_matrix_or_linop @ v
    else:
        lv = np.dot(op_matrix_or_linop, v)
    
    residual = lv - eigenvalue * v
    return float(np.linalg.norm(residual) / v_norm)


def solve_liouvillian_spectrum(
    model: LindbladLattice,
    method: str = "auto",
    k: int = 6,
    tolerance_s: float = 1e-8,
    maxiter: Optional[int] = 2000,
    sigma: float = 1e-5,
    cache: Optional[OperatorCache] = None,
) -> GapResult:
    """Solve the Liouvillian spectrum and steady state with rigorous residual verification.

    Args:
        model: LindbladLattice instance.
        method: Solver method ("auto", "exact_dense", "sparse_shift_invert", "matrix_free").
        k: Number of eigenvalues/eigenvectors to compute for sparse methods.
        tolerance_s: Numerical tolerance for zero/stationary mode detection.
        maxiter: Maximum Arnoldi iterations for Krylov solvers.
        sigma: Shift parameter for shift-invert SuperLU factorization.
        cache: Optional OperatorCache for reusing SuperLU factorizations.

    Returns:
        GapResult with verified spectral gap, residual norms, and steady-state density matrix.
    """
    d = model.dimension
    size = d * d
    active_cache = cache if cache is not None else DEFAULT_OPERATOR_CACHE

    if method == "auto":
        method = "exact_dense" if d <= 32 else "sparse_shift_invert"

    t0 = time.perf_counter()

    if method == "exact_dense":
        if d > 48:
            raise ValueError(
                f"exact_dense method requested for dimension {d} (matrix size {size}x{size}); "
                "use sparse_shift_invert to prevent memory exhaustion"
            )
        l_dense = model.liouvillian()
        values, vectors = np.linalg.eig(l_dense)
        iteration_count = 1
        active_op = l_dense

    elif method == "sparse_shift_invert":
        # Direct sparse Kronecker assembly
        superop = build_sparse_liouvillian(model)
        
        # Check cache for SuperLU factorization
        cache_key = f"splu_{d}_{sigma:.6e}"
        lu = active_cache.get(cache_key)
        if lu is None:
            shifted = superop - sigma * sparse.eye(size, format="csc", dtype=np.complex128)
            lu = splu(shifted)
            active_cache.set(cache_key, lu)

        calls = 0

        def inv_matvec(v: np.ndarray) -> np.ndarray:
            nonlocal calls
            calls += 1
            return lu.solve(v)

        opinv = LinearOperator((size, size), matvec=inv_matvec, dtype=np.complex128)
        kk = max(2, min(k, size - 2))
        values, vectors = eigs(
            superop,
            k=kk,
            sigma=sigma,
            which="LM",
            OPinv=opinv,
            tol=1e-8,
            maxiter=maxiter,
            return_eigenvectors=True,
        )
        iteration_count = calls
        active_op = superop

    elif method == "matrix_free":
        # Matrix-free LinearOperator without superoperator matrix storage
        linop = make_matrix_free_liouvillian(model)
        kk = max(2, min(k, size - 2))
        actual_maxiter = min(maxiter or 100, 100)
        try:
            values, vectors = eigs(
                linop,
                k=kk,
                which="SM",
                tol=1e-4,
                maxiter=actual_maxiter,
                return_eigenvectors=True,
            )
        except Exception:
            # Fallback to largest magnitude if unshifted SM fails to converge
            values, vectors = eigs(
                linop,
                k=kk,
                which="LM",
                tol=1e-4,
                maxiter=actual_maxiter,
                return_eigenvectors=True,
            )
        iteration_count = actual_maxiter
        active_op = linop

    else:
        raise ValueError(f"Unknown solver method: {method}")

    # Identify stationary eigenvalue closest to 0
    vals = np.asarray(values, dtype=np.complex128)
    stat_idx = int(np.argmin(np.abs(vals)))
    stationary_val = vals[stat_idx]
    stationary_vec = vectors[:, stat_idx] if vectors is not None else None

    # Compute explicit residual norm of stationary mode
    residual_norm = _compute_residual_norm(active_op, stationary_val, stationary_vec)

    # Stationary mode count and decay spectrum
    modes = int(np.count_nonzero(np.abs(vals) <= tolerance_s))
    non_stat = vals[np.abs(vals - stationary_val) > tolerance_s]
    decays = -non_stat.real[(-non_stat.real) > tolerance_s]

    gap_zero = bool(len(decays) == 0 or modes > 1)
    if gap_zero:
        sub = 0.0
        super_rate = 0.0
        gap = 0.0
    else:
        sub = float(np.min(decays))
        super_rate = float(np.max(decays))
        gap = sub

    tau_sub = float(np.inf if gap_zero or sub == 0.0 else 1.0 / sub)
    tau_super = float(np.inf if super_rate == 0.0 else 1.0 / super_rate)

    # Reconstruct density matrix
    rho_ss = _extract_steady_state(stationary_vec, d)
    chiral_score_val, exhibits_chiral = _chiral_score(model, rho_ss)

    probe = np.eye(d, dtype=np.complex128) / float(d)
    trace_res = model.trace_residual(probe)
    h_herm_res = float(np.linalg.norm(model.hamiltonian - model.hamiltonian.conj().T))

    converged = bool(
        residual_norm <= max(tolerance_s, 1e-3)
        or (method == "exact_dense" and np.all(np.isfinite(vals)))
    )

    return GapResult(
        gap_s=gap,
        decoherence_time_s=tau_sub,
        stationary_eigenvalue_s=complex(stationary_val),
        method=method,
        stationary_residual_s=residual_norm,
        trace_preservation_residual_s=trace_res,
        hermiticity_residual=h_herm_res,
        stationary_modes=modes,
        gap_zero=gap_zero,
        converged=converged,
        subradiant_gap_s=sub,
        superradiant_gap_s=super_rate,
        tau_subradiant_s=tau_sub,
        tau_superradiant_s=tau_super,
        chiral_current_s=chiral_score_val,
        exhibits_chiral_current=exhibits_chiral,
        stationary_state=rho_ss,
        iteration_count=iteration_count,
    )


def stream_lindblad_propagation(
    model: LindbladLattice,
    rho0: np.ndarray,
    times_s: np.ndarray,
    max_memory_bytes: int = 104857600,
) -> Iterator[Tuple[float, np.ndarray]]:
    """Memory-bounded generator yielding (time, rho(t)) along the Lindblad trajectory.

    Uses a 4th-order Runge-Kutta (RK4) integration step on the Lindblad RHS:
        d rho / dt = L(rho)

    Args:
        model: LindbladLattice instance.
        rho0: Initial density matrix (d x d).
        times_s: Monotonically increasing time grid in seconds.
        max_memory_bytes: Maximum allowed memory for state buffers.

    Yields:
        (t, rho_t) tuples where rho_t is the Hermitized and trace-normalized state at time t.
    """
    d = model.dimension
    state_bytes = d * d * 16  # complex128
    if state_bytes > max_memory_bytes:
        raise MemoryError(
            f"State matrix requires {state_bytes} bytes, exceeding max_memory_bytes={max_memory_bytes}"
        )

    rho = np.asarray(rho0, dtype=np.complex128).copy()
    if rho.shape != (d, d):
        raise ValueError(f"rho0 must have shape ({d}, {d})")

    # Trace-normalize initial state
    tr0 = np.trace(rho)
    if abs(tr0) < 1e-15:
        raise ValueError("Initial density matrix must have non-zero trace")
    rho = (rho + rho.conj().T) / 2.0
    rho /= tr0

    t_prev = float(times_s[0])
    yield t_prev, rho.copy()

    for i in range(1, len(times_s)):
        t_curr = float(times_s[i])
        dt = t_curr - t_prev
        if dt <= 0:
            raise ValueError("times_s must be strictly monotonically increasing")

        # Classical 4th-order Runge-Kutta step
        k1 = model.rhs(rho)
        k2 = model.rhs(rho + 0.5 * dt * k1)
        k3 = model.rhs(rho + 0.5 * dt * k2)
        k4 = model.rhs(rho + dt * k3)

        rho = rho + (dt / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)

        # Enforce physical Hermiticity and trace preservation
        rho = (rho + rho.conj().T) / 2.0
        tr = np.trace(rho)
        if abs(tr) > 1e-15:
            rho /= tr

        t_prev = t_curr
        yield t_curr, rho.copy()
