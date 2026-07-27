"""Offline macro-to-micro inversion with a lightweight winding TDA proxy."""
from pathlib import Path
import csv
import numpy as np


def load_signal(path: str | Path) -> tuple[np.ndarray, str]:
    """Load one numeric column from CSV or a one-dimensional NPY array."""
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(path)
    if path.suffix.lower() == ".npy":
        values = np.asarray(np.load(path), dtype=float).reshape(-1)
    elif path.suffix.lower() == ".csv":
        with path.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.reader(handle))
        try:
            values = np.asarray([float(row[-1]) for row in rows if row], dtype=float)
        except (ValueError, IndexError) as exc:
            raise ValueError("CSV must contain numeric values in its final column") from exc
    else:
        raise ValueError("input must be .csv or .npy")
    if values.size < 4 or not np.all(np.isfinite(values)):
        raise ValueError("signal must contain at least four finite values")
    return values, "empirical_csv" if path.suffix.lower() == ".csv" else "empirical_npy"


def synthetic_signal(n: int = 256, seed: int = 0) -> np.ndarray:
    if n < 4:
        raise ValueError("n must be >= 4")
    rng = np.random.default_rng(seed)
    t = np.linspace(0.0, 4.0 * np.pi, n, endpoint=False)
    return np.sin(t) + 0.25 * np.sin(3.0 * t + 0.2) + 0.03 * rng.normal(size=n)


def invert_macro_signal(signal: np.ndarray, sample_rate_hz: float = 100.0) -> dict:
    """Extract a bounded winding/cycle proxy and invert phenomenological rates."""
    y = np.asarray(signal, dtype=float).reshape(-1)
    if y.size < 4 or not np.all(np.isfinite(y)) or sample_rate_hz <= 0:
        raise ValueError("finite signal of length >= 4 and positive sample rate required")
    centered = y - np.mean(y)
    analytic = centered + 1j * np.imag(np.fft.ifft(1j * np.sign(np.fft.fftfreq(y.size)) * np.fft.fft(centered)))
    phase = np.unwrap(np.angle(analytic + 1e-12))
    cycles = abs(float(phase[-1] - phase[0]) / (2.0 * np.pi))
    beta_1 = int(max(0, round(cycles)))
    charge = float(np.mean(np.sign(np.diff(centered)))) if y.size > 1 else 0.0
    amplitude = float(np.std(centered))
    gamma_pump = float(sample_rate_hz * (1.0 + amplitude) * (1.0 + beta_1))
    ciss_strength = float(abs(charge) * (1.0 + beta_1))
    return {"beta_1": beta_1, "q_emp_mean": charge, "amplitude": amplitude,
            "gamma_pump_hz": gamma_pump, "ciss_spin_orbit_strength": ciss_strength,
            "n_samples": int(y.size)}


def invert_macro_signal_accelerated(signal: np.ndarray, sample_rate_hz: float = 100.0,
                                    max_points: int = 512) -> dict:
    """Return standard inversion plus bounded sparse graph beta-1 proxy."""
    from .tda_accelerated import SparseTDAConfig, sparse_cycle_rank
    values = np.asarray(signal, dtype=float).reshape(-1)
    standard = invert_macro_signal(values, sample_rate_hz)
    points = np.column_stack((values[:-1], values[1:]))
    sparse = sparse_cycle_rank(points, SparseTDAConfig(max_points=max_points))
    return {**standard, "sparse_tda": sparse}

def invert_rg_magnetization(magnetization: np.ndarray, times_s: np.ndarray, sample_rate_hz: float = 100.0, block_size: int = 2) -> dict:
    """Handoff a coarse-grained magnetization field to the macro-TDA proxy."""
    from .rg_coarse_graining import block_spin_decimate, temporal_rescale
    field = np.asarray(magnetization, dtype=float)
    if field.ndim != 3 or field.shape[2] != 3: raise ValueError("magnetization must have shape (time, sites, 3)")
    coarse = block_spin_decimate(field, block_size)
    scaled = temporal_rescale(np.asarray(times_s, dtype=float), block_size)
    result = invert_macro_signal(np.linalg.norm(coarse, axis=2).mean(axis=1), sample_rate_hz)
    return {**result, "rg_block_size": int(block_size), "rg_samples": int(len(scaled)), "rg_time_end_s": float(scaled[-1])}
