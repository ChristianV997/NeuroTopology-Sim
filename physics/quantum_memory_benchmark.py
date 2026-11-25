"""Synthetic write-wait-read comparison of a qubit pseudomode and a classical OU bit.

All rates are SI s^-1 or rad s^-1. The model is a numerical memory benchmark,
not a calibrated biological model. The receiver gets only a reduced qubit state
(or one noisy classical scalar) and a basis announcement made after the wait.
"""
from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Mapping

import numpy as np

HBAR_J_S = 1.054571817e-34
KB_J_K = 1.380649e-23
BB84_LABELS = ("Z0", "Z1", "X+", "X-")
MAX_FOCK_CUTOFF = 32
MAX_STEPS = 20_000
MAX_MATRIX_WORK_UNITS = 25_000_000


@dataclass(frozen=True)
class PseudomodeConfig:
    """One damped thermal oscillator coupled to a qubit memory.

    ``hamiltonian_over_hbar`` has angular-frequency units. The oscillator is
    truncated to ``fock_cutoff`` number states and damped by thermal Lindblad
    jumps. ``mode_drive_rad_s`` is a coherent drive coefficient in that same
    angular-frequency Hamiltonian.
    """

    temperature_K: float = 310.0
    mode_frequency_rad_s: float = 1.644e13
    coupling_rad_s: float = 5.0e11
    mode_damping_rate_s: float = 2.0e12
    mode_drive_rad_s: float = 0.0
    qubit_dephasing_rate_s: float = 0.0
    qubit_relaxation_rate_s: float = 0.0
    wait_s: float = 2.0e-13
    max_step_s: float = 5.0e-15
    fock_cutoff: int = 12
    max_steps: int = MAX_STEPS

    def __post_init__(self) -> None:
        positives = (self.temperature_K, self.mode_frequency_rad_s, self.max_step_s)
        if any(not math.isfinite(x) or x <= 0 for x in positives):
            raise ValueError("temperature, mode frequency, and max step must be finite and positive")
        nonnegative = (
            self.coupling_rad_s,
            self.mode_damping_rate_s,
            self.mode_drive_rad_s,
            self.qubit_dephasing_rate_s,
            self.qubit_relaxation_rate_s,
            self.wait_s,
        )
        if any(not math.isfinite(x) or x < 0 for x in nonnegative):
            raise ValueError("couplings, rates, drive, and wait must be finite and non-negative")
        if (
            isinstance(self.fock_cutoff, bool)
            or not isinstance(self.fock_cutoff, (int, np.integer))
            or not 2 <= self.fock_cutoff <= MAX_FOCK_CUTOFF
        ):
            raise ValueError(f"fock_cutoff must be an integer from 2 to {MAX_FOCK_CUTOFF}")
        if (
            isinstance(self.max_steps, bool)
            or not isinstance(self.max_steps, int)
            or not 1 <= self.max_steps <= MAX_STEPS
        ):
            raise ValueError(f"max_steps must be an integer from 1 to {MAX_STEPS}")
        steps = max(1, math.ceil(self.wait_s / self.max_step_s))
        if steps > self.max_steps:
            raise ValueError("requested integration exceeds max_steps")
        estimated_work = steps * (2 * int(self.fock_cutoff)) ** 3
        if estimated_work > MAX_MATRIX_WORK_UNITS:
            raise ValueError("requested integration exceeds the matrix-work budget")


@dataclass(frozen=True)
class ClassicalOUConfig:
    """One-bit measure-and-store comparator followed by a scalar OU process."""

    wait_s: float = 2.0e-13
    tau_s: float = 1.0e-12
    initial_amplitude: float = 1.0
    stationary_std: float = 0.2

    def __post_init__(self) -> None:
        if not math.isfinite(self.wait_s) or self.wait_s < 0:
            raise ValueError("wait_s must be finite and non-negative")
        if not math.isfinite(self.tau_s) or self.tau_s <= 0:
            raise ValueError("tau_s must be finite and positive")
        if not math.isfinite(self.initial_amplitude) or self.initial_amplitude <= 0:
            raise ValueError("initial_amplitude must be finite and positive")
        if not math.isfinite(self.stationary_std) or self.stationary_std < 0:
            raise ValueError("stationary_std must be finite and non-negative")


@dataclass(frozen=True)
class QuantumBenchmarkResult:
    mean_success: float
    success_by_input: Mapping[str, float]
    input_count: int
    postselected_count: int
    max_trace_error: float
    max_hermiticity_error: float
    minimum_eigenvalue: float
    thermal_occupation: float
    mode_population_n_ge_4: float
    mode_edge_population: float


@dataclass(frozen=True)
class ClassicalBenchmarkResult:
    mean_success: float
    trial_count: int
    input_count: int
    postselected_count: int
    standard_error: float
    memory_bits: int


def thermal_occupation(mode_frequency_rad_s: float, temperature_K: float) -> float:
    """Bose occupation for angular frequency in rad/s and temperature in K."""
    if not math.isfinite(mode_frequency_rad_s) or mode_frequency_rad_s <= 0:
        raise ValueError("mode frequency must be finite and positive")
    if not math.isfinite(temperature_K) or temperature_K <= 0:
        raise ValueError("temperature must be finite and positive")
    exponent = HBAR_J_S * mode_frequency_rad_s / (KB_J_K * temperature_K)
    if exponent > 700.0:
        return 0.0
    return 1.0 / math.expm1(exponent)


def bb84_state(label: str) -> np.ndarray:
    """Return a unit-trace density matrix; labels stay with evaluator/scorer."""
    states = {
        "Z0": np.array([[1.0, 0.0], [0.0, 0.0]], dtype=complex),
        "Z1": np.array([[0.0, 0.0], [0.0, 1.0]], dtype=complex),
        "X+": 0.5 * np.array([[1.0, 1.0], [1.0, 1.0]], dtype=complex),
        "X-": 0.5 * np.array([[1.0, -1.0], [-1.0, 1.0]], dtype=complex),
    }
    try:
        return states[label].copy()
    except KeyError as exc:
        raise ValueError("unknown input state") from exc


def _validate_qubit_density(rho: np.ndarray) -> np.ndarray:
    state = np.asarray(rho, dtype=complex)
    if state.shape != (2, 2) or not np.all(np.isfinite(state)):
        raise ValueError("qubit input must be a finite 2x2 density matrix")
    if np.max(np.abs(state - state.conj().T)) > 1e-10:
        raise ValueError("qubit input must be Hermitian")
    if abs(np.trace(state) - 1.0) > 1e-10:
        raise ValueError("qubit input must have unit trace")
    if float(np.min(np.linalg.eigvalsh((state + state.conj().T) / 2.0))) < -1e-10:
        raise ValueError("qubit input must be positive semidefinite")
    return state


def _annihilation(cutoff: int) -> np.ndarray:
    out = np.zeros((cutoff, cutoff), dtype=complex)
    for n in range(1, cutoff):
        out[n - 1, n] = math.sqrt(n)
    return out


def _thermal_density(cutoff: int, nbar: float) -> np.ndarray:
    q = nbar / (1.0 + nbar)
    weights = np.power(q, np.arange(cutoff, dtype=float))
    weights /= weights.sum()
    return np.diag(weights.astype(complex))


def _dissipator(rho: np.ndarray, jump: np.ndarray) -> np.ndarray:
    product = jump.conj().T @ jump
    return jump @ rho @ jump.conj().T - 0.5 * (product @ rho + rho @ product)


def _pseudomode_operators(config: PseudomodeConfig) -> tuple[np.ndarray, tuple[np.ndarray, ...], float]:
    n = int(config.fock_cutoff)
    a = _annihilation(n)
    adag = a.conj().T
    ident_q, ident_b = np.eye(2, dtype=complex), np.eye(n, dtype=complex)
    sigma_z = np.diag([1.0, -1.0]).astype(complex)
    n_op = adag @ a
    x_mode = a + adag
    hbar_h = (
        config.mode_frequency_rad_s * np.kron(ident_q, n_op)
        + 0.5 * config.coupling_rad_s * np.kron(sigma_z, x_mode)
        + config.mode_drive_rad_s * np.kron(ident_q, x_mode)
    )
    nbar = thermal_occupation(config.mode_frequency_rad_s, config.temperature_K)
    jumps: list[np.ndarray] = []
    if config.mode_damping_rate_s:
        jumps.append(math.sqrt(config.mode_damping_rate_s * (nbar + 1.0)) * np.kron(ident_q, a))
        if nbar:
            jumps.append(math.sqrt(config.mode_damping_rate_s * nbar) * np.kron(ident_q, adag))
    if config.qubit_dephasing_rate_s:
        jumps.append(math.sqrt(config.qubit_dephasing_rate_s / 2.0) * np.kron(sigma_z, ident_b))
    if config.qubit_relaxation_rate_s:
        sigma_minus = np.array([[0.0, 0.0], [1.0, 0.0]], dtype=complex)
        jumps.append(math.sqrt(config.qubit_relaxation_rate_s) * np.kron(sigma_minus, ident_b))
    return hbar_h, tuple(jumps), nbar


def _rhs(rho: np.ndarray, hbar_h: np.ndarray, jumps: tuple[np.ndarray, ...]) -> np.ndarray:
    out = -1j * (hbar_h @ rho - rho @ hbar_h)
    for jump in jumps:
        out += _dissipator(rho, jump)
    return out


def _assert_density_physical(rho: np.ndarray) -> None:
    trace_error, hermiticity_error, minimum_eigenvalue = density_diagnostics(rho)
    if trace_error > 1e-8 or hermiticity_error > 1e-8 or minimum_eigenvalue < -1e-7:
        raise ArithmeticError(
            "density evolution left physical tolerance; reduce max_step_s or increase fock_cutoff"
        )


def evolve_quantum_state(rho_qubit: np.ndarray, config: PseudomodeConfig) -> tuple[np.ndarray, np.ndarray, float]:
    """Evolve input qubit plus inaccessible thermal pseudomode; return joint state."""
    state = _validate_qubit_density(rho_qubit)
    hbar_h, jumps, nbar = _pseudomode_operators(config)
    mode = _thermal_density(int(config.fock_cutoff), nbar)
    rho = np.kron(state, mode)
    if config.wait_s == 0.0:
        _assert_density_physical(rho)
        return rho, mode, nbar
    steps = max(1, math.ceil(config.wait_s / config.max_step_s))
    dt = config.wait_s / steps
    for _ in range(steps):
        k1 = _rhs(rho, hbar_h, jumps)
        k2 = _rhs(rho + 0.5 * dt * k1, hbar_h, jumps)
        k3 = _rhs(rho + 0.5 * dt * k2, hbar_h, jumps)
        k4 = _rhs(rho + dt * k3, hbar_h, jumps)
        rho = rho + (dt / 6.0) * (k1 + 2.0 * k2 + 2.0 * k3 + k4)
    _assert_density_physical(rho)
    return rho, mode, nbar


def reduced_qubit_state(joint_density: np.ndarray, fock_cutoff: int) -> np.ndarray:
    """Partial trace over the pseudomode; this is the receiver's only state."""
    d = int(fock_cutoff)
    rho = np.asarray(joint_density, dtype=complex)
    if d < 2 or rho.shape != (2 * d, 2 * d) or not np.all(np.isfinite(rho)):
        raise ValueError("joint density has invalid shape or non-finite values")
    rho4 = rho.reshape(2, d, 2, d)
    return np.einsum("aibi->ab", rho4)


def quantum_receiver_probabilities(qubit_density: np.ndarray, announced_basis: str) -> tuple[float, float]:
    """Unconditional outcome probabilities; receiver sees no input label or bath."""
    rho = _validate_qubit_density(qubit_density)
    if announced_basis == "Z":
        p0, p1 = float(rho[0, 0].real), float(rho[1, 1].real)
    elif announced_basis == "X":
        plus = 0.5 * np.array([[1.0, 1.0], [1.0, 1.0]], dtype=complex)
        p0 = float(np.trace(plus @ rho).real)
        p1 = 1.0 - p0
    else:
        raise ValueError("announced_basis must be 'Z' or 'X'")
    if not math.isfinite(p0) or not math.isfinite(p1) or min(p0, p1) < -1e-8 or max(p0, p1) > 1.0 + 1e-8:
        raise ArithmeticError("readout probabilities are nonphysical")
    total = p0 + p1
    if abs(total - 1.0) > 1e-8:
        raise ArithmeticError("readout probabilities do not sum to one")
    return p0 / total, p1 / total


def density_diagnostics(rho: np.ndarray) -> tuple[float, float, float]:
    """Return trace error, Hermiticity error, and minimum Hermitian eigenvalue."""
    state = np.asarray(rho, dtype=complex)
    if state.ndim != 2 or state.shape[0] != state.shape[1] or not np.all(np.isfinite(state)):
        raise ValueError("density matrix must be finite and square")
    herm_error = float(np.max(np.abs(state - state.conj().T)))
    hermitian = (state + state.conj().T) / 2.0
    trace_error = float(abs(np.trace(state) - 1.0))
    minimum_eigenvalue = float(np.min(np.linalg.eigvalsh(hermitian)))
    return trace_error, herm_error, minimum_eigenvalue


def _mode_populations(rho: np.ndarray, cutoff: int) -> np.ndarray:
    rho4 = np.asarray(rho, dtype=complex).reshape(2, cutoff, 2, cutoff)
    mode_state = np.einsum("aiaj->ij", rho4)
    return np.real(np.diag(mode_state))


def quantum_write_wait_read(config: PseudomodeConfig) -> QuantumBenchmarkResult:
    """Score four BB84 preparations; every input is measured with no rejection."""
    task = {"Z0": ("Z", 0), "Z1": ("Z", 1), "X+": ("X", 0), "X-": ("X", 1)}
    successes: dict[str, float] = {}
    trace_errors: list[float] = []
    herm_errors: list[float] = []
    minimum_eigs: list[float] = []
    mode_pops: list[np.ndarray] = []
    nbar = thermal_occupation(config.mode_frequency_rad_s, config.temperature_K)
    for label in BB84_LABELS:
        joint, _, _ = evolve_quantum_state(bb84_state(label), config)
        diag = density_diagnostics(joint)
        trace_errors.append(diag[0])
        herm_errors.append(diag[1])
        minimum_eigs.append(diag[2])
        qubit = reduced_qubit_state(joint, int(config.fock_cutoff))
        basis, bit = task[label]
        probs = quantum_receiver_probabilities(qubit, basis)
        successes[label] = probs[bit]
        mode_pops.append(_mode_populations(joint, int(config.fock_cutoff)))
    mean_mode = np.mean(np.stack(mode_pops), axis=0)
    return QuantumBenchmarkResult(
        mean_success=float(np.mean(list(successes.values()))),
        success_by_input=successes,
        input_count=len(BB84_LABELS),
        postselected_count=0,
        max_trace_error=max(trace_errors),
        max_hermiticity_error=max(herm_errors),
        minimum_eigenvalue=min(minimum_eigs),
        thermal_occupation=nbar,
        mode_population_n_ge_4=float(mean_mode[4:].sum()) if len(mean_mode) > 4 else 0.0,
        mode_edge_population=float(mean_mode[-1]),
    )


def binary_classical_write_score(alpha: float, bloch_vector: np.ndarray) -> float:
    """Optimal delayed-basis score for a valid two-outcome qubit POVM.

    The first effect is ``(alpha I + m.sigma)/2``. The receiver may choose the
    outcome-to-bit mapping after the X or Z basis is announced.
    """
    vector = np.asarray(bloch_vector, dtype=float)
    if not math.isfinite(alpha) or not 0.0 <= alpha <= 2.0:
        raise ValueError("POVM alpha must be finite and in [0, 2]")
    if vector.shape != (3,) or not np.all(np.isfinite(vector)):
        raise ValueError("POVM Bloch vector must have three finite values")
    allowed_norm = min(alpha, 2.0 - alpha)
    if float(np.linalg.norm(vector)) > allowed_norm + 1e-12:
        raise ValueError("binary POVM effect is not positive")
    return 0.5 + (abs(float(vector[0])) + abs(float(vector[2]))) / 4.0


classical_bound_one_bit = binary_classical_write_score(
    1.0, np.array([1.0 / math.sqrt(2.0), 0.0, 1.0 / math.sqrt(2.0)])
)


def _ou_sign_reliability(config: ClassicalOUConfig) -> float:
    decay = math.exp(-config.wait_s / config.tau_s)
    noise = config.stationary_std * math.sqrt(max(0.0, 1.0 - decay * decay))
    if noise == 0.0:
        return 1.0
    z = config.initial_amplitude * decay / noise
    return 0.5 * math.erfc(-z / math.sqrt(2.0))


def classical_ou_expected_score(config: ClassicalOUConfig) -> ClassicalBenchmarkResult:
    """Exact expected score for a one-bit Breidbart measurement plus OU aging."""
    chi = 2.0 * _ou_sign_reliability(config) - 1.0
    mean = 0.5 + chi * math.sqrt(2.0) / 4.0
    return ClassicalBenchmarkResult(float(mean), 0, 4, 0, 0.0, 1)


def classical_receiver(memory_value: float, announced_basis: str) -> int:
    """Receiver sees only the noisy scalar and delayed basis announcement."""
    if not math.isfinite(memory_value):
        raise ValueError("memory value must be finite")
    if announced_basis not in ("Z", "X"):
        raise ValueError("announced_basis must be 'Z' or 'X'")
    return int(memory_value < 0.0)


def classical_ou_trial_scores(
    config: ClassicalOUConfig, *, n_trials: int, seed: int
) -> ClassicalBenchmarkResult:
    """Monte Carlo estimate; seed and labels remain evaluator-side only."""
    if isinstance(n_trials, bool) or not isinstance(n_trials, int) or n_trials < 1:
        raise ValueError("n_trials must be a positive integer")
    if isinstance(seed, bool) or not isinstance(seed, (int, np.integer)):
        raise ValueError("seed must be an integer")
    rng = np.random.default_rng(int(seed))
    labels = np.array([0, 1, 2, 3], dtype=int)
    states = [bb84_state(x) for x in BB84_LABELS]
    axis = np.array([1.0 / math.sqrt(2.0), 0.0, 1.0 / math.sqrt(2.0)])
    p_plus = []
    for rho in states:
        bloch = np.array([
            float(np.trace(rho @ np.array([[0, 1], [1, 0]], dtype=complex)).real),
            float(np.trace(rho @ np.array([[0, -1j], [1j, 0]], dtype=complex)).real),
            float(np.trace(rho @ np.diag([1.0, -1.0])).real),
        ])
        p_plus.append(0.5 * (1.0 + float(axis @ bloch)))
    label_ix = rng.integers(0, len(labels), size=n_trials)
    plus = rng.random(n_trials) < np.asarray(p_plus)[label_ix]
    stored_bit = np.where(plus, 0, 1)
    decay = math.exp(-config.wait_s / config.tau_s)
    noise_std = config.stationary_std * math.sqrt(max(0.0, 1.0 - decay * decay))
    memory_value = decay * config.initial_amplitude * np.where(stored_bit == 0, 1.0, -1.0)
    if noise_std:
        memory_value = memory_value + rng.normal(0.0, noise_std, size=n_trials)
    guessed = (memory_value < 0.0).astype(int)
    target_bit = np.array([0, 1, 0, 1], dtype=int)[label_ix]
    correct = guessed == target_bit
    score = float(np.mean(correct))
    return ClassicalBenchmarkResult(
        mean_success=score,
        trial_count=n_trials,
        input_count=len(BB84_LABELS),
        postselected_count=0,
        standard_error=math.sqrt(score * (1.0 - score) / n_trials),
        memory_bits=1,
    )
