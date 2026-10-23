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
from numbers import Integral, Real
from typing import Iterator, List, Optional, Sequence, Tuple

import numpy as np

from .bounded import IncrementalSummary, RollingCovariance


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


def _positive_integer(value: object, *, name: str) -> int:
    """Validate an integer-valued contract field, excluding bool and floats."""
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Integral):
        raise StreamContractError(f"{name} must be an integer")
    normalized = int(value)
    if normalized < 1:
        raise StreamContractError(f"{name} must be >= 1")
    return normalized


def _nonempty_string(value: object, *, name: str) -> str:
    """Validate an opaque identifier without echoing the supplied value."""
    if not isinstance(value, str) or not value:
        raise StreamContractError(f"{name} must be a non-empty string")
    return value


def _finite_nonnegative_tolerance(value: object, *, name: str) -> float:
    """Validate one scalar comparison tolerance without accepting bools."""
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise StreamContractError(
            f"{name} tolerance must be a finite non-negative real number"
        )
    try:
        normalized = float(value)
    except (OverflowError, TypeError, ValueError) as exc:
        raise StreamContractError(
            f"{name} tolerance must be a finite non-negative real number"
        ) from exc
    if not np.isfinite(normalized) or normalized < 0:
        raise StreamContractError(
            f"{name} tolerance must be a finite non-negative real number"
        )
    return normalized


@dataclass(frozen=True)
class StreamBounds:
    """Hard bounds for one streaming session."""

    max_chunk_samples: int
    max_channels: int
    allow_uneven_final: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "max_chunk_samples",
            _positive_integer(self.max_chunk_samples, name="max_chunk_samples"),
        )
        object.__setattr__(
            self,
            "max_channels",
            _positive_integer(self.max_channels, name="max_channels"),
        )
        if not isinstance(self.allow_uneven_final, (bool, np.bool_)):
            raise StreamContractError("allow_uneven_final must be a boolean")
        object.__setattr__(self, "allow_uneven_final", bool(self.allow_uneven_final))


@dataclass(frozen=True)
class ChunkingPolicy:
    """Chunk size and stride. ``stride is None`` means non-overlapping."""

    chunk_size: int
    stride: Optional[int] = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "chunk_size", _positive_integer(self.chunk_size, name="chunk_size")
        )
        if self.stride is not None:
            object.__setattr__(
                self, "stride", _positive_integer(self.stride, name="stride")
            )
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
    try:
        ts = np.asarray(timestamps)
    except (TypeError, ValueError, OverflowError) as exc:
        raise TimelineContractError(
            "timestamps must be a rectangular numeric array"
        ) from exc
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
    if np.iscomplexobj(ts):
        raise TimelineContractError(
            "timestamps must be real-valued; complex input is rejected, not cast"
        )
    try:
        finite_input = bool(np.all(np.isfinite(ts)))
    except (TypeError, ValueError, OverflowError) as exc:
        raise TimelineContractError("timestamps must be numeric") from exc
    if not finite_input:
        raise TimelineContractError("timestamps contain non-finite values")
    try:
        with np.errstate(over="ignore", invalid="ignore"):
            normalized = ts.astype(np.float64, copy=False)
    except (TypeError, ValueError, OverflowError) as exc:
        raise TimelineContractError(
            "timestamps must be representable as finite float64 values"
        ) from exc
    if not bool(np.all(np.isfinite(normalized))):
        raise TimelineContractError(
            "timestamps must be representable as finite float64 values"
        )
    if normalized.shape[0] >= 2 and not bool(
        np.all(normalized[1:] > normalized[:-1])
    ):
        raise TimelineContractError(
            "timestamps must be strictly monotonic increasing "
            "(repeated or reversed samples are rejected)"
        )
    return normalized


def _as_real_float64(values: object, *, what: str) -> np.ndarray:
    """Return ``values`` as float64. Complex input is refused, never cast."""
    try:
        arr = np.asarray(values)
    except (TypeError, ValueError, OverflowError) as exc:
        raise StreamContractError(f"{what} must be a rectangular numeric array") from exc
    if np.iscomplexobj(arr):
        raise StreamContractError(
            f"{what} must be real-valued; complex input is rejected, not cast"
        )
    try:
        return arr.astype(np.float64, copy=False)
    except (TypeError, ValueError, OverflowError) as exc:
        raise StreamContractError(
            f"{what} must be representable as real float64 values"
        ) from exc


def _contains_non_finite_rows(data: np.ndarray) -> bool:
    """Scan a signal in bounded row blocks, without an N-by-C boolean temporary."""
    block_rows = 1024
    for start in range(0, data.shape[0], block_rows):
        if not bool(np.isfinite(data[start : start + block_rows]).all()):
            return True
    return False


def _validated_covariance_matrix(
    values: np.ndarray, *, expected_shape: Tuple[int, int], what: str
) -> np.ndarray:
    """Require a finite float64 covariance with the exact comparable shape."""
    matrix = np.asarray(values)
    if matrix.shape != expected_shape:
        raise StreamContractError(
            f"{what} covariance shape {matrix.shape} != expected {expected_shape}"
        )
    if matrix.dtype != np.dtype(np.float64):
        raise StreamContractError(
            f"{what} covariance dtype {matrix.dtype} != expected float64"
        )
    if not bool(np.isfinite(matrix).all()):
        raise StreamContractError(f"{what} covariance contains non-finite values")
    return matrix


def validate_signal_shape(signal: np.ndarray, *, max_channels: int) -> np.ndarray:
    """Require ``(samples, channels)`` layout; reject empty / oversized channel axes.

    A 1-D vector is rejected rather than reshaped into a single-channel matrix, and
    complex input is rejected rather than cast. ``batch_stream_covariance_parity``
    applies the same rules, so batch and stream paths accept the same inputs.
    """
    data = _as_real_float64(signal, what="signal")
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
      mode never pads: samples past the last full window are dropped when
      ``allow_uneven_final`` is True and raise ``ChunkBoundError`` otherwise.
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
    covered = 0
    while start < n:
        stop = start + policy.chunk_size
        if stop > n:
            if policy.overlapping:
                # Overlap mode never pads. Samples after the last full window form an
                # uneven final: dropped when allowed, refused when uneven finals are off.
                if covered < n and not bounds.allow_uneven_final:
                    raise ChunkBoundError(
                        f"end-of-stream remainder {n - covered} samples past the last "
                        f"full window is shorter than chunk_size {policy.chunk_size} and "
                        "uneven finals are disabled"
                    )
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
        covered = stop
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
        if not isinstance(self.bounds, StreamBounds):
            raise StreamContractError("bounds must be a StreamBounds instance")
        self.n_channels = _positive_integer(self.n_channels, name="n_channels")
        if self.n_channels > self.bounds.max_channels:
            raise ChunkBoundError(
                f"n_channels {self.n_channels} exceeds max_channels "
                f"{self.bounds.max_channels}"
            )
        self.run_id = _nonempty_string(self.run_id, name="run_id")
        self.cov = RollingCovariance(self.n_channels)
        self.summary = IncrementalSummary(self.n_channels)

    def reset(self, run_id: str) -> None:
        """Clear accumulators for an independent subject/run (no cross-run leakage)."""
        validated_run_id = _nonempty_string(run_id, name="run_id")
        self.run_id = validated_run_id
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
        if run_id is not None:
            supplied_run_id = _nonempty_string(run_id, name="run_id")
            if supplied_run_id != self.run_id:
                raise StreamContractError(
                    "run_id mismatch; call reset() between independent subjects/runs"
                )
        block = _as_real_float64(chunk, what="chunk")
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
    explicit; this is engineering parity, not a scientific PASS. Invalid,
    non-finite, or numerically unrepresentable comparisons raise
    ``StreamContractError`` instead of returning an equivalence verdict.
    """
    data = _as_real_float64(signal, what="signal")
    if data.ndim != 2:
        raise ShapeContractError("signal must be 2-D (samples, channels)")
    if data.shape[0] < 2:
        raise EmptyInputError("covariance parity requires at least 2 samples")
    if data.shape[1] == 0:
        raise EmptyInputError("covariance parity requires at least 1 channel")
    try:
        requested_chunk_sizes = tuple(chunk_sizes)
    except (TypeError, ValueError, OverflowError) as exc:
        raise StreamContractError(
            "chunk_sizes must be a non-empty sequence of positive integers"
        ) from exc
    if not requested_chunk_sizes:
        raise StreamContractError("chunk_sizes must not be empty")
    try:
        validated_chunk_sizes = tuple(
            _positive_integer(chunk_size, name="chunk_size")
            for chunk_size in requested_chunk_sizes
        )
    except StreamContractError as exc:
        raise StreamContractError(f"invalid chunk_sizes: {exc}") from exc

    absolute_tolerance = _finite_nonnegative_tolerance(atol, name="atol")
    relative_tolerance = _finite_nonnegative_tolerance(rtol, name="rtol")

    if _contains_non_finite_rows(data):
        raise StreamContractError("signal contains non-finite values")

    with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
        reference = np.asarray(np.cov(data, rowvar=False, ddof=1))
    # NumPy returns a scalar for one channel; the streaming contract is always C×C.
    if reference.ndim == 0 and data.shape[1] == 1:
        reference = reference.reshape((1, 1))
    expected_shape = (data.shape[1], data.shape[1])
    reference = _validated_covariance_matrix(
        reference, expected_shape=expected_shape, what="batch"
    )

    out: List[Tuple[int, bool, float]] = []
    for chunk_size in validated_chunk_sizes:
        acc = RollingCovariance(data.shape[1])
        with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
            for start in range(0, data.shape[0], chunk_size):
                acc.update(data[start : start + chunk_size])
            got = acc.matrix(ddof=1)
        got = _validated_covariance_matrix(
            got, expected_shape=expected_shape, what="stream"
        )

        with np.errstate(over="ignore", invalid="ignore"):
            absolute_difference = np.abs(got - reference)
        if not bool(np.isfinite(absolute_difference).all()):
            raise StreamContractError(
                "covariance difference is non-finite or not representable as float64"
            )
        max_abs_diff = float(np.max(absolute_difference))

        # Normalize before applying the tolerance formula to avoid overflow in
        # ``atol + rtol * abs(reference)`` for finite but very large covariances.
        scale = np.maximum(np.abs(got), np.abs(reference))
        if absolute_tolerance > 0.0:
            scale = np.maximum(scale, absolute_tolerance)
        scale = np.where(scale == 0.0, 1.0, scale)
        with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
            normalized_difference = np.abs(got / scale - reference / scale)
            normalized_tolerance = (
                absolute_tolerance / scale
                + relative_tolerance * (np.abs(reference) / scale)
            )
        if not bool(
            np.isfinite(normalized_difference).all()
            and np.isfinite(normalized_tolerance).all()
        ):
            raise StreamContractError("normalized covariance comparison is non-finite")
        equivalent = bool(np.all(normalized_difference <= normalized_tolerance))
        out.append((chunk_size, equivalent, max_abs_diff))
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
