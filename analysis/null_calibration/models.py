"""Seeded null generators.

Generators never tune themselves toward a model family.
"""
from __future__ import annotations

import math
import random
from typing import Any, Callable

from .schema import NULL_MODELS


def lag1_corr(series: list[float]) -> float | None:
    if len(series) < 3:
        return None
    xs = series[:-1]
    ys = series[1:]
    mx = sum(xs) / len(xs)
    my = sum(ys) / len(ys)
    num = sum((a - mx) * (b - my) for a, b in zip(xs, ys))
    dx = math.sqrt(sum((a - mx) ** 2 for a in xs))
    dy = math.sqrt(sum((b - my) ** 2 for b in ys))
    if dx == 0.0 or dy == 0.0:
        return None
    return num / (dx * dy)


def variance(series: list[float]) -> float | None:
    if len(series) < 2:
        return None
    mean = sum(series) / len(series)
    return sum((x - mean) ** 2 for x in series) / (len(series) - 1)


def _require_finite(series: list[float], name: str) -> None:
    if not series:
        raise ValueError(f"{name} is empty")
    if any(not math.isfinite(x) for x in series):
        raise ValueError(f"{name} contains a non-finite value")


def generate_flat(series: list[float], rng: random.Random) -> list[float]:
    del rng
    _require_finite(series, "series")
    return [0.0] * len(series)


def generate_gaussian(series: list[float], rng: random.Random, *, scale: float | None = None) -> list[float]:
    _require_finite(series, "series")
    sigma = 1.0 if scale is None else scale
    if not math.isfinite(sigma) or sigma < 0:
        raise ValueError("gaussian scale must be finite and non-negative")
    return [rng.gauss(0.0, sigma) for _ in series]


def generate_matched_variance(series: list[float], rng: random.Random) -> list[float]:
    var = variance(series)
    if var is None:
        raise ValueError("matched_variance requires at least two finite samples")
    return generate_gaussian(series, rng, scale=math.sqrt(max(var, 0.0)))


def generate_circular_shift(series: list[float], rng: random.Random) -> list[float]:
    _require_finite(series, "series")
    n = len(series)
    if n < 2:
        raise ValueError("circular_shift requires length >= 2")
    shift = rng.randrange(1, n)
    return series[-shift:] + series[:-shift]


def generate_block_shuffle(series: list[float], rng: random.Random, *, block_size: int = 4) -> list[float]:
    _require_finite(series, "series")
    n = len(series)
    if n < 2:
        raise ValueError("block_shuffle requires length >= 2")
    size = max(1, min(int(block_size), n))
    blocks = [series[i : i + size] for i in range(0, n, size)]
    rng.shuffle(blocks)
    out: list[float] = []
    for block in blocks:
        out.extend(block)
    return out[:n]


def generate_phase_shuffle(series: list[float], rng: random.Random) -> list[float]:
    _require_finite(series, "series")
    n = len(series)
    if n < 4:
        raise ValueError("phase_shuffle requires length >= 4")
    try:
        import numpy as np
    except ImportError as exc:
        raise ValueError("phase_shuffle requires numpy") from exc
    arr = np.asarray(series, dtype=float)
    spec = np.fft.rfft(arr)
    mag = np.abs(spec)
    phases = np.array([rng.uniform(0.0, 2.0 * math.pi) for _ in range(mag.size)])
    phases[0] = 0.0
    if n % 2 == 0:
        phases[-1] = 0.0
    shuffled = mag * np.exp(1j * phases)
    out = np.fft.irfft(shuffled, n=n)
    return [float(x) for x in out]


def generate_matched_autocorrelation(series: list[float], rng: random.Random) -> list[float]:
    _require_finite(series, "series")
    rho = lag1_corr(series)
    var = variance(series) or 1.0
    if rho is None or abs(rho) >= 0.999:
        return generate_matched_variance(series, rng)
    eps_sd = math.sqrt(max(var * (1.0 - rho * rho), 0.0))
    out = [rng.gauss(0.0, math.sqrt(var))]
    for _ in range(1, len(series)):
        out.append(rho * out[-1] + rng.gauss(0.0, eps_sd))
    return out


def generate_label_permutation(group_a: list[float], group_b: list[float], rng: random.Random) -> tuple[list[float], list[float]]:
    _require_finite(group_a, "group_a")
    _require_finite(group_b, "group_b")
    pooled = list(group_a) + list(group_b)
    rng.shuffle(pooled)
    n_a = len(group_a)
    return pooled[:n_a], pooled[n_a:]


GENERATORS: dict[str, Callable[..., Any]] = {
    "flat": generate_flat,
    "gaussian": generate_gaussian,
    "phase_shuffle": generate_phase_shuffle,
    "circular_shift": generate_circular_shift,
    "block_shuffle": generate_block_shuffle,
    "matched_variance": generate_matched_variance,
    "matched_autocorrelation": generate_matched_autocorrelation,
}

PRESERVES_VARIANCE = {
    "flat": False,
    "gaussian": False,
    "phase_shuffle": True,
    "circular_shift": True,
    "block_shuffle": True,
    "matched_variance": True,
    "matched_autocorrelation": True,
    "label_permutation": True,
}

PRESERVES_AUTOCORR = {
    "flat": False,
    "gaussian": False,
    "phase_shuffle": True,
    "circular_shift": True,
    "block_shuffle": False,
    "matched_variance": False,
    "matched_autocorrelation": True,
    "label_permutation": False,
}

assert set(GENERATORS) | {"label_permutation"} == set(NULL_MODELS)
