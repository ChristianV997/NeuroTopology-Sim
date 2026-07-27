"""Estimate an OQuPy-ready bath spectrum from an atomistic MD trajectory.

The default gap model is an electrostatic Stark-gap proxy:
``DeltaE(t) = -mu_TRP dot E_env(t)``.  It requires per-atom charges in the
MD topology and is not a substitute for QM/MM excitation energies.  A direct
``--gap-series`` input can be used when a QM/MM or diabatic energy-gap series
has already been computed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

import numpy as np

K_B = 1.380649e-23
H_BAR = 1.054571817e-34
EPS0 = 8.8541878128e-12
COULOMB = 1.0 / (4.0 * np.pi * EPS0)
DEBYE = 3.33564e-30
ANGSTROM = 1e-10
ELEMENTARY_CHARGE = 1.602176634e-19


def _fft_autocorrelation(values: np.ndarray) -> np.ndarray:
    """Return an unbiased real autocorrelation in O(N log N) time."""
    x = np.asarray(values, float).reshape(-1)
    x = x - np.mean(x)
    n = x.size
    padded = np.zeros(2 * n, float)
    padded[:n] = x
    spectrum = np.fft.rfft(padded)
    correlation = np.fft.irfft(spectrum * spectrum.conj(), n=padded.size)[:n]
    return np.asarray(correlation / np.arange(n, 0, -1), float)


def _gap_from_md(topology: Path, trajectory: Path, site_selection: str, environment_selection: str, dipole_debye: np.ndarray, dt_s: float | None) -> tuple[np.ndarray, float]:
    """Stream MD frames and calculate electrostatic TRP gap fluctuations in joules."""
    try:
        import MDAnalysis as mda
    except ImportError as exc:
        raise RuntimeError("MDAnalysis is required for --topology/--trajectory mode") from exc
    universe = mda.Universe(str(topology), str(trajectory), in_memory=False)
    site = universe.select_atoms(site_selection)
    environment = universe.select_atoms(environment_selection)
    if site.n_atoms == 0 or environment.n_atoms == 0:
        raise ValueError("site and environment selections must both contain atoms")
    charges = np.asarray(environment.charges, float)
    if charges.shape != (environment.n_atoms,) or not np.all(np.isfinite(charges)) or np.allclose(charges, 0.0):
        raise ValueError("environment atoms must have finite nonzero partial charges in the topology")
    mu = np.asarray(dipole_debye, float).reshape(3) * DEBYE
    gaps: list[float] = []
    observed_dt_s = None
    for timestep in universe.trajectory:
        # MDAnalysis reports trajectory dt in picoseconds.
        observed_dt_s = float(timestep.dt) * 1e-12 if timestep.dt is not None else observed_dt_s
        site_position = np.mean(site.positions, axis=0) * ANGSTROM
        displacement = site_position[None, :] - environment.positions * ANGSTROM
        dimensions = np.asarray(timestep.dimensions[:3], float) * ANGSTROM if timestep.dimensions is not None else None
        if dimensions is not None and np.all(dimensions > 0):
            displacement -= np.rint(displacement / dimensions) * dimensions
        distances = np.linalg.norm(displacement, axis=1)
        if np.any(distances <= 1e-12):
            raise ValueError("environment selection contains an atom coincident with the TRP site")
        electric_field = COULOMB * np.sum((charges * ELEMENTARY_CHARGE / distances[:, None] ** 3) * displacement, axis=0)
        gaps.append(float(-np.dot(mu, electric_field)))
    if len(gaps) < 4:
        raise ValueError("at least four MD frames are required")
    step = float(dt_s if dt_s is not None else observed_dt_s or 0.0)
    if step <= 0:
        raise ValueError("trajectory timestep is unavailable; pass --dt-fs")
    return np.asarray(gaps, float), step


def _load_gap_series(path: Path, dt_s: float) -> tuple[np.ndarray, float]:
    """Load a QM/MM excitation-gap CSV with one finite joule value per row."""
    values = np.loadtxt(path, delimiter=",", ndmin=1, dtype=float)
    values = np.asarray(values).reshape(-1)
    if values.size < 4 or not np.all(np.isfinite(values)):
        raise ValueError("gap-series CSV must contain at least four finite joule values")
    return values, dt_s


def calculate_spectral_density(gap_j: np.ndarray, dt_s: float, temperature_K: float) -> dict[str, np.ndarray | float | str]:
    """Apply a harmonic quantum correction and return SI/OQuPy spectral arrays.

    ``S_classical(omega)`` is the two-sided classical gap spectrum obtained
    from the unbiased autocorrelation.  The correction
    ``x/tanh(x), x=beta*hbar*omega/2`` produces a symmetrized quantum spectrum.
    The reported energy spectral density uses
    ``J(omega)=omega*S_quantum(omega)/(2*k_B*T)`` and therefore has joule units.
    This convention is recorded explicitly for the downstream adapter.
    """
    if dt_s <= 0 or temperature_K <= 0:
        raise ValueError("dt_s and temperature_K must be positive")
    correlation = _fft_autocorrelation(gap_j)
    n = correlation.size
    frequencies = np.fft.rfftfreq(2 * n, dt_s)
    omega = 2.0 * np.pi * frequencies
    spectrum = np.maximum(0.0, 2.0 * dt_s * np.real(np.fft.rfft(correlation, n=2 * n)))
    x = H_BAR * omega / (2.0 * K_B * temperature_K)
    correction = np.ones_like(x)
    nonzero = x != 0
    correction[nonzero] = x[nonzero] / np.tanh(x[nonzero])
    quantum_spectrum = spectrum * correction
    spectral_density = omega * quantum_spectrum / (2.0 * K_B * temperature_K)
    spectral_density[0] = 0.0
    return {"omega_s": omega, "correlation_J2": correlation, "classical_spectrum_J2_s": spectrum, "quantum_correction": correction, "quantum_spectrum_J2_s": quantum_spectrum, "spectral_density_J": spectral_density, "reorganization_energy_estimate_J": float(np.trapz(spectral_density[1:] / omega[1:], omega[1:]) / np.pi), "temperature_K": float(temperature_K), "dt_s": float(dt_s), "convention": "J(omega)=omega*S_quantum(omega)/(2*k_B*T); SI energy spectral density"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--gap-series", type=Path)
    source.add_argument("--topology", type=Path)
    parser.add_argument("--trajectory", type=Path)
    parser.add_argument("--site-selection", default="resname TRP and resid 21")
    parser.add_argument("--environment-selection", default="not resname TRP")
    parser.add_argument("--dipole-debye", nargs=3, type=float, default=[2.1, 0.0, 0.0])
    parser.add_argument("--dt-fs", type=float)
    parser.add_argument("--temperature-K", type=float, default=310.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.gap_series is not None:
        if args.dt_fs is None:
            parser.error("--dt-fs is required with --gap-series")
        gaps, dt_s = _load_gap_series(args.gap_series, args.dt_fs * 1e-15)
        source_kind = "qm_mm_gap_series"
    else:
        if args.trajectory is None:
            parser.error("--trajectory is required with --topology")
        gaps, dt_s = _gap_from_md(args.topology, args.trajectory, args.site_selection, args.environment_selection, np.asarray(args.dipole_debye), None if args.dt_fs is None else args.dt_fs * 1e-15)
        source_kind = "md_electrostatic_stark_proxy"
    result = calculate_spectral_density(gaps, dt_s, args.temperature_K)
    json_payload = {"schema": "ScienceR-Dsim.MDSpectralDensity.v1", "source_kind": source_kind, "n_frames": int(gaps.size), "gap_mean_J": float(np.mean(gaps)), "gap_std_J": float(np.std(gaps)), "omega_s": np.asarray(result["omega_s"]).tolist(), "spectral_density_J": np.asarray(result["spectral_density_J"]).tolist(), "reorganization_energy_estimate_J": result["reorganization_energy_estimate_J"], "dt_s": result["dt_s"], "temperature_K": result["temperature_K"], "convention": result["convention"]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.with_suffix(".json").write_text(json.dumps(json_payload, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    np.savez_compressed(args.output.with_suffix(".npz"), gap_j=gaps, omega_s=np.asarray(result["omega_s"]), correlation_J2=np.asarray(result["correlation_J2"]), spectral_density_J=np.asarray(result["spectral_density_J"]), temperature_K=np.asarray(args.temperature_K), dt_s=np.asarray(dt_s))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
