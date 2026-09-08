"""Benchmark harness: full vs bounded/adaptive higher-order runtime + equivalence.

Computes the same synthetic higher-order feature set two ways -- full
materialization and bounded streaming -- and verifies numerical equivalence
(checksum, means, variances, extrema, feature counts) within tolerance. Also
supports adaptive chunk sizing (via the memory planner), deterministic replay,
and a simple checkpoint/resume of the streaming state.

Semantics-preserving: the bounded path reproduces the full path's numbers within
floating tolerance; nothing here changes scientific meaning, and all fixtures are
synthetic performance scaffolding (never scientific/biological evidence).
"""
from __future__ import annotations

import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import numpy as np

from .bounded import (
    IncrementalSummary,
    RollingCovariance,
    evaluate_triads,
    iter_signal_windows,
    one_at_a_time_surrogates,
    spectral_power_sum,
)
from .planner import MemoryPlan, PlanRequest, plan_chunk
from .protocols import (
    SpectralSegmentFn,
    SurrogateFn,
    TriadStatFn,
    fixture_spectral_power,
    fixture_surrogate_stat,
    fixture_triad_stat,
)
from .telemetry import MemoryTelemetry, json_safe


@dataclass(frozen=True)
class WorkloadConfig:
    n_samples: int = 20000
    n_channels: int = 12
    seed: int = 0
    segment_len: int = 512
    candidate_limit: Optional[int] = 64
    surrogate_limit: int = 16
    surrogate_seed: int = 12345


def make_signal(cfg: WorkloadConfig) -> np.ndarray:
    """Deterministic synthetic multichannel signal for benchmarking."""
    if cfg.n_samples < 1 or cfg.n_channels < 1:
        raise ValueError("n_samples and n_channels must be >= 1")
    rng = np.random.default_rng(cfg.seed)
    t = np.arange(cfg.n_samples, dtype=np.float64)[:, None]
    freqs = (1.0 + np.arange(cfg.n_channels, dtype=np.float64))[None, :]
    base = np.sin(2.0 * np.pi * freqs * t / max(cfg.n_samples, 1))
    return (base + 0.25 * rng.standard_normal((cfg.n_samples, cfg.n_channels))).astype(np.float64)


def _metrics(cov: np.ndarray, summary_mean: np.ndarray, summary_var: np.ndarray,
             summary_min: np.ndarray, summary_max: np.ndarray, summary_checksum: float,
             triad_checksum: float, triad_count: int, spectral_sum: float,
             spectral_count: int, surrogate_mean: float, surrogate_checksum: float,
             count: int) -> Dict[str, Any]:
    return {
        "covariance_checksum": float(np.nansum(cov)),
        "summary_mean_sum": float(np.sum(summary_mean)),
        "summary_var_sum": float(np.sum(summary_var)),
        "summary_min_sum": float(np.sum(summary_min)),
        "summary_max_sum": float(np.sum(summary_max)),
        "summary_checksum": float(summary_checksum),
        "triad_checksum": float(triad_checksum),
        "triad_count": int(triad_count),
        "spectral_sum": float(spectral_sum),
        "spectral_count": int(spectral_count),
        "surrogate_mean": float(surrogate_mean),
        "surrogate_checksum": float(surrogate_checksum),
        "count": int(count),
    }


def compute_full(signal: np.ndarray, cfg: WorkloadConfig, *,
                 triad_fn: TriadStatFn = fixture_triad_stat,
                 segment_fn: SpectralSegmentFn = fixture_spectral_power,
                 surrogate_fn: SurrogateFn = fixture_surrogate_stat) -> Dict[str, Any]:
    """Full-materialization reference computation."""
    X = np.asarray(signal, dtype=np.float64)
    cov = np.cov(X, rowvar=False, ddof=1)               # materializes a centered copy
    cov = np.atleast_2d(cov)
    summary_mean = X.mean(axis=0)
    summary_var = X.var(axis=0, ddof=0)
    summary_min = X.min(axis=0)
    summary_max = X.max(axis=0)
    summary_checksum = float(X.sum())
    triad_checksum, triad_count = evaluate_triads(cov, triad_fn, cfg.candidate_limit)
    spectral_sum, spectral_count = spectral_power_sum(X, cfg.segment_len, segment_fn)
    surrogate_mean, surrogate_stats = one_at_a_time_surrogates(
        X, surrogate_fn, surrogate_limit=cfg.surrogate_limit, seed=cfg.surrogate_seed)
    surrogate_checksum = float(np.sum(surrogate_stats))
    return _metrics(cov, summary_mean, summary_var, summary_min, summary_max,
                    summary_checksum, triad_checksum, triad_count, spectral_sum,
                    spectral_count, surrogate_mean, surrogate_checksum, X.shape[0])


def _stream_cov_and_summary(signal: np.ndarray, chunk_size: int, n_channels: int):
    cov_acc = RollingCovariance(n_channels)
    summary = IncrementalSummary(n_channels)
    for window in iter_signal_windows(signal, chunk_size):
        cov_acc.update(window)
        summary.update(window)
    return cov_acc, summary


def compute_bounded(signal: np.ndarray, cfg: WorkloadConfig, *, chunk_size: int,
                    triad_fn: TriadStatFn = fixture_triad_stat,
                    segment_fn: SpectralSegmentFn = fixture_spectral_power,
                    surrogate_fn: SurrogateFn = fixture_surrogate_stat) -> Dict[str, Any]:
    """Bounded streaming computation with the same outputs as :func:`compute_full`."""
    X = np.asarray(signal, dtype=np.float64)
    cov_acc, summary = _stream_cov_and_summary(X, chunk_size, cfg.n_channels)
    cov = np.atleast_2d(cov_acc.matrix(ddof=1))
    triad_checksum, triad_count = evaluate_triads(cov, triad_fn, cfg.candidate_limit)
    spectral_sum, spectral_count = spectral_power_sum(X, cfg.segment_len, segment_fn)
    surrogate_mean, surrogate_stats = one_at_a_time_surrogates(
        X, surrogate_fn, surrogate_limit=cfg.surrogate_limit, seed=cfg.surrogate_seed)
    surrogate_checksum = float(np.sum(surrogate_stats))
    return _metrics(cov, summary.mean, summary.variance, summary.minimum, summary.maximum,
                    summary.checksum, triad_checksum, triad_count, spectral_sum,
                    spectral_count, surrogate_mean, surrogate_checksum, summary.count)


def compute_bounded_checkpointed(signal: np.ndarray, cfg: WorkloadConfig, *,
                                 chunk_size: int, checkpoint_path: str,
                                 **fns) -> Dict[str, Any]:
    """Bounded computation that persists/reloads streaming state midway (resume).

    Processes the covariance/summary stream in two halves, saving the accumulator
    state to ``checkpoint_path`` (atomic .npz) and reloading it before finishing.
    The result matches :func:`compute_bounded` for the same ``chunk_size``.
    """
    X = np.asarray(signal, dtype=np.float64)
    windows = list(iter_signal_windows(X, chunk_size))
    half = len(windows) // 2

    cov_acc = RollingCovariance(cfg.n_channels)
    summary = IncrementalSummary(cfg.n_channels)
    for w in windows[:half]:
        cov_acc.update(w)
        summary.update(w)

    tmp = Path(checkpoint_path)
    tmp.parent.mkdir(parents=True, exist_ok=True)
    fd_tmp = tmp.with_suffix(tmp.suffix + ".tmp")
    # Write via a file handle so np.savez does not append an extra ".npz".
    with open(fd_tmp, "wb") as handle:
        np.savez(handle, cov_count=cov_acc.count, cov_mean=cov_acc._mean, cov_m2=cov_acc._m2,
                 s_count=summary.count, s_mean=summary._mean, s_m2=summary._m2,
                 s_min=summary.minimum, s_max=summary.maximum, s_checksum=summary.checksum)
    import os
    os.replace(fd_tmp, tmp)

    # Resume from a fresh state loaded from disk.
    with np.load(tmp, allow_pickle=False) as data:
        cov2 = RollingCovariance(cfg.n_channels)
        cov2.count = int(data["cov_count"]); cov2._mean = data["cov_mean"].copy(); cov2._m2 = data["cov_m2"].copy()
        sum2 = IncrementalSummary(cfg.n_channels)
        sum2.count = int(data["s_count"]); sum2._mean = data["s_mean"].copy(); sum2._m2 = data["s_m2"].copy()
        sum2.minimum = data["s_min"].copy(); sum2.maximum = data["s_max"].copy()
        sum2.checksum = float(data["s_checksum"])
    for w in windows[half:]:
        cov2.update(w)
        sum2.update(w)

    cov = np.atleast_2d(cov2.matrix(ddof=1))
    triad_fn = fns.get("triad_fn", fixture_triad_stat)
    segment_fn = fns.get("segment_fn", fixture_spectral_power)
    surrogate_fn = fns.get("surrogate_fn", fixture_surrogate_stat)
    triad_checksum, triad_count = evaluate_triads(cov, triad_fn, cfg.candidate_limit)
    spectral_sum, spectral_count = spectral_power_sum(X, cfg.segment_len, segment_fn)
    surrogate_mean, surrogate_stats = one_at_a_time_surrogates(
        X, surrogate_fn, surrogate_limit=cfg.surrogate_limit, seed=cfg.surrogate_seed)
    return _metrics(cov, sum2.mean, sum2.variance, sum2.minimum, sum2.maximum,
                    sum2.checksum, triad_checksum, triad_count, spectral_sum,
                    spectral_count, surrogate_mean, float(np.sum(surrogate_stats)), sum2.count)


# --------------------------------------------------------------------------- #
# Equivalence
# --------------------------------------------------------------------------- #
_FLOAT_METRICS = (
    "covariance_checksum", "summary_mean_sum", "summary_var_sum", "summary_min_sum",
    "summary_max_sum", "summary_checksum", "triad_checksum", "spectral_sum",
    "surrogate_mean", "surrogate_checksum",
)
_INT_METRICS = ("triad_count", "spectral_count", "count")


@dataclass
class EquivalenceReport:
    equivalent: bool
    tolerance: float
    float_rel_errors: Dict[str, Optional[float]]
    int_mismatches: Dict[str, List[int]]

    def to_dict(self) -> Dict[str, Any]:
        return json_safe(asdict(self))


def verify_equivalence(reference: Dict[str, Any], candidate: Dict[str, Any],
                       tolerance: float = 1e-9) -> EquivalenceReport:
    """Compare two metric dicts: float metrics within tolerance, ints exact."""
    float_errs: Dict[str, Optional[float]] = {}
    ok = True
    for key in _FLOAT_METRICS:
        a = float(reference[key]); b = float(candidate[key])
        denom = max(abs(a), abs(b), 1e-300)
        rel = abs(a - b) / denom
        float_errs[key] = rel
        if rel > tolerance:
            ok = False
    int_mismatch: Dict[str, List[int]] = {}
    for key in _INT_METRICS:
        a = int(reference[key]); b = int(candidate[key])
        if a != b:
            ok = False
            int_mismatch[key] = [a, b]
    return EquivalenceReport(equivalent=ok, tolerance=tolerance,
                             float_rel_errors=float_errs, int_mismatches=int_mismatch)


# --------------------------------------------------------------------------- #
# Benchmark orchestration
# --------------------------------------------------------------------------- #
def _measure(fn: Callable[[], Dict[str, Any]]) -> Dict[str, Any]:
    fn()  # warm-up
    import time

    t0 = time.perf_counter()
    with MemoryTelemetry() as mem:
        metrics = fn()
    elapsed = time.perf_counter() - t0
    return {"metrics": metrics, "tracemalloc_peak_bytes": mem.peak_bytes,
            "wall_s": elapsed}


def run_benchmark(cfg: WorkloadConfig, *, chunk_size: int = 2048,
                  budget_bytes: int = 4 * 1024 * 1024, min_chunk: int = 256,
                  max_chunk: int = 65536, tolerance: float = 1e-9,
                  enable_checkpoint: bool = True) -> Dict[str, Any]:
    """Run full/bounded/adaptive/replay(/checkpoint) and verify equivalence."""
    signal = make_signal(cfg)

    full = _measure(lambda: compute_full(signal, cfg))
    bounded = _measure(lambda: compute_bounded(signal, cfg, chunk_size=chunk_size))

    plan = plan_chunk(PlanRequest(
        n_samples=cfg.n_samples, n_channels=cfg.n_channels, dtype_itemsize=8,
        target_budget_bytes=budget_bytes, min_chunk=min_chunk, max_chunk=max_chunk,
        op_multiplier=3, surrogates=cfg.surrogate_limit > 0))
    adaptive = _measure(lambda: compute_bounded(signal, cfg, chunk_size=plan.chunk_size))

    replay_a = compute_bounded(signal, cfg, chunk_size=chunk_size)
    replay_b = compute_bounded(signal, cfg, chunk_size=chunk_size)
    replay_identical = replay_a == replay_b

    modes: Dict[str, Any] = {
        "full_materialization": full,
        "bounded_streaming": bounded,
        "adaptive_chunks": {**adaptive, "plan": plan.to_dict()},
    }
    equivalence = {
        "bounded_vs_full": verify_equivalence(full["metrics"], bounded["metrics"], tolerance).to_dict(),
        "adaptive_vs_full": verify_equivalence(full["metrics"], adaptive["metrics"], tolerance).to_dict(),
    }

    checkpoint_available = False
    if enable_checkpoint:
        with tempfile.TemporaryDirectory(prefix="hio_ckpt_") as d:
            ckpt = compute_bounded_checkpointed(
                signal, cfg, chunk_size=chunk_size, checkpoint_path=str(Path(d) / "state.npz"))
        modes["checkpoint_resume"] = {"metrics": ckpt}
        equivalence["checkpoint_vs_full"] = verify_equivalence(
            full["metrics"], ckpt, tolerance).to_dict()
        checkpoint_available = True

    all_equiv = all(e["equivalent"] for e in equivalence.values()) and replay_identical

    peak_full = full["tracemalloc_peak_bytes"]
    peak_bounded = bounded["tracemalloc_peak_bytes"]
    peak_ratio = (peak_bounded / peak_full) if (peak_full and peak_full > 0) else None

    return json_safe({
        "schema": "higher_order_runtime/v1",
        "evidence_class": "performance_only",
        "synthetic": True,
        "config": asdict(cfg),
        "modes": modes,
        "equivalence": equivalence,
        "deterministic_replay_identical": bool(replay_identical),
        "checkpoint_available": checkpoint_available,
        "all_equivalent": bool(all_equiv),
        "tracemalloc_peak_ratio_bounded_over_full": peak_ratio,
        "notes": [
            "Bounded/adaptive paths reproduce the full path within tolerance; "
            "runtime optimization does not alter scientific semantics.",
            "tracemalloc peak is Python-allocation only, not process RSS.",
            "Synthetic fixtures: performance evidence only, never scientific evidence.",
        ],
    })
