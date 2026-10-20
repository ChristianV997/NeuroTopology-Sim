"""Explicit streaming / chunk contracts for the higher-order runtime.

This module makes chunk boundaries, state carry vs reset, temporal alignment,
and bounded-input failure modes fail-closed and testable. It is **not** a new
online-analysis engine and does not change scientific feature semantics.

Design notes
------------
* Default chunking is tumbling (non-overlapping). Optional overlap uses an
  explicit ``stride < chunk_size``; warm-up length is ``chunk_size - stride``.
* Incomplete spectral tails are **dropped**, never zero-padded (padding would
  change FFT power and break batch/stream parity).
* Timestamps are optional. When provided they must be finite and strictly
  monotonic; the runtime never fabricates, resamples, or interpolates them.
* ``StreamSession.reset`` is required between independent subjects/runs so
  accumulator state cannot leak across run boundaries.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterator, List, Optional, Sequence, Tuple

import numpy as np

from .bounded import IncrementalSummary, RollingCovariance, _as_2d


class StreamContractError(ValueError):
    """Base class for streaming contract violations (never a scientific PASS)."""


class ChunkBoundError(StreamContractError):
    """Raised when a chunk exceeds configured sample/channel bounds."""


class TimelineContractError(StreamContractError):
    """Raised for non-monotonic, non-finite, repeated, or misaligned timestamps."""


class ShapeContractError(StreamContractError):
    """Raised when channel count or 2-D (samples, channels) layout is violated.

    Column identity / permutation is caller-owned and is not fingerprint-checked.
    """


class EmptyInputError(StreamContractError):
    """Raised for empty or unusable signal inputs."""


@dataclass(frozen=True)
class StreamBounds:
    """Hard bounds for one streaming session."""

    max_chunk_samples: int
    max_channels: int
    allow_uneven_final: bool = True

    def __post_init__(self) -> None:
        if self.max_chunk_samples < 1:
            raise StreamContractError("max_chunk_samples must be >= 1")
        if self.max_channels < 1:
            raise StreamContractError("max_channels must be >= 1")


@dataclass(frozen=True)
class ChunkingPolicy:
    """Chunk size and stride. ``stride is None`` means non-overlapping."""

    chunk_size: int
    stride: Optional[int] = None

    def __post_init__(self) -> None:
        if self.chunk_size < 1:
            raise StreamContractError("chunk_size must be >= 1")
        if self.stride is not None and self.stride < 1:
            raise StreamContractError("stride must be >= 1")
        if self.stride is not None and self.stride > self.chunk_size:
            raise StreamContractError("stride must be <= chunk_size")

    @property
    def effective_stride(self) -> int:
        return self.chunk_size if self.stride is None else self.stride

    @property
    def warmup_samples(self) -> int:
        """Samples carried from the previous window when overlapping."""
        return self.chunk_size - self.effective_stride

    @property
    def overlapping(self) -> bool:
        return self.effective_stride < self.chunk_size


def validate_timestamps(timestamps: np.ndarray, *, n_samples: int) -> np.ndarray:
    """Validate optional timestamps: finite, length-matched, strictly increasing."""
    ts = np.asarray(timestamps)
    if ts.ndim != 1:
        raise TimelineContractError("timestamps must be a 1-D array")
    if ts.shape[0] != n_samples:
        raise TimelineContractError(
            f"timestamp length {ts.shape[0]} != n_samples {n_samples}"
        )
    if ts.shape[0] == 0:
        raise TimelineContractError("timestamps are empty")
    if not np.issubdtype(ts.dtype, np.number):
        raise TimelineContractError("timestamps must be numeric")
    if not np.all(np.isfinite(ts)):
        raise TimelineContractError("timestamps contain non-finite values")
    if ts.shape[0] >= 2 and not np.all(np.diff(ts.astype(np.float64)) > 0):
        raise TimelineContractError(
            "timestamps must be strictly monotonic increasing "
            "(repeated or reversed samples are rejected)"
        )
    return ts.astype(np.float64, copy=False)


def validate_signal_shape(signal: np.ndarray, *, max_channels: int) -> np.ndarray:
    """Require ``(samples, channels)`` layout; reject empty / oversized channel axes.

    Unlike the legacy ``_as_2d`` helper used by accumulator utilities, this path
    does **not** silently reshape a 1-D vector into a single-channel matrix.
    That keeps ``iter_contract_windows`` aligned with ``StreamSession.update``.
    """
    data = np.asarray(signal, dtype=np.float64)
    if data.ndim != 2:
        raise ShapeContractError("signal must be 2-D (samples, channels)")
    if data.shape[0] == 0:
        raise EmptyInputError("signal has zero samples")
    if data.shape[1] == 0:
        raise EmptyInputError("signal has zero channels")
    if data.shape[1] > max_channels:
        raise ChunkBoundError(
            f"channel count {data.shape[1]} exceeds max_channels {max_channels}"
        )
    if not np.all(np.isfinite(data)):
        raise StreamContractError("signal contains non-finite values")
    return data


def iter_contract_windows(
    signal: np.ndarray,
    policy: ChunkingPolicy,
    bounds: StreamBounds,
    timestamps: Optional[np.ndarray] = None,
) -> Iterator[Tuple[np.ndarray, Optional[np.ndarray], int, int]]:
    """Yield ``(chunk, chunk_timestamps|None, start, stop)`` under contract rules.

    * Rejects ``chunk_size > max_chunk_samples`` (explicit bound, no silent clamp).
    * Uneven final windows are allowed only when ``allow_uneven_final`` is True;
      otherwise a short final remainder raises ``ChunkBoundError``.
    * Incomplete windows shorter than ``chunk_size`` at end-of-stream are yielded
      only for non-overlapping mode when ``allow_uneven_final`` is True. Overlap
      mode never fabricates padding to fill a partial window.
    * Timestamps, when provided, are sliced with the same indices (no fabrication).
    """
    if policy.chunk_size > bounds.max_chunk_samples:
        raise ChunkBoundError(
            f"chunk_size {policy.chunk_size} exceeds max_chunk_samples "
            f"{bounds.max_chunk_samples}"
        )
    data = validate_signal_shape(signal, max_channels=bounds.max_channels)
    n = data.shape[0]
    ts = None if timestamps is None else validate_timestamps(timestamps, n_samples=n)
    stride = policy.effective_stride
    start = 0
    while start < n:
        stop = start + policy.chunk_size
        if stop > n:
            if policy.overlapping:
                # Overlap mode: do not emit a padded partial window.
                break
            if not bounds.allow_uneven_final:
                raise ChunkBoundError(
                    f"end-of-stream remainder {n - start} samples is shorter than "
                    f"chunk_size {policy.chunk_size} and uneven finals are disabled"
                )
            stop = n
            if stop == start:
                break
        chunk = data[start:stop]
        if chunk.shape[0] > bounds.max_chunk_samples:
            raise ChunkBoundError(
                f"chunk length {chunk.shape[0]} exceeds max_chunk_samples "
                f"{bounds.max_chunk_samples}"
            )
        chunk_ts = None if ts is None else ts[start:stop]
        yield chunk, chunk_ts, start, stop
        start += stride


@dataclass
class StreamSession:
    """Stateful streaming session with explicit carry / reset semantics.

    Accumulators (covariance + summary) carry across chunks within one ``run_id``.
    Calling :meth:`reset` is mandatory before an independent subject/run; updating
    with a different ``run_id`` without reset raises ``StreamContractError``.
    """

    n_channels: int
    bounds: StreamBounds
    run_id: str
    cov: RollingCovariance = None  # type: ignore[assignment]
    summary: IncrementalSummary = None  # type: ignore[assignment]
    chunks_seen: int = 0
    samples_seen: int = 0
    last_timestamp: Optional[float] = None

    def __post_init__(self) -> None:
        if self.n_channels < 1:
            raise StreamContractError("n_channels must be >= 1")
        if self.n_channels > self.bounds.max_channels:
            raise ChunkBoundError(
                f"n_channels {self.n_channels} exceeds max_channels "
                f"{self.bounds.max_channels}"
            )
        if not self.run_id:
            raise StreamContractError("run_id must be non-empty")
        self.cov = RollingCovariance(self.n_channels)
        self.summary = IncrementalSummary(self.n_channels)

    def reset(self, run_id: str) -> None:
        """Clear accumulators for an independent subject/run (no cross-run leakage)."""
        if not run_id:
            raise StreamContractError("run_id must be non-empty")
        self.run_id = run_id
        self.cov = RollingCovariance(self.n_channels)
        self.summary = IncrementalSummary(self.n_channels)
        self.chunks_seen = 0
        self.samples_seen = 0
        self.last_timestamp = None

    def update(
        self,
        chunk: np.ndarray,
        *,
        run_id: Optional[str] = None,
        timestamps: Optional[np.ndarray] = None,
    ) -> None:
        """Ingest one chunk; reject oversize, shape drift, and timeline breaks."""
        if run_id is not None and run_id != self.run_id:
            raise StreamContractError(
                f"run_id mismatch: session={self.run_id!r} chunk={run_id!r}; "
                "call reset() between independent subjects/runs"
            )
        block = np.asarray(chunk, dtype=np.float64)
        if block.ndim != 2:
            raise ShapeContractError("chunk must be 2-D (samples, channels)")
        if block.shape[0] == 0:
            raise EmptyInputError("chunk has zero samples")
        if block.shape[0] > self.bounds.max_chunk_samples:
            raise ChunkBoundError(
                f"chunk length {block.shape[0]} exceeds max_chunk_samples "
                f"{self.bounds.max_chunk_samples}"
            )
        if block.shape[1] != self.n_channels:
            raise ShapeContractError(
                f"channel count changed: expected {self.n_channels}, got {block.shape[1]}"
            )
        if not np.all(np.isfinite(block)):
            raise StreamContractError("chunk contains non-finite values")

        if timestamps is not None:
            ts = validate_timestamps(timestamps, n_samples=block.shape[0])
            if self.last_timestamp is not None and not (ts[0] > self.last_timestamp):
                raise TimelineContractError(
                    "chunk timestamps are not continuous with prior stream state "
                    f"(last={self.last_timestamp}, next_first={float(ts[0])})"
                )
            self.last_timestamp = float(ts[-1])

        self.cov.update(block)
        self.summary.update(block)
        self.chunks_seen += 1
        self.samples_seen += int(block.shape[0])


def batch_stream_covariance_parity(
    signal: np.ndarray,
    *,
    chunk_sizes: Sequence[int],
    atol: float = 1e-8,
    rtol: float = 0.0,
) -> List[Tuple[int, bool, float]]:
    """Compare streaming covariance vs ``np.cov`` for each chunk size.

    Returns ``(chunk_size, equivalent, max_abs_diff)``. Declared tolerances are
    explicit; this is engineering parity, not a scientific PASS.
    """
    data = _as_2d(signal)
    if data.shape[0] < 2:
        raise EmptyInputError("covariance parity requires at least 2 samples")
    reference = np.cov(data, rowvar=False, ddof=1)
    out: List[Tuple[int, bool, float]] = []
    for chunk_size in chunk_sizes:
        if chunk_size < 1:
            raise StreamContractError("chunk_size must be >= 1")
        acc = RollingCovariance(data.shape[1])
        for start in range(0, data.shape[0], chunk_size):
            acc.update(data[start : start + chunk_size])
        got = acc.matrix(ddof=1)
        diff = float(np.nanmax(np.abs(got - reference)))
        ok = bool(np.allclose(got, reference, rtol=rtol, atol=atol, equal_nan=True))
        out.append((int(chunk_size), ok, diff))
    return out


def deterministic_accumulator_bytes(n_channels: int, dtype_itemsize: int = 8) -> int:
    """Deterministic working-set size of cov+summary accumulators (not process RSS).

    Meaningful bound check: O(C^2) co-moment matrix + O(C) summary vectors.
    Does not claim a measured speed or RSS improvement.
    """
    if n_channels < 1 or dtype_itemsize < 1:
        raise StreamContractError("n_channels and dtype_itemsize must be >= 1")
    cov = n_channels * n_channels * dtype_itemsize  # M2
    mean = n_channels * dtype_itemsize
    summary = 4 * n_channels * dtype_itemsize  # mean, m2, min, max
    return int(cov + mean + summary)
