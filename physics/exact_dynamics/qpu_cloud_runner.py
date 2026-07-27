"""Fail-closed AWS Braket evaluator for unitary Hamiltonian subroutines.

This module maps a local SI-unit Hamiltonian to a first-order Trotter circuit.
It deliberately does *not* model bath dissipation, decoherence, or
non-Markovian memory; a successful task therefore validates only this unitary
subroutine and never a biological-coherence hypothesis.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import importlib.util
import math
from pathlib import Path
import time
from typing import Any, Iterable, Sequence

import numpy as np

HBAR_J_S = 1.054571817e-34
DM1_ARN = "arn:aws:braket:::device/quantum-simulator/amazon/dm1"
_FAIL_PREFIX = "FALSIFIED: NOISE_DOMINANT"


@dataclass(frozen=True)
class QpuCloudConfig:
    """Remote execution configuration; time values are SI seconds."""

    device_arn: str = DM1_ARN
    shots: int = 0
    trotter_steps: int = 1
    max_qubits: int = 8
    s3_destination_folder: tuple[str, str] | None = None
    temperature_K: float = 310.0
    relaxation_time_s: float | None = None
    phase_relaxation_ratio: float = 1.0
    chiral_pairs: tuple[tuple[int, int], ...] = ((0, 1),)
    poll_timeout_s: float = 900.0
    poll_interval_s: float = 2.0

    def __post_init__(self) -> None:
        if self.shots != 0 or self.trotter_steps < 1 or not 1 <= self.max_qubits <= 8:
            raise ValueError("shots, trotter_steps, and max_qubits are invalid")
        if (self.temperature_K <= 0 or self.phase_relaxation_ratio <= 0
                or self.poll_timeout_s <= 0 or self.poll_interval_s <= 0
                or (self.relaxation_time_s is not None and self.relaxation_time_s <= 0)):
            raise ValueError("density-matrix bath parameters are invalid")


@dataclass(frozen=True)
class PauliTerm:
    """One real coefficient in joules times an N-qubit Pauli word."""

    coefficient_J: float
    word: str


class QuantumCloudEvaluator:
    """Build and execute a Braket unitary circuit from local TD-DFT Hamiltonian data.

    The input NPZ must contain ``H_sys_si`` (finite Hermitian square matrix in
    joules) and scalar string ``hamiltonian_unit`` exactly equal to ``"J"``.
    Matrices are embedded in the next power-of-two computational subspace.
    """

    def __init__(self, tddft_npz: str | Path, config: QpuCloudConfig = QpuCloudConfig()) -> None:
        self.config = config
        self.input_path = Path(tddft_npz).resolve()
        self._fail_if_unavailable()
        self.hamiltonian_J = self._load_hamiltonian(self.input_path)
        self.site_count = self.hamiltonian_J.shape[0]
        self.qubit_count = int(math.ceil(math.log2(self.site_count))) if self.site_count > 1 else 1
        if self.qubit_count > config.max_qubits:
            raise RuntimeError(f"{_FAIL_PREFIX}: Pauli expansion requires {self.qubit_count} qubits, above configured maximum {config.max_qubits}")
        self.embedded_hamiltonian_J = self._embed_hamiltonian(self.hamiltonian_J, self.qubit_count)
        # Imports occur only after dependency capability validation.
        from braket.quantum_information import PauliString
        self._PauliString = PauliString

    def _fail_if_unavailable(self) -> None:
        if not self.input_path.is_file():
            raise FileNotFoundError(f"{_FAIL_PREFIX}: required local TD-DFT input is missing: {self.input_path}")
        required = ("braket", "braket.aws", "braket.circuits", "braket.quantum_information", "braket.tracking")
        try:
            installed = all(importlib.util.find_spec(module) is not None for module in required)
        except ModuleNotFoundError:
            installed = False
        if not installed:
            raise RuntimeError(f"{_FAIL_PREFIX}: Amazon Braket SDK dependencies are missing; install amazon-braket-sdk before cloud execution")

    @staticmethod
    def _load_hamiltonian(path: Path) -> np.ndarray:
        try:
            with np.load(path, allow_pickle=False) as data:
                if "H_sys_si" not in data.files or "hamiltonian_unit" not in data.files:
                    raise ValueError("NPZ requires H_sys_si and hamiltonian_unit")
                unit = str(np.asarray(data["hamiltonian_unit"]).item())
                matrix = np.asarray(data["H_sys_si"], dtype=complex)
        except (OSError, ValueError) as exc:
            raise RuntimeError(f"{_FAIL_PREFIX}: invalid TD-DFT NPZ input: {exc}") from exc
        if unit != "J": raise RuntimeError(f"{_FAIL_PREFIX}: H_sys_si must declare SI unit 'J', got {unit!r}")
        if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1] or matrix.shape[0] < 2:
            raise RuntimeError(f"{_FAIL_PREFIX}: H_sys_si must be a square matrix of dimension at least two")
        if not np.all(np.isfinite(matrix)) or not np.allclose(matrix, matrix.conj().T, atol=1e-30, rtol=1e-10):
            raise RuntimeError(f"{_FAIL_PREFIX}: H_sys_si must be finite and Hermitian in joules")
        return matrix

    @staticmethod
    def _embed_hamiltonian(hamiltonian_J: np.ndarray, qubit_count: int) -> np.ndarray:
        dimension = 1 << qubit_count
        embedded = np.zeros((dimension, dimension), dtype=complex)
        embedded[:hamiltonian_J.shape[0], :hamiltonian_J.shape[1]] = hamiltonian_J
        return embedded

    @staticmethod
    def _pauli_words(qubit_count: int) -> Iterable[str]:
        alphabet = "IXYZ"
        for integer in range(4 ** qubit_count):
            digits: list[str] = []
            value = integer
            for _ in range(qubit_count):
                digits.append(alphabet[value % 4]); value //= 4
            yield "".join(reversed(digits))

    @staticmethod
    def _pauli_matrix(word: str) -> np.ndarray:
        matrices = {"I": np.eye(2, dtype=complex), "X": np.array([[0, 1], [1, 0]], complex),
                    "Y": np.array([[0, -1j], [1j, 0]], complex), "Z": np.array([[1, 0], [0, -1]], complex)}
        product = np.array([[1]], dtype=complex)
        for symbol in word: product = np.kron(product, matrices[symbol])
        return product

    def pauli_decomposition(self, *, coefficient_tolerance_J: float = 1e-30) -> tuple[PauliTerm, ...]:
        """Return the exact finite Pauli-basis decomposition of the padded H.

        ``PauliString`` is constructed for every retained word to enforce the
        Braket tensor-product representation before circuit synthesis.
        """
        if coefficient_tolerance_J < 0: raise ValueError("coefficient_tolerance_J must be non-negative")
        dimension = self.embedded_hamiltonian_J.shape[0]; terms: list[PauliTerm] = []
        for word in self._pauli_words(self.qubit_count):
            _ = self._PauliString(word)
            coefficient = np.trace(self._pauli_matrix(word) @ self.embedded_hamiltonian_J) / dimension
            if abs(coefficient.imag) > max(coefficient_tolerance_J, 1e-24):
                raise RuntimeError(f"{_FAIL_PREFIX}: Hermitian Pauli coefficient unexpectedly complex for {word}")
            if abs(coefficient.real) > coefficient_tolerance_J:
                terms.append(PauliTerm(float(coefficient.real), word))
        return tuple(terms)

    @staticmethod
    def _append_pauli_exponential(circuit: Any, term: PauliTerm, delta_t_s: float) -> None:
        """Append exp(-i coefficient * PauliWord * dt / hbar) using native gates."""
        support = [index for index, symbol in enumerate(term.word) if symbol != "I"]
        if not support: return  # global phase has no observable effect
        for qubit in support:
            symbol = term.word[qubit]
            if symbol == "X": circuit.h(qubit)
            elif symbol == "Y": circuit.rz(qubit, -np.pi / 2).h(qubit)
        for control, target in zip(support[:-1], support[1:]): circuit.cnot(control, target)
        angle = 2.0 * term.coefficient_J * delta_t_s / HBAR_J_S
        circuit.rz(support[-1], float(angle))
        for control, target in reversed(tuple(zip(support[:-1], support[1:]))): circuit.cnot(control, target)
        for qubit in reversed(support):
            symbol = term.word[qubit]
            if symbol == "X": circuit.h(qubit)
            elif symbol == "Y": circuit.h(qubit).rz(qubit, np.pi / 2)

    def _relaxation_time_s(self) -> float:
        """Return the predeclared phenomenological bath limit in seconds.

        At 10 K and 310 K the anchors are 1.76 ns and 0.95 ns respectively;
        intermediate temperatures are linearly interpolated and are explicitly
        a noise-model assumption, not an ab-initio bath calculation.
        """
        if self.config.relaxation_time_s is not None: return self.config.relaxation_time_s
        fraction = float(np.clip((self.config.temperature_K - 10.0) / 300.0, 0.0, 1.0))
        return (1.76e-9 * (1.0 - fraction)) + (0.95e-9 * fraction)

    def _append_dissipators(self, circuit: Any, delta_t_s: float) -> None:
        """Append deterministic amplitude/phase damping after one Suzuki block."""
        tau = self._relaxation_time_s()
        amplitude_probability = float(1.0 - np.exp(-delta_t_s / tau))
        phase_probability = float(1.0 - np.exp(-delta_t_s / (tau * self.config.phase_relaxation_ratio)))
        for qubit in range(self.qubit_count):
            circuit.amplitude_damping(qubit, amplitude_probability)
            circuit.phase_damping(qubit, phase_probability)

    def build_chiral_current_observable(self, site_i: int, site_j: int) -> Any:
        """Map i(a†_i a_j-a†_j a_i) to a Jordan-Wigner Pauli observable sum.

        For i<j, J_ij = 1/2 (X_i Z...Z Y_j - Y_i Z...Z X_j).  The encoded
        site indices must be distinct physical sites in the local Hamiltonian.
        """
        if not (0 <= site_i < self.site_count and 0 <= site_j < self.site_count) or site_i == site_j:
            raise ValueError("chiral current sites must be distinct valid local Hamiltonian indices")
        from braket.circuits import Observable
        # The two-site snapshot uses the compact |site 0>, |site 1> encoding
        # in one qubit. Its current i(a0^dagger a1-a1^dagger a0) is -Y.
        # Braket's OpenQASM serializer does not accept a negative scalar
        # observable (it emits invalid ``-1.0 * y(...)`` syntax), so expose
        # the positive Y representative and keep the compact orientation
        # convention in the telemetry schema. The magnitude and dynamics are
        # unchanged; callers needing the signed convention multiply by -1 for
        # the ordered pair (0, 1).
        if self.site_count == 2 and self.qubit_count == 1:
            return Observable.Y()
        if self.site_count != self.qubit_count:
            raise RuntimeError(
                f"{_FAIL_PREFIX}: chiral-current Jordan-Wigner observables require one qubit per site; "
                f"the compact {self.site_count}-site/{self.qubit_count}-qubit encoding is unsupported"
            )
        left, right = sorted((site_i, site_j))
        def observable(first: str, last: str) -> Any:
            word = ["I"] * self.qubit_count; word[left] = first; word[right] = last
            for index in range(left + 1, right): word[index] = "Z"
            word_string = "".join(word); _ = self._PauliString(word_string)
            factors = {"I": Observable.I, "X": Observable.X, "Y": Observable.Y, "Z": Observable.Z}
            value = factors[word[0]]()
            for symbol in word[1:]: value = value @ factors[symbol]()
            return value
        forward = observable("X", "Y"); backward = observable("Y", "X")
        sign = 1.0 if site_i < site_j else -1.0
        return sign * 0.5 * forward - sign * 0.5 * backward

    def build_circuit(self, time_s: float) -> Any:
        """Create DM1 second-order Suzuki evolution, noise, and density telemetry."""
        if not np.isfinite(time_s) or time_s < 0: raise ValueError("time_s must be finite and non-negative seconds")
        from braket.circuits import Circuit, Observable
        circuit = Circuit(); delta_t_s = time_s / self.config.trotter_steps
        terms = self.pauli_decomposition()
        for _ in range(self.config.trotter_steps):
            # Symmetric second-order Suzuki: forward half step then reverse half step.
            for term in terms: self._append_pauli_exponential(circuit, term, delta_t_s / 2.0)
            for term in reversed(terms): self._append_pauli_exponential(circuit, term, delta_t_s / 2.0)
            self._append_dissipators(circuit, delta_t_s)
        circuit.expectation(observable=Observable.Z(), target=0)
        for pair in self.config.chiral_pairs:
            circuit.expectation(observable=self.build_chiral_current_observable(*pair), target=list(range(self.qubit_count)))
        circuit.density_matrix(target=list(range(self.qubit_count)))
        return circuit

    @staticmethod
    def _aws_duration_s(metadata: dict[str, object], start_key: str, end_key: str) -> float | None:
        """Decode Braket ISO timestamps; return ``None`` if AWS omits either field."""
        start, end = metadata.get(start_key), metadata.get(end_key)
        if not isinstance(start, str) or not isinstance(end, str):
            return None
        try:
            return float((datetime.fromisoformat(end.replace("Z", "+00:00")) - datetime.fromisoformat(start.replace("Z", "+00:00"))).total_seconds())
        except ValueError:
            return None

    def run(self, time_points_s: Sequence[float]) -> dict[str, object]:
        """Submit one task per requested time and return observable evidence plus cost telemetry."""
        times = np.asarray(time_points_s, dtype=float)
        if times.ndim != 1 or times.size == 0 or not np.all(np.isfinite(times)) or np.any(times < 0):
            raise ValueError("time_points_s must be a non-empty finite non-negative 1D sequence in seconds")
        from braket.aws import AwsDevice
        from braket.tracking import Tracker
        if self.config.device_arn != DM1_ARN:
            raise RuntimeError(f"{_FAIL_PREFIX}: QPU override cannot satisfy DM1 density-matrix/noise telemetry contract")
        device = AwsDevice(self.config.device_arn)
        expectations: list[float] = []; survival: list[float] = []; currents: list[list[float]] = []; density_telemetry: list[dict[str, object]] = []; task_ids: list[str] = []; task_durations: list[float] = []; task_timing: list[dict[str, float | None]] = []
        with Tracker() as tracker:
            for time_s in times:
                circuit = self.build_circuit(float(time_s))
                kwargs: dict[str, object] = {"shots": self.config.shots}
                if self.config.s3_destination_folder is not None: kwargs["s3_destination_folder"] = self.config.s3_destination_folder
                started = time.monotonic()
                task = device.run(circuit, **kwargs)
                terminal_failures = {"FAILED", "CANCELLED"}
                while True:
                    state = str(task.state()).upper()
                    if state == "COMPLETED":
                        break
                    if state in terminal_failures:
                        raise RuntimeError(f"{_FAIL_PREFIX}: DM1 task {task.id} terminated with state {state}")
                    if time.monotonic() - started > self.config.poll_timeout_s:
                        raise TimeoutError(f"{_FAIL_PREFIX}: DM1 task {task.id} exceeded {self.config.poll_timeout_s:g} s polling timeout")
                    time.sleep(self.config.poll_interval_s)
                result = task.result(); values = result.values
                try:
                    metadata = dict(task.metadata())
                except Exception:
                    metadata = {}
                expectation = float(values[0]); current_values = [float(value) for value in values[1:1 + len(self.config.chiral_pairs)]]
                density = np.asarray(values[-1], dtype=complex)
                # DM1 may serialize a density-matrix result as ``(1, N, N)``
                # (one result axis) rather than directly as ``(N, N)``.
                # Remove singleton result axes, then enforce the physical
                # square-matrix contract before calculating telemetry.
                # The current Braket SDK returns complex matrices as a
                # ``(2, N, N)`` real/imaginary payload; decode that contract
                # before squeezing singleton result axes.
                if density.ndim == 3 and density.shape[-1] == 2 and density.shape[0] == density.shape[1]:
                    density = density[..., 0] + 1j * density[..., 1]
                elif density.ndim == 3 and density.shape[0] == 2 and density.shape[1] == density.shape[2]:
                    density = density[0] + 1j * density[1]
                density = np.squeeze(density)
                if density.ndim != 2 or density.shape[0] != density.shape[1]:
                    raise RuntimeError(
                        f"{_FAIL_PREFIX}: DM1 returned invalid density-matrix shape {density.shape}"
                    )
                eigenvalues = np.linalg.eigvalsh(density).real
                elapsed = float(time.monotonic() - started)
                expectations.append(expectation); currents.append(current_values); survival.append(float(density[0, 0].real)); task_ids.append(str(task.id)); task_durations.append(elapsed)
                task_timing.append({"client_wall_duration_s": elapsed, "queue_duration_s": self._aws_duration_s(metadata, "createdAt", "startedAt"), "execution_duration_s": self._aws_duration_s(metadata, "startedAt", "endedAt")})
                density_telemetry.append({"trace": float(np.trace(density).real), "hermiticity_residual": float(np.linalg.norm(density - density.conj().T)),
                                          "minimum_eigenvalue": float(np.min(eigenvalues)),
                                          "matrix_real": density.real.tolist(), "matrix_imag": density.imag.tolist()})
            cost = {"simulator_cost_usd": float(tracker.simulator_tasks_cost()), "qpu_cost_usd": float(tracker.qpu_tasks_cost()),
                    "task_statistics": tracker.quantum_tasks_statistics()}
        return {"verdict": "SUPPORTED_BY_QPU", "device_arn": self.config.device_arn,
                "time_span_s": [float(times.min()), float(times.max())], "time_points_s": times.tolist(),
                "expectation_values": expectations, "chiral_current_expectation_values": currents,
                "survival_probability_site_0": survival, "density_matrix_telemetry": density_telemetry, "task_ids": task_ids,
                "task_durations_s": task_durations, "task_timing": task_timing, "total_execution_duration_s": float(sum(task_durations)),
                "execution_cost": cost, "scientific_note": "Task success supports only the requested second-order-Trotter density-matrix subroutine with phenomenological Markovian amplitude/phase damping. Structured bath dissipation and non-Markovian memory effects remain unmodeled; Z expectation is a single-qubit occupation proxy, while density_matrix[0,0] is the encoded site-0 survival probability."}
