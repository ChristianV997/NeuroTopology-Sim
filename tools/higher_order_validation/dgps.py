"""Deterministic data-generating processes for adversarial validation."""
from __future__ import annotations

import hashlib
from typing import Dict, Tuple

import numpy as np


def source_checksum(arr: np.ndarray) -> str:
    """SHA-256 of shape, dtype, and contiguous bytes (block-hashed)."""
    a = np.ascontiguousarray(np.asarray(arr))
    h = hashlib.sha256()
    h.update(str(a.shape).encode("utf-8"))
    h.update(b"|")
    h.update(str(a.dtype).encode("utf-8"))
    h.update(b"|")
    view = memoryview(a).cast("B")
    block = 1024 * 1024
    for start in range(0, len(view), block):
        h.update(view[start : start + block])
    return h.hexdigest()


def _rng(seed: int) -> np.random.Generator:
    return np.random.default_rng(int(seed))


def generate_independent_gaussian(
    n_channels: int = 6,
    n_samples: int = 2048,
    seed: int = 0,
) -> np.ndarray:
    """Independent Gaussian noise (negative control). Shape (n_channels, n_samples)."""
    rng = _rng(seed)
    return rng.standard_normal((n_channels, n_samples)).astype(np.float64)


def generate_pure_pairwise(
    n_channels: int = 6,
    n_samples: int = 2048,
    seed: int = 0,
    pair: Tuple[int, int] = (0, 1),
    corr: float = 0.85,
) -> np.ndarray:
    """Pure pairwise dependence between two channels; others independent."""
    rng = _rng(seed)
    x = rng.standard_normal((n_channels, n_samples))
    i, j = pair
    shared = rng.standard_normal(n_samples)
    noise = rng.standard_normal(n_samples)
    x[i] = shared
    x[j] = corr * shared + np.sqrt(max(0.0, 1.0 - corr**2)) * noise
    return x.astype(np.float64)


def generate_pure_triadic(
    n_channels: int = 6,
    n_samples: int = 2048,
    seed: int = 0,
    triad: Tuple[int, int, int] = (0, 1, 2),
) -> np.ndarray:
    """Pure triadic dependence via XOR-like multiplicative interaction.

    Pairwise correlations remain near zero while the third-order moment is large.
    """
    rng = _rng(seed)
    x = rng.standard_normal((n_channels, n_samples))
    a, b, c = triad
    u = rng.choice([-1.0, 1.0], size=n_samples)
    v = rng.choice([-1.0, 1.0], size=n_samples)
    x[a] = u
    x[b] = v
    x[c] = u * v  # triadic; pairwise E[u*v]=0, E[u*(u*v)]=0, E[v*(u*v)]=0
    # Add tiny independent noise so ranks are well-defined.
    x[a] = x[a] + 0.05 * rng.standard_normal(n_samples)
    x[b] = x[b] + 0.05 * rng.standard_normal(n_samples)
    x[c] = x[c] + 0.05 * rng.standard_normal(n_samples)
    return x.astype(np.float64)


def generate_amplitude_modulation(
    n_channels: int = 6,
    n_samples: int = 2048,
    seed: int = 0,
    carrier_hz: float = 10.0,
    mod_hz: float = 1.0,
    fs: float = 128.0,
) -> np.ndarray:
    """Amplitude-modulated carrier on channel 0; others independent."""
    rng = _rng(seed)
    t = np.arange(n_samples) / fs
    envelope = 1.0 + 0.8 * np.sin(2 * np.pi * mod_hz * t)
    carrier = np.sin(2 * np.pi * carrier_hz * t)
    x = rng.standard_normal((n_channels, n_samples))
    x[0] = envelope * carrier + 0.1 * rng.standard_normal(n_samples)
    return x.astype(np.float64)


def generate_common_driver(
    n_channels: int = 6,
    n_samples: int = 2048,
    seed: int = 0,
    targets: Tuple[int, int] = (1, 2),
    driver_channel: int = 0,
    strength: float = 0.9,
) -> np.ndarray:
    """Common-driver confounding: driver drives two targets (spurious pairwise)."""
    rng = _rng(seed)
    x = rng.standard_normal((n_channels, n_samples))
    driver = rng.standard_normal(n_samples)
    x[driver_channel] = driver
    for t in targets:
        x[t] = strength * driver + np.sqrt(max(0.0, 1.0 - strength**2)) * rng.standard_normal(
            n_samples
        )
    return x.astype(np.float64)


def generate_temporal_smoothing(
    n_channels: int = 6,
    n_samples: int = 2048,
    seed: int = 0,
    ar_coef: float = 0.9,
) -> np.ndarray:
    """Temporally smoothed (AR(1)) independent channels — autocorrelation confound."""
    rng = _rng(seed)
    innov = rng.standard_normal((n_channels, n_samples))
    x = np.zeros_like(innov)
    for t in range(1, n_samples):
        x[:, t] = ar_coef * x[:, t - 1] + innov[:, t]
    return x.astype(np.float64)


def generate_volume_conduction_mixing(
    n_channels: int = 6,
    n_samples: int = 2048,
    seed: int = 0,
    mix: float = 0.6,
) -> np.ndarray:
    """Volume-conduction-like instantaneous linear mixing of independent sources."""
    rng = _rng(seed)
    sources = rng.standard_normal((n_channels, n_samples))
    # Mixing matrix: identity + symmetric instantaneous bleed
    A = np.eye(n_channels) * (1.0 - mix) + mix / n_channels
    return (A @ sources).astype(np.float64)


def generate_held_out_subjects(
    n_channels: int = 6,
    n_samples: int = 1024,
    seed: int = 0,
) -> Dict[str, np.ndarray]:
    """Two synthetic 'subjects': train has pairwise; held-out is independent."""
    train = generate_pure_pairwise(n_channels, n_samples, seed=seed, corr=0.9)
    held = generate_independent_gaussian(n_channels, n_samples, seed=seed + 1)
    return {"train": train, "held_out": held}


DGP_REGISTRY = {
    "pure_pairwise_dependence": generate_pure_pairwise,
    "pure_triadic_dependence": generate_pure_triadic,
    "amplitude_modulation": generate_amplitude_modulation,
    "common_driver_confounding": generate_common_driver,
    "temporal_smoothing": generate_temporal_smoothing,
    "volume_conduction_like_mixing": generate_volume_conduction_mixing,
    "independent_gaussian_noise": generate_independent_gaussian,
}
