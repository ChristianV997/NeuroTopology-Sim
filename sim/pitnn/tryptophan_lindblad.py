"""Dense single-excitation Lindblad solver with a positive phonon bath."""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np

@dataclass(frozen=True)
class LindbladConfig:
    transition_energy_eV: float = 4.43
    dielectric_constant: float = 4.0
    gamma0_s: float = 0.1e9
    gamma_dephasing_s: float = 10.0e12
    phonon_reorganization_eV: float = 0.08
    phonon_cutoff_s: float = 5.0e12
    phonon_rate_s: float = 1.0e12
    max_sites: int = 32

class TryptophanLindbladModel:
    """Construct and propagate a reduced excitonic density matrix."""
    def __init__(self, positions_m: np.ndarray, dipoles_Cm: np.ndarray, config: LindbladConfig = LindbladConfig()):
        positions, dipoles = np.asarray(positions_m, float), np.asarray(dipoles_Cm, float)
        if positions.ndim != 2 or positions.shape[1] != 3 or dipoles.shape != positions.shape:
            raise ValueError("positions and dipoles must both have shape (N,3)")
        if len(positions) > config.max_sites or not np.all(np.isfinite(positions)) or not np.all(np.isfinite(dipoles)):
            raise ValueError("invalid or oversized exciton network")
        self.positions, self.dipoles, self.config = positions, dipoles, config
        self.hamiltonian = self._build_hamiltonian()
        self.gamma_rad = self._build_radiative_rates()

    def phonon_spectral_density(self, omega_s: np.ndarray | float) -> np.ndarray:
        """Return super-Ohmic J(omega) in joules for angular rate s^-1."""
        omega = np.asarray(omega_s, dtype=float)
        if np.any(omega < 0) or not np.all(np.isfinite(omega)) or self.config.phonon_cutoff_s <= 0:
            raise ValueError("omega must be finite/non-negative and cutoff positive")
        lambda_j = self.config.phonon_reorganization_eV * 1.602176634e-19
        ratio = omega / self.config.phonon_cutoff_s
        return 2.0 * lambda_j * ratio**3 * np.exp(-ratio)

    def phonon_dissipator(self, rho: np.ndarray) -> np.ndarray:
        """Apply positive-rate pure dephasing; populations are conserved."""
        state = np.asarray(rho, dtype=complex)
        n = len(self.positions)
        if state.shape != (n, n):
            raise ValueError(f"rho must have shape {(n, n)}")
        result = -self.config.phonon_rate_s * state.copy()
        np.fill_diagonal(result, 0.0)
        return result

    def _build_hamiltonian(self) -> np.ndarray:
        n = len(self.positions)
        h = np.eye(n, dtype=complex) * self.config.transition_energy_eV * 1.602176634e-19
        displacement = self.positions[:, None, :] - self.positions[None, :, :]
        distance = np.linalg.norm(displacement, axis=-1)
        if np.any((distance + np.eye(n)) == 0):
            raise ValueError("coincident exciton positions are invalid")
        safe = np.where(distance == 0, 1.0, distance)
        mu_dot = self.dipoles @ self.dipoles.T
        mu_r = np.einsum("ik,ijk->ij", self.dipoles, displacement)
        mu_mr = np.einsum("jk,ijk->ij", self.dipoles, displacement)
        coupling = (mu_dot / safe**3 - 3.0 * mu_r * mu_mr / safe**5) / (4.0 * np.pi * 8.8541878128e-12 * self.config.dielectric_constant)
        np.fill_diagonal(coupling, 0.0)
        h += coupling
        return (h + h.conj().T) / 2.0

    def _build_radiative_rates(self) -> np.ndarray:
        norms = np.linalg.norm(self.dipoles, axis=1)
        unit = self.dipoles / np.maximum(norms[:, None], 1e-30)
        rates = self.config.gamma0_s * (unit @ unit.T)
        return (rates + rates.T) / 2.0

    def rhs(self, rho: np.ndarray) -> np.ndarray:
        """Evaluate the Lindblad RHS in density-matrix units per second."""
        state = np.asarray(rho, complex)
        n = len(self.positions)
        if state.shape != (n, n):
            raise ValueError(f"rho must have shape {(n, n)}")
        commutator = -1j * (self.hamiltonian @ state - state @ self.hamiltonian) / 1.054571817e-34
        radiative = -0.5 * (self.gamma_rad @ state + state @ self.gamma_rad)
        off_diagonal = state.copy()
        np.fill_diagonal(off_diagonal, 0.0)
        deph = -self.config.gamma_dephasing_s * off_diagonal
        return commutator + radiative + deph + self.phonon_dissipator(state)

    def propagate(self, rho0: np.ndarray, times_s: np.ndarray) -> np.ndarray:
        """Propagate with fixed-step RK4, returning (time,N,N) complex states."""
        times = np.asarray(times_s, float)
        rho = np.asarray(rho0, complex).copy()
        n = len(self.positions)
        if times.ndim != 1 or len(times) < 1 or np.any(np.diff(times) <= 0) or rho.shape != (n, n):
            raise ValueError("times must be strictly increasing and rho0 must be shape (N,N)")
        history = np.empty((len(times), n, n), complex)
        history[0] = rho
        for i, dt in enumerate(np.diff(times), 1):
            k1 = self.rhs(rho); k2 = self.rhs(rho + dt*k1/2); k3 = self.rhs(rho + dt*k2/2); k4 = self.rhs(rho + dt*k3)
            rho = rho + dt * (k1 + 2*k2 + 2*k3 + k4) / 6.0
            rho = (rho + rho.conj().T) / 2.0
            history[i] = rho
        return history

    def identify_subradiant_states(self) -> dict:
        """Return finite decay widths and phonon-limited enhancements."""
        total_width = self.gamma_rad + np.eye(len(self.positions)) * self.config.phonon_rate_s
        heff = self.hamiltonian - 0.5j * 1.054571817e-34 * total_width
        values = np.linalg.eigvals(heff)
        widths = np.maximum(0.0, -2.0 * values.imag / 1.054571817e-34)
        dark = np.flatnonzero(widths < self.config.phonon_rate_s + 0.1 * self.config.gamma0_s)
        enhancement = np.divide(self.config.gamma0_s, widths, out=np.zeros(len(widths)), where=widths > 0)
        return {"eigenvalues_J": values, "decay_widths_s": widths, "subradiant_indices": dark.tolist(), "lifetime_enhancement": enhancement.tolist()}
