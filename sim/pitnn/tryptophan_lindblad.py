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

    # Reduced Planck constant in joule-seconds (SI); shared by rhs / _rhs_into.
    _HBAR_J_S = 1.054571817e-34

    def _rhs_into(self, state: np.ndarray, out: np.ndarray,
                  sh: np.ndarray, tmp: np.ndarray, deph: np.ndarray) -> np.ndarray:
        """Evaluate the Lindblad RHS into ``out`` using caller-owned scratch.

        Numerically identical to :meth:`rhs` -- the operation order and grouping
        are preserved exactly -- but every intermediate is written into
        preallocated ``(N,N)`` complex128 buffers (``out``, ``sh``, ``tmp``,
        ``deph``) instead of allocating fresh temporaries. This lets the RK4 hot
        loop in :meth:`propagate` reuse buffers across every sub-step rather than
        churning ~15 dense arrays per evaluation. Units: density-matrix per second.
        """
        h = self.hamiltonian
        # commutator = -1j * (H @ rho - rho @ H) / hbar
        np.matmul(h, state, out=out)
        np.matmul(state, h, out=sh)
        out -= sh
        out *= -1j
        out /= self._HBAR_J_S
        # radiative = -0.5 * (gamma_rad @ rho + rho @ gamma_rad)
        np.matmul(self.gamma_rad, state, out=sh)
        np.matmul(state, self.gamma_rad, out=tmp)
        sh += tmp
        sh *= -0.5
        out += sh
        # dephasing = -gamma_dephasing * offdiagonal(rho)
        np.copyto(deph, state)
        np.fill_diagonal(deph, 0.0)
        deph *= -self.config.gamma_dephasing_s
        out += deph
        # phonon dissipator = -phonon_rate * offdiagonal(rho)  (populations conserved)
        np.copyto(tmp, state)
        np.fill_diagonal(tmp, 0.0)
        tmp *= -self.config.phonon_rate_s
        out += tmp
        return out

    def rhs(self, rho: np.ndarray) -> np.ndarray:
        """Evaluate the Lindblad RHS in density-matrix units per second."""
        state = np.asarray(rho, complex)
        n = len(self.positions)
        if state.shape != (n, n):
            raise ValueError(f"rho must have shape {(n, n)}")
        out = np.empty((n, n), dtype=complex)
        sh = np.empty((n, n), dtype=complex)
        tmp = np.empty((n, n), dtype=complex)
        deph = np.empty((n, n), dtype=complex)
        return self._rhs_into(state, out, sh, tmp, deph)

    def propagate(self, rho0: np.ndarray, times_s: np.ndarray) -> np.ndarray:
        """Propagate with fixed-step RK4, returning (time,N,N) complex states."""
        times = np.asarray(times_s, float)
        rho = np.asarray(rho0, complex).copy()
        n = len(self.positions)
        if times.ndim != 1 or len(times) < 1 or np.any(np.diff(times) <= 0) or rho.shape != (n, n):
            raise ValueError("times must be strictly increasing and rho0 must be shape (N,N)")
        history = np.empty((len(times), n, n), complex)
        history[0] = rho
        # Preallocated RK4 stage + RHS scratch buffers, reused every step instead
        # of allocating fresh (N,N) temporaries. The arithmetic below reproduces
        # the exact RK4 update `rho + dt*(k1 + 2*k2 + 2*k3 + k4)/6` and the
        # Hermitian symmetrization, in the same operation order (bit-identical).
        k1 = np.empty((n, n), complex); k2 = np.empty((n, n), complex)
        k3 = np.empty((n, n), complex); k4 = np.empty((n, n), complex)
        stage = np.empty((n, n), complex); acc = np.empty((n, n), complex)
        conj = np.empty((n, n), complex)
        sh = np.empty((n, n), complex); tmp = np.empty((n, n), complex); deph = np.empty((n, n), complex)
        for i, dt in enumerate(np.diff(times), 1):
            self._rhs_into(rho, k1, sh, tmp, deph)
            np.multiply(k1, dt, out=stage); stage /= 2.0; stage += rho          # rho + dt*k1/2
            self._rhs_into(stage, k2, sh, tmp, deph)
            np.multiply(k2, dt, out=stage); stage /= 2.0; stage += rho          # rho + dt*k2/2
            self._rhs_into(stage, k3, sh, tmp, deph)
            np.multiply(k3, dt, out=stage); stage += rho                        # rho + dt*k3
            self._rhs_into(stage, k4, sh, tmp, deph)
            # acc = k1 + 2*k2 + 2*k3 + k4  (same left-to-right grouping)
            np.multiply(k2, 2.0, out=acc); acc += k1
            np.multiply(k3, 2.0, out=stage); acc += stage
            acc += k4
            acc *= dt; acc /= 6.0
            rho += acc                                                          # rho + dt*(...)/6
            np.conjugate(rho, out=conj); rho += conj.T; rho /= 2.0              # (rho + rho^H)/2
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
