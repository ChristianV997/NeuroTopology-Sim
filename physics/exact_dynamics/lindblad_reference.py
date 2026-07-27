"""Classical density-matrix reference matching the DM1 damping contract."""
from __future__ import annotations
from dataclasses import dataclass
import math
import numpy as np
from scipy.linalg import expm
from .qpu_cloud_runner import HBAR_J_S


@dataclass(frozen=True)
class LindbladReferenceConfig:
    """Markovian amplitude/phase damping rates in s^-1 on encoded qubits."""
    relaxation_time_s: float
    phase_relaxation_ratio: float = 1.0

    def __post_init__(self) -> None:
        if self.relaxation_time_s <= 0 or self.phase_relaxation_ratio <= 0: raise ValueError("relaxation parameters must be positive")

    @property
    def amplitude_rate_s(self) -> float: return 1.0 / self.relaxation_time_s

    @property
    def phase_rate_s(self) -> float: return 1.0 / (self.relaxation_time_s * self.phase_relaxation_ratio)


def _single_qubit_operator(operator: np.ndarray, qubit: int, qubit_count: int) -> np.ndarray:
    product = np.array([[1.0]], complex)
    for index in range(qubit_count): product = np.kron(product, operator if index == qubit else np.eye(2))
    return product


def jump_operators(qubit_count: int, config: LindbladReferenceConfig) -> tuple[np.ndarray, ...]:
    """Return jumps matching Braket amplitude/phase damping infinitesimal limits."""
    if qubit_count < 1: raise ValueError("qubit_count must be positive")
    sigma_minus = np.array([[0, 1], [0, 0]], complex); excited_projector = np.diag([0.0, 1.0])
    operators: list[np.ndarray] = []
    for qubit in range(qubit_count):
        operators.append(math.sqrt(config.amplitude_rate_s) * _single_qubit_operator(sigma_minus, qubit, qubit_count))
        operators.append(math.sqrt(config.phase_rate_s) * _single_qubit_operator(excited_projector, qubit, qubit_count))
    return tuple(operators)


def liouvillian(hamiltonian_J: np.ndarray, jumps: tuple[np.ndarray, ...]) -> np.ndarray:
    """Vectorized Lindblad generator using column-major density vectorization."""
    hamiltonian = np.asarray(hamiltonian_J, complex); dimension = hamiltonian.shape[0]
    if hamiltonian.shape != (dimension, dimension) or not np.allclose(hamiltonian, hamiltonian.conj().T): raise ValueError("Hamiltonian must be Hermitian square")
    identity = np.eye(dimension); generator = -1j * (np.kron(identity, hamiltonian) - np.kron(hamiltonian.T, identity)) / HBAR_J_S
    for jump in jumps:
        dagger_jump = jump.conj().T @ jump
        generator += np.kron(jump.conj(), jump) - 0.5 * (np.kron(identity, dagger_jump) + np.kron(dagger_jump.T, identity))
    return generator


def propagate_lindblad(hamiltonian_J: np.ndarray, initial_rho: np.ndarray, times_s: np.ndarray, config: LindbladReferenceConfig) -> np.ndarray:
    """Propagate a finite encoded density matrix exactly by matrix exponentiation."""
    rho = np.asarray(initial_rho, complex); times = np.asarray(times_s, float); dimension = rho.shape[0]
    if rho.shape != (dimension, dimension) or not np.allclose(rho, rho.conj().T) or not np.isclose(np.trace(rho), 1): raise ValueError("initial rho must be Hermitian trace one")
    if times.ndim != 1 or not len(times) or np.any(times < 0): raise ValueError("times_s must be non-negative 1D")
    qubits = int(round(math.log2(dimension)))
    if 1 << qubits != dimension: raise ValueError("density dimension must be a power of two")
    generator = liouvillian(hamiltonian_J, jump_operators(qubits, config)); vector = rho.reshape(-1, order="F")
    return np.asarray([(expm(generator * time) @ vector).reshape((dimension, dimension), order="F") for time in times])


def validate_density_trajectory(states: np.ndarray, *, tolerance: float = 1e-8) -> None:
    """Fail on non-finite trace, Hermiticity, or positivity violations."""
    trajectory = np.asarray(states, complex)
    if trajectory.ndim != 3 or trajectory.shape[1] != trajectory.shape[2] or not np.all(np.isfinite(trajectory)): raise ValueError("density trajectory has invalid shape or values")
    for state in trajectory:
        if abs(np.trace(state) - 1.0) > tolerance: raise ValueError("unphysical trace deviation")
        if np.linalg.norm(state - state.conj().T) > tolerance: raise ValueError("unphysical Hermiticity deviation")
        if np.min(np.linalg.eigvalsh(state).real) < -tolerance: raise ValueError("unphysical negative eigenvalue")
