"""Streaming high-density MEG/fMRI ingestion and spatial RG coarse graining."""
from __future__ import annotations
from pathlib import Path
from typing import Iterator
import numpy as np
from scipy.signal import hilbert
from .rg_coarse_graining import block_spin_decimate


def sensor_coordinates(n_channels: int = 256) -> np.ndarray:
    """Return deterministic Fibonacci-sphere sensor coordinates in unit metres."""
    if n_channels < 3: raise ValueError("at least three sensor channels are required")
    index = np.arange(n_channels, dtype=float)
    golden = np.pi * (3.0 - np.sqrt(5.0))
    z = 1.0 - 2.0 * (index + 0.5) / n_channels
    radius = np.sqrt(np.maximum(0.0, 1.0-z*z))
    return np.column_stack((radius*np.cos(golden*index), radius*np.sin(golden*index), z))

def _array_source(path: Path) -> np.ndarray:
    if path.suffix.lower() == ".npy": return np.load(path, mmap_mode="r", allow_pickle=False)
    if path.suffix.lower() == ".npz":
        with np.load(path, allow_pickle=False) as bundle:
            key = "data" if "data" in bundle else bundle.files[0]
            return np.asarray(bundle[key], dtype=float)
    raise ValueError("high-density input must be .npy or .npz")

def iter_sensor_chunks(path: str | Path, chunk_samples: int = 256) -> Iterator[np.ndarray]:
    """Yield finite `(time, 256)` chunks without materializing NPY input."""
    if chunk_samples < 1: raise ValueError("chunk_samples must be positive")
    array = _array_source(Path(path))
    values = np.asarray(array)
    if values.ndim == 4: values = values.reshape(values.shape[0], -1)
    if values.ndim != 2 or values.shape[1] != 256: raise ValueError("input must have shape (samples, 256) or (samples,x,y,z) with 256 voxels")
    for start in range(0, values.shape[0], chunk_samples):
        chunk = np.asarray(values[start:start+chunk_samples], dtype=float)
        if not np.all(np.isfinite(chunk)): raise ValueError("input contains non-finite values")
        yield chunk

def chunk_to_spin_field(chunk: np.ndarray) -> np.ndarray:
    """Map one sensor chunk into a unit vector field `(time,256,3)`."""
    values = np.asarray(chunk, dtype=float)
    if values.ndim != 2 or values.shape[1] != 256 or not np.all(np.isfinite(values)): raise ValueError("chunk must be finite with 256 channels")
    centered = values - values.mean(axis=0, keepdims=True)
    normalized = centered / np.maximum(centered.std(axis=0, keepdims=True), np.finfo(float).eps)
    phase = np.angle(hilbert(normalized, axis=0))
    field = np.stack((np.cos(phase), np.sin(phase), np.tanh(normalized)), axis=2)
    return field / np.maximum(np.linalg.norm(field, axis=2, keepdims=True), np.finfo(float).eps)

def iter_rg_fields(path: str | Path, block_size: int = 4, chunk_samples: int = 256) -> Iterator[np.ndarray]:
    """Yield spatially coarse `(time, 256/block_size, 3)` fields per chunk."""
    if block_size not in {4, 8}: raise ValueError("block_size must be 4 or 8 for the high-density pipeline")
    for chunk in iter_sensor_chunks(path, chunk_samples):
        yield block_spin_decimate(chunk_to_spin_field(chunk), block_size, normalize=True)

def synthetic_meg_256(n_samples: int = 1024, seed: int = 0) -> np.ndarray:
    """Return deterministic 256-channel validation data, labelled synthetic."""
    if n_samples < 16: raise ValueError("n_samples must be at least 16")
    rng = np.random.default_rng(seed); time = np.linspace(0, 8*np.pi, n_samples, endpoint=False)
    channel_phase = np.linspace(0, 2*np.pi, 256, endpoint=False)
    return np.sin(time[:,None] + channel_phase[None,:]) + .15*np.sin(3*time[:,None]-2*channel_phase[None,:]) + .02*rng.normal(size=(n_samples,256))
