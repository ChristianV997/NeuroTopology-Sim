"""Bounded, allocation-conscious streaming utilities for signal/topology work.

These helpers process long multichannel signals in fixed-size chunks so that
peak memory stays bounded by ``chunk_size`` (plus any caller-owned reduction
state) instead of the full ``n_samples``. They are deliberately dependency-light
(NumPy + stdlib ``tracemalloc``): there is no GPU/Numba/JAX requirement and no
accelerated path here, so nothing to fall back *from*.

Design goals (all opt-in, defaults favour bounded memory):

* fixed-size chunk iteration over an in-memory array (zero-copy views);
* reusable work buffers for an optional per-chunk transform;
* optional callback-based per-chunk summaries (bounded output);
* optional full-history retention (suppressed by default);
* deterministic aggregation (Chan's stable streaming mean/variance combine,
  applied strictly in chunk order) plus a stable order-dependent checksum;
* explicit finite-value checks;
* explicit peak-memory telemetry via :class:`MemoryTelemetry`.

Determinism note: for a *fixed* ``chunk_size`` the aggregates and checksum are
reproducible bit-for-bit across runs. Across *different* ``chunk_size`` values,
floating-point summation grouping changes, so equality holds only within a
declared tolerance (see ``docs/performance_benchmarking.md``). No data is
dropped and no precision is silently reduced: every sample contributes and all
accumulation is float64.
"""
from __future__ import annotations

import tracemalloc
from dataclasses import dataclass
from typing import Callable, Iterator, Optional

import numpy as np

__all__ = [
    "MemoryTelemetry",
    "StreamAggregate",
    "StreamResult",
    "iter_chunks",
    "iter_windows",
    "bounded_stream",
]


class MemoryTelemetry:
    """Context manager reporting transient peak allocation via ``tracemalloc``.

    Records the peak number of bytes traced by Python allocators *inside* the
    ``with`` block, relative to the allocation level at entry. Nesting is
    supported: if tracing was already active the outer tracer is left running
    and only a peak snapshot is taken.

    Example
    -------
    >>> with MemoryTelemetry() as mem:      # doctest: +SKIP
    ...     do_work()
    >>> mem.peak_bytes                       # doctest: +SKIP
    """

    def __init__(self) -> None:
        self.peak_bytes: Optional[int] = None
        self._started_here = False

    def __enter__(self) -> "MemoryTelemetry":
        self._started_here = not tracemalloc.is_tracing()
        if self._started_here:
            tracemalloc.start()
        # Reset the peak so the measurement reflects only this block.
        tracemalloc.reset_peak()
        return self

    def __exit__(self, *exc: object) -> None:
        _, peak = tracemalloc.get_traced_memory()
        self.peak_bytes = int(peak)
        if self._started_here:
            tracemalloc.stop()


def _as_2d(signal: np.ndarray) -> np.ndarray:
    """Return a read view of ``signal`` shaped ``(n_samples, n_channels)``."""
    arr = np.asarray(signal)
    if arr.ndim == 1:
        return arr.reshape(-1, 1)
    if arr.ndim == 2:
        return arr
    raise ValueError("signal must be 1-D (samples,) or 2-D (samples, channels)")


def iter_chunks(signal: np.ndarray, chunk_size: int) -> Iterator[np.ndarray]:
    """Yield consecutive non-overlapping chunk *views* of ``signal``.

    Views (not copies) keep iteration allocation-free. The final chunk may be
    shorter than ``chunk_size``. ``signal`` may be 1-D or 2-D; the first axis is
    the sample axis.
    """
    if chunk_size < 1:
        raise ValueError("chunk_size must be >= 1")
    n = signal.shape[0]
    for start in range(0, n, chunk_size):
        yield signal[start:start + chunk_size]


def iter_windows(signal: np.ndarray, window: int, step: Optional[int] = None) -> Iterator[np.ndarray]:
    """Yield fixed-length window *views* of ``signal`` (topology-window helper).

    ``step`` defaults to ``window`` (non-overlapping/tumbling windows). Only
    complete windows are yielded; a trailing partial window is not emitted so
    every yielded window has identical shape (deterministic downstream cost).
    """
    if window < 1:
        raise ValueError("window must be >= 1")
    step = window if step is None else step
    if step < 1:
        raise ValueError("step must be >= 1")
    n = signal.shape[0]
    for start in range(0, n - window + 1, step):
        yield signal[start:start + window]


@dataclass
class StreamAggregate:
    """Deterministic streaming mean/variance over chunks (Chan's combine).

    Accumulates fixed-size ``(n_channels,)`` state regardless of the number of
    chunks, so memory is bounded. Combining chunk statistics uses the numerically
    stable parallel algorithm of Chan, Golub & LeVeque (1979); for a fixed chunk
    order the result is reproducible.
    """
    count: int
    mean: np.ndarray
    _m2: np.ndarray
    minimum: np.ndarray
    maximum: np.ndarray
    checksum: float

    @classmethod
    def empty(cls, n_channels: int) -> "StreamAggregate":
        return cls(
            count=0,
            mean=np.zeros(n_channels, dtype=np.float64),
            _m2=np.zeros(n_channels, dtype=np.float64),
            minimum=np.full(n_channels, np.inf, dtype=np.float64),
            maximum=np.full(n_channels, -np.inf, dtype=np.float64),
            checksum=0.0,
        )

    def update(self, chunk: np.ndarray) -> None:
        """Fold one ``(m, n_channels)`` chunk into the running statistics."""
        block = np.asarray(chunk, dtype=np.float64)
        if block.ndim != 2 or block.shape[1] != self.mean.shape[0]:
            raise ValueError("chunk must be 2-D with matching channel count")
        m = block.shape[0]
        if m == 0:
            return
        b_count = m
        b_mean = block.mean(axis=0)
        b_m2 = ((block - b_mean) ** 2).sum(axis=0)
        # Chan parallel combine of (count, mean, M2).
        if self.count == 0:
            self.mean = b_mean.copy()
            self._m2 = b_m2.copy()
            self.count = b_count
        else:
            total = self.count + b_count
            delta = b_mean - self.mean
            self.mean = self.mean + delta * (b_count / total)
            self._m2 = self._m2 + b_m2 + (delta ** 2) * (self.count * b_count / total)
            self.count = total
        np.minimum(self.minimum, block.min(axis=0), out=self.minimum)
        np.maximum(self.maximum, block.max(axis=0), out=self.maximum)
        # Order-dependent but run-reproducible checksum (float64, chunk order).
        self.checksum += float(block.sum())

    @property
    def variance(self) -> np.ndarray:
        """Population variance per channel (0 when fewer than 1 sample)."""
        if self.count < 1:
            return np.zeros_like(self.mean)
        return self._m2 / self.count

    @property
    def std(self) -> np.ndarray:
        return np.sqrt(self.variance)


@dataclass
class StreamResult:
    """Outcome of :func:`bounded_stream`."""
    n_samples: int
    n_channels: int
    n_chunks: int
    chunk_size: int
    count: int
    mean: np.ndarray
    variance: np.ndarray
    minimum: np.ndarray
    maximum: np.ndarray
    checksum: float
    peak_bytes: Optional[int]
    summaries: Optional[list]
    history: Optional[list]


def bounded_stream(
    signal: np.ndarray,
    chunk_size: int,
    *,
    transform: Optional[Callable[[np.ndarray, np.ndarray], np.ndarray]] = None,
    summarize: Optional[Callable[[int, np.ndarray], object]] = None,
    store_history: bool = False,
    check_finite: bool = True,
    track_memory: bool = False,
) -> StreamResult:
    """Process ``signal`` in fixed-size chunks with bounded memory.

    Parameters
    ----------
    signal:
        1-D ``(n_samples,)`` or 2-D ``(n_samples, n_channels)`` array. The first
        axis is streamed; nothing is copied unless a ``transform`` or
        ``store_history`` requires it.
    chunk_size:
        Number of samples per chunk (peak working set scales with this, not with
        ``n_samples``).
    transform:
        Optional ``transform(chunk_view, out) -> array`` applied per chunk. It
        must write its result into the provided reusable ``out`` buffer (shape
        ``(len(chunk), n_channels)``) and return an array of the same channel
        count. The *returned* array is what gets aggregated, so a transform may
        return ``out`` (in place) to stay allocation-free. When omitted, raw
        chunks are aggregated.
    summarize:
        Optional ``summarize(chunk_index, values) -> summary`` callback. Returned
        summaries are collected in a bounded list (one small object per chunk),
        enabling per-chunk telemetry without retaining full data.
    store_history:
        When ``True`` retain a copy of every chunk's aggregated values. Default
        ``False`` (history suppressed) to keep memory bounded.
    check_finite:
        When ``True`` (default) raise ``ValueError`` on any NaN/Inf in the
        aggregated values.
    track_memory:
        When ``True`` wrap the loop in :class:`MemoryTelemetry` and report the
        transient peak in ``StreamResult.peak_bytes``.

    Returns
    -------
    StreamResult
        Deterministic per-channel aggregates, checksum, and optional telemetry.
    """
    if chunk_size < 1:
        raise ValueError("chunk_size must be >= 1")
    data = _as_2d(signal)
    n_samples, n_channels = data.shape
    aggregate = StreamAggregate.empty(n_channels)
    summaries: Optional[list] = [] if summarize is not None else None
    history: Optional[list] = [] if store_history else None

    # Single reusable work buffer for the transform output (bounded memory).
    work: Optional[np.ndarray] = None
    if transform is not None:
        work = np.empty((chunk_size, n_channels), dtype=np.float64)

    n_chunks = 0

    def _run() -> None:
        nonlocal n_chunks
        for index, chunk in enumerate(iter_chunks(data, chunk_size)):
            m = chunk.shape[0]
            if transform is not None:
                out = work[:m]  # reuse the same backing buffer every chunk
                values = np.asarray(transform(chunk, out), dtype=np.float64)
                if values.ndim != 2 or values.shape[1] != n_channels:
                    raise ValueError("transform must return a (m, n_channels) array")
            else:
                values = chunk
            if check_finite and not np.all(np.isfinite(values)):
                raise ValueError(f"non-finite value encountered in chunk {index}")
            aggregate.update(values)
            if summaries is not None:
                summaries.append(summarize(index, values))
            if history is not None:
                history.append(np.array(values, dtype=np.float64, copy=True))
            n_chunks += 1

    if track_memory:
        with MemoryTelemetry() as mem:
            _run()
        peak_bytes = mem.peak_bytes
    else:
        _run()
        peak_bytes = None

    return StreamResult(
        n_samples=n_samples,
        n_channels=n_channels,
        n_chunks=n_chunks,
        chunk_size=chunk_size,
        count=aggregate.count,
        mean=aggregate.mean,
        variance=aggregate.variance,
        minimum=aggregate.minimum,
        maximum=aggregate.maximum,
        checksum=aggregate.checksum,
        peak_bytes=peak_bytes,
        summaries=summaries,
        history=history,
    )
