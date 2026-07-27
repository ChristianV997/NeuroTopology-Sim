"""Deterministic Kadanoff block-spin coarse graining for PITNN states."""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np

@dataclass(frozen=True)
class RGConfig:
    block_size: int = 2
    dynamic_exponent: float = 1.0
    normalize_blocks: bool = False

def block_spin_decimate(spins: np.ndarray, block_size: int = 2, normalize: bool = False) -> np.ndarray:
    """Average contiguous (time, sites, 3) blocks, dropping a remainder."""
    values = np.asarray(spins, dtype=float)
    if values.ndim != 3 or values.shape[2] != 3 or not np.all(np.isfinite(values)):
        raise ValueError("spins must be finite with shape (time, sites, 3)")
    if block_size < 1 or values.shape[1] < block_size:
        raise ValueError("block_size must be positive and no larger than sites")
    usable = values.shape[1] - values.shape[1] % block_size
    coarse = values[:, :usable].reshape(values.shape[0], usable // block_size, block_size, 3).mean(axis=2)
    if normalize:
        norms = np.linalg.norm(coarse, axis=2, keepdims=True)
        coarse = coarse / np.maximum(norms, np.finfo(float).eps)
    return coarse

def temporal_rescale(times_s: np.ndarray, block_size: int, dynamic_exponent: float = 1.0) -> np.ndarray:
    """Rescale elapsed time by b^z while preserving the initial epoch."""
    times = np.asarray(times_s, dtype=float)
    if times.ndim != 1 or len(times) < 1 or not np.all(np.isfinite(times)) or np.any(np.diff(times) <= 0):
        raise ValueError("times must be finite and strictly increasing")
    if block_size < 1 or dynamic_exponent < 0:
        raise ValueError("block_size must be positive and exponent non-negative")
    return times[0] + (times - times[0]) / float(block_size ** dynamic_exponent)

def coarse_grain_trajectory(spins: np.ndarray, times_s: np.ndarray, config: RGConfig = RGConfig()) -> tuple[np.ndarray, np.ndarray]:
    """Return mesoscopic magnetization and its rescaled time coordinate."""
    return block_spin_decimate(spins, config.block_size, config.normalize_blocks), temporal_rescale(times_s, config.block_size, config.dynamic_exponent)
