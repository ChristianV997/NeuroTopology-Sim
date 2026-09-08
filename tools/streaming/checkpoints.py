"""Deterministic streaming checkpoints for bounded stream processing.

Provides JSON-safe, atomically written checkpoint records so a long bounded
stream can be interrupted and resumed without materializing a full trajectory.
Resume restores aggregate state and continues from ``current_offset``; a clean
run and an interrupted-then-resumed run must produce the same aggregates for
identical configuration and source data.

This module is purely additive: it imports :class:`~tools.streaming.bounded.StreamAggregate`
and :func:`~tools.streaming.bounded.iter_chunks` but does not modify
``bounded.py``, ``adaptive.py``, or ``memory_telemetry.py``.

Scientific-integrity note: fixtures and demos are performance / reproducibility
scaffolding only — never scientific evidence. No topology or Bayes-factor
semantics are claimed.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Union

import numpy as np

from tools.streaming.bounded import StreamAggregate, StreamResult, iter_chunks

__all__ = [
    "CHECKPOINT_SCHEMA_VERSION",
    "CheckpointError",
    "CheckpointCorruptionError",
    "CheckpointConfigMismatchError",
    "CheckpointSourceMismatchError",
    "StreamInterrupt",
    "StreamCheckpoint",
    "CheckpointedRunResult",
    "compute_source_checksum",
    "compute_configuration_hash",
    "aggregate_state_from_stream",
    "restore_aggregate",
    "aggregate_state_checksum",
    "build_checkpoint",
    "write_checkpoint",
    "load_checkpoint",
    "validate_resume",
    "checkpointed_bounded_stream",
]

CHECKPOINT_SCHEMA_VERSION = "1.0"

PathLike = Union[str, Path]


class CheckpointError(Exception):
    """Base error for checkpoint / resume failures."""


class CheckpointCorruptionError(CheckpointError):
    """Raised when a checkpoint file is partial, invalid, or checksum-mismatched."""


class CheckpointConfigMismatchError(CheckpointError):
    """Raised when resume configuration does not match the checkpoint."""


class CheckpointSourceMismatchError(CheckpointError):
    """Raised when the source signal checksum does not match the checkpoint."""


# --------------------------------------------------------------------------- #
# Hashing / JSON helpers
# --------------------------------------------------------------------------- #


def _json_safe(value: Any) -> Any:
    """Recursively convert to JSON-safe form; non-finite floats become ``None``."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (np.floating,)):
        f = float(value)
        return f if math.isfinite(f) else None
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, np.ndarray):
        return _json_safe(value.tolist())
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


def _canonical_json(obj: Any) -> str:
    """Stable JSON serialization for hashing (sorted keys, no NaN)."""
    return json.dumps(_json_safe(obj), sort_keys=True, separators=(",", ":"), allow_nan=False)


def _sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def compute_source_checksum(signal: np.ndarray) -> str:
    """Deterministic checksum of source array bytes, shape, and dtype.

    Hashes in fixed-size blocks so a full second trajectory is never materialized.
    """
    arr = np.ascontiguousarray(np.asarray(signal))
    h = hashlib.sha256()
    h.update(str(arr.shape).encode("utf-8"))
    h.update(b"|")
    h.update(str(arr.dtype).encode("utf-8"))
    h.update(b"|")
    view = memoryview(arr).cast("B")
    block = 1024 * 1024
    for start in range(0, len(view), block):
        h.update(view[start:start + block])
    return h.hexdigest()


def compute_configuration_hash(
    *,
    chunk_size: int,
    overlap: int,
    dtype: str,
    n_channels: int,
    n_samples: int,
    backend: str,
    check_finite: bool = True,
) -> str:
    """Hash of resume-critical configuration (excludes provenance / timestamps)."""
    payload = {
        "backend": str(backend),
        "check_finite": bool(check_finite),
        "chunk_size": int(chunk_size),
        "dtype": str(dtype),
        "n_channels": int(n_channels),
        "n_samples": int(n_samples),
        "overlap": int(overlap),
    }
    return _sha256_hex(_canonical_json(payload))


def aggregate_state_from_stream(agg: StreamAggregate) -> Dict[str, Any]:
    """Serialize :class:`StreamAggregate` to a finite, JSON-safe dict."""
    if agg.count < 1:
        # Empty aggregates use +/-Inf sentinels; expose nulls instead of Inf.
        minimum: Any = [None] * int(agg.mean.shape[0])
        maximum: Any = [None] * int(agg.mean.shape[0])
        mean = [0.0] * int(agg.mean.shape[0])
        m2 = [0.0] * int(agg.mean.shape[0])
        checksum = 0.0
    else:
        mean = [float(x) for x in np.asarray(agg.mean, dtype=np.float64)]
        m2 = [float(x) for x in np.asarray(agg._m2, dtype=np.float64)]
        minimum = [float(x) for x in np.asarray(agg.minimum, dtype=np.float64)]
        maximum = [float(x) for x in np.asarray(agg.maximum, dtype=np.float64)]
        checksum = float(agg.checksum)
        for name, seq in (("mean", mean), ("m2", m2), ("minimum", minimum), ("maximum", maximum)):
            if any(not math.isfinite(v) for v in seq):
                raise CheckpointError(f"non-finite value in aggregate field {name}")
        if not math.isfinite(checksum):
            raise CheckpointError("non-finite aggregate checksum")
    state = {
        "count": int(agg.count),
        "mean": mean,
        "m2": m2,
        "minimum": minimum,
        "maximum": maximum,
        "checksum": checksum,
    }
    return _json_safe(state)


def restore_aggregate(state: Dict[str, Any]) -> StreamAggregate:
    """Rebuild a :class:`StreamAggregate` from serialized state."""
    if not isinstance(state, dict):
        raise CheckpointCorruptionError("aggregate_state must be an object")
    required = ("count", "mean", "m2", "minimum", "maximum", "checksum")
    missing = [k for k in required if k not in state]
    if missing:
        raise CheckpointCorruptionError(f"aggregate_state missing fields: {missing}")
    mean = np.asarray(state["mean"], dtype=np.float64)
    m2 = np.asarray(state["m2"], dtype=np.float64)
    n = int(mean.shape[0])
    if m2.shape != mean.shape:
        raise CheckpointCorruptionError("aggregate_state mean/m2 shape mismatch")
    count = int(state["count"])
    if count < 1:
        minimum = np.full(n, np.inf, dtype=np.float64)
        maximum = np.full(n, -np.inf, dtype=np.float64)
    else:
        minimum = np.asarray(
            [(-math.inf if v is None else v) for v in state["minimum"]],
            dtype=np.float64,
        )
        maximum = np.asarray(
            [(math.inf if v is None else v) for v in state["maximum"]],
            dtype=np.float64,
        )
        if minimum.shape != mean.shape or maximum.shape != mean.shape:
            raise CheckpointCorruptionError("aggregate_state min/max shape mismatch")
    return StreamAggregate(
        count=count,
        mean=mean.copy(),
        _m2=m2.copy(),
        minimum=minimum.copy(),
        maximum=maximum.copy(),
        checksum=float(state["checksum"]),
    )


def aggregate_state_checksum(state: Dict[str, Any]) -> str:
    """Deterministic checksum of the aggregate-state payload."""
    return _sha256_hex(_canonical_json(state))


# --------------------------------------------------------------------------- #
# Checkpoint record
# --------------------------------------------------------------------------- #


@dataclass
class StreamCheckpoint:
    """One resumable snapshot of bounded stream progress."""

    schema_version: str
    source_checksum: str
    n_channels: int
    n_samples: int
    dtype: str
    chunk_size: int
    overlap: int
    current_offset: int
    completed_window_count: int
    aggregate_state: Dict[str, Any]
    aggregate_state_checksum: str
    backend: str
    configuration_hash: str
    provenance_label: str
    timestamp: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "source_checksum": self.source_checksum,
            "n_channels": int(self.n_channels),
            "n_samples": int(self.n_samples),
            "dtype": str(self.dtype),
            "chunk_size": int(self.chunk_size),
            "overlap": int(self.overlap),
            "current_offset": int(self.current_offset),
            "completed_window_count": int(self.completed_window_count),
            "aggregate_state": self.aggregate_state,
            "aggregate_state_checksum": self.aggregate_state_checksum,
            "backend": str(self.backend),
            "configuration_hash": self.configuration_hash,
            "provenance_label": str(self.provenance_label),
        }
        if self.timestamp is not None:
            payload["timestamp"] = self.timestamp
        return _json_safe(payload)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "StreamCheckpoint":
        if not isinstance(data, dict):
            raise CheckpointCorruptionError("checkpoint root must be a JSON object")
        required = (
            "schema_version",
            "source_checksum",
            "n_channels",
            "n_samples",
            "dtype",
            "chunk_size",
            "overlap",
            "current_offset",
            "completed_window_count",
            "aggregate_state",
            "aggregate_state_checksum",
            "backend",
            "configuration_hash",
            "provenance_label",
        )
        missing = [k for k in required if k not in data]
        if missing:
            raise CheckpointCorruptionError(f"checkpoint missing fields: {missing}")
        return cls(
            schema_version=str(data["schema_version"]),
            source_checksum=str(data["source_checksum"]),
            n_channels=int(data["n_channels"]),
            n_samples=int(data["n_samples"]),
            dtype=str(data["dtype"]),
            chunk_size=int(data["chunk_size"]),
            overlap=int(data["overlap"]),
            current_offset=int(data["current_offset"]),
            completed_window_count=int(data["completed_window_count"]),
            aggregate_state=dict(data["aggregate_state"]),
            aggregate_state_checksum=str(data["aggregate_state_checksum"]),
            backend=str(data["backend"]),
            configuration_hash=str(data["configuration_hash"]),
            provenance_label=str(data["provenance_label"]),
            timestamp=None if data.get("timestamp") is None else str(data["timestamp"]),
        )

    def verify_integrity(self) -> None:
        """Raise :class:`CheckpointCorruptionError` if the record is inconsistent."""
        if self.schema_version != CHECKPOINT_SCHEMA_VERSION:
            raise CheckpointCorruptionError(
                f"unsupported schema_version {self.schema_version!r}; "
                f"expected {CHECKPOINT_SCHEMA_VERSION!r}"
            )
        if self.chunk_size < 1:
            raise CheckpointCorruptionError("chunk_size must be >= 1")
        if self.overlap < 0:
            raise CheckpointCorruptionError("overlap must be >= 0")
        if self.overlap >= self.chunk_size and self.chunk_size > 0:
            raise CheckpointCorruptionError("overlap must be < chunk_size")
        if self.n_channels < 1 or self.n_samples < 0:
            raise CheckpointCorruptionError("invalid channel/sample dimensions")
        if self.current_offset < 0 or self.current_offset > self.n_samples:
            raise CheckpointCorruptionError("current_offset out of range")
        if self.completed_window_count < 0:
            raise CheckpointCorruptionError("completed_window_count must be >= 0")
        expected = aggregate_state_checksum(self.aggregate_state)
        if expected != self.aggregate_state_checksum:
            raise CheckpointCorruptionError("aggregate_state_checksum mismatch")
        # Finite check on serialized floats.
        dumped = _canonical_json(self.to_dict())
        if "Infinity" in dumped or "NaN" in dumped:
            raise CheckpointCorruptionError("checkpoint contains non-finite JSON tokens")


def build_checkpoint(
    *,
    signal: np.ndarray,
    aggregate: StreamAggregate,
    chunk_size: int,
    overlap: int,
    current_offset: int,
    completed_window_count: int,
    backend: str,
    provenance_label: str,
    source_checksum: Optional[str] = None,
    include_timestamp: bool = False,
    check_finite: bool = True,
) -> StreamCheckpoint:
    """Construct a validated checkpoint from live stream state."""
    data = np.asarray(signal)
    if data.ndim == 1:
        n_samples, n_channels = data.shape[0], 1
    elif data.ndim == 2:
        n_samples, n_channels = data.shape
    else:
        raise ValueError("signal must be 1-D or 2-D")
    dtype = str(data.dtype)
    src = source_checksum if source_checksum is not None else compute_source_checksum(data)
    agg_state = aggregate_state_from_stream(aggregate)
    cfg = compute_configuration_hash(
        chunk_size=chunk_size,
        overlap=overlap,
        dtype=dtype,
        n_channels=n_channels,
        n_samples=n_samples,
        backend=backend,
        check_finite=check_finite,
    )
    ts = None
    if include_timestamp:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    cp = StreamCheckpoint(
        schema_version=CHECKPOINT_SCHEMA_VERSION,
        source_checksum=src,
        n_channels=n_channels,
        n_samples=n_samples,
        dtype=dtype,
        chunk_size=int(chunk_size),
        overlap=int(overlap),
        current_offset=int(current_offset),
        completed_window_count=int(completed_window_count),
        aggregate_state=agg_state,
        aggregate_state_checksum=aggregate_state_checksum(agg_state),
        backend=str(backend),
        configuration_hash=cfg,
        provenance_label=str(provenance_label),
        timestamp=ts,
    )
    cp.verify_integrity()
    return cp


def write_checkpoint(path: PathLike, checkpoint: StreamCheckpoint) -> None:
    """Atomically write ``checkpoint`` as finite JSON (temp file + ``os.replace``)."""
    checkpoint.verify_integrity()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(checkpoint.to_dict(), indent=2, sort_keys=True, allow_nan=False) + "\n"
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_name, str(path))
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def load_checkpoint(path: PathLike) -> StreamCheckpoint:
    """Load and validate a checkpoint; partial/corrupt files fail clearly."""
    path = Path(path)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CheckpointCorruptionError(f"cannot read checkpoint: {path}") from exc
    if not raw.strip():
        raise CheckpointCorruptionError(f"empty checkpoint file: {path}")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise CheckpointCorruptionError(f"invalid JSON in checkpoint: {path}") from exc
    cp = StreamCheckpoint.from_dict(data)
    cp.verify_integrity()
    return cp


def validate_resume(
    checkpoint: StreamCheckpoint,
    signal: np.ndarray,
    *,
    chunk_size: int,
    overlap: int,
    backend: str,
    check_finite: bool = True,
) -> None:
    """Detect source / configuration mismatches before resuming."""
    checkpoint.verify_integrity()
    data = np.asarray(signal)
    src = compute_source_checksum(data)
    if src != checkpoint.source_checksum:
        raise CheckpointSourceMismatchError(
            "source checksum mismatch: refusing to resume from a different source"
        )
    if data.ndim == 1:
        n_samples, n_channels = data.shape[0], 1
        dtype = str(data.dtype)
    elif data.ndim == 2:
        n_samples, n_channels = data.shape
        dtype = str(data.dtype)
    else:
        raise ValueError("signal must be 1-D or 2-D")
    if n_channels != checkpoint.n_channels or n_samples != checkpoint.n_samples:
        raise CheckpointSourceMismatchError(
            "source dimensions do not match checkpoint channel/sample dimensions"
        )
    if dtype != checkpoint.dtype:
        raise CheckpointConfigMismatchError(
            f"dtype mismatch: checkpoint={checkpoint.dtype!r} current={dtype!r}"
        )
    cfg = compute_configuration_hash(
        chunk_size=chunk_size,
        overlap=overlap,
        dtype=dtype,
        n_channels=n_channels,
        n_samples=n_samples,
        backend=backend,
        check_finite=check_finite,
    )
    if cfg != checkpoint.configuration_hash:
        raise CheckpointConfigMismatchError(
            "configuration hash mismatch: refusing to resume with different settings"
        )
    if int(chunk_size) != checkpoint.chunk_size or int(overlap) != checkpoint.overlap:
        raise CheckpointConfigMismatchError(
            "chunk_size/overlap mismatch versus checkpoint record"
        )
    if str(backend) != checkpoint.backend:
        raise CheckpointConfigMismatchError(
            f"backend mismatch: checkpoint={checkpoint.backend!r} current={backend!r}"
        )


# --------------------------------------------------------------------------- #
# Checkpointed stream runner
# --------------------------------------------------------------------------- #


@dataclass
class CheckpointedRunResult:
    """Outcome of :func:`checkpointed_bounded_stream`."""

    stream: StreamResult
    checkpoints_written: int
    resumed: bool
    final_checkpoint_path: Optional[str]
    interrupted: bool = False


def _as_2d(signal: np.ndarray) -> np.ndarray:
    arr = np.asarray(signal)
    if arr.ndim == 1:
        return arr.reshape(-1, 1)
    if arr.ndim == 2:
        return arr
    raise ValueError("signal must be 1-D (samples,) or 2-D (samples, channels)")


def _iter_windows_with_overlap(
    data: np.ndarray,
    chunk_size: int,
    overlap: int,
    start_offset: int,
):
    """Yield ``(offset_after, window_view)`` advancing by ``chunk_size - overlap``.

    When ``overlap == 0`` this matches :func:`iter_chunks` semantics (including a
    trailing partial window). When ``overlap > 0``, only complete windows of
    length ``chunk_size`` are emitted (deterministic fixed cost).
    """
    n = data.shape[0]
    if chunk_size < 1:
        raise ValueError("chunk_size must be >= 1")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap must satisfy 0 <= overlap < chunk_size")
    stride = chunk_size - overlap
    offset = int(start_offset)
    if overlap == 0:
        # Align with iter_chunks: start at offset, take successive chunks.
        # Resume offset is the next sample index (end of the window just done).
        while offset < n:
            end = min(offset + chunk_size, n)
            yield end, data[offset:end]
            offset = end
    else:
        # Resume offset is the *start* of the next window (start + stride),
        # not the exclusive end of the current window.
        while offset + chunk_size <= n:
            window = data[offset:offset + chunk_size]
            next_start = offset + stride
            yield next_start, window
            offset = next_start


class StreamInterrupt(Exception):
    """Internal: cooperative interruption after a checkpoint write (test fixture)."""


def checkpointed_bounded_stream(
    signal: np.ndarray,
    chunk_size: int,
    checkpoint_path: PathLike,
    *,
    overlap: int = 0,
    checkpoint_every: int = 1,
    resume: bool = False,
    backend: str = "numpy",
    provenance_label: str = "streaming-checkpoint",
    include_timestamp: bool = False,
    transform: Optional[Callable[[np.ndarray, np.ndarray], np.ndarray]] = None,
    summarize: Optional[Callable[[int, np.ndarray], object]] = None,
    store_history: bool = False,
    check_finite: bool = True,
    track_memory: bool = False,
    interrupt_after_windows: Optional[int] = None,
    write_final_checkpoint: bool = True,
) -> CheckpointedRunResult:
    """Run a bounded stream with periodic atomic checkpoints.

    Parameters
    ----------
    resume:
        When ``True`` and ``checkpoint_path`` exists, validate and continue from
        the stored offset / aggregate. Source and configuration mismatches raise
        before any further processing.
    interrupt_after_windows:
        Test / audit fixture: after writing the checkpoint that follows this many
        *new* windows in the current invocation, raise :class:`StreamInterrupt`
        (caught internally) and return with ``interrupted=True``.
    store_history:
        Default ``False``. Enabling it retains per-window copies and defeats the
        no-full-trajectory goal; left for parity with ``bounded_stream`` only.
    """
    if chunk_size < 1:
        raise ValueError("chunk_size must be >= 1")
    if checkpoint_every < 1:
        raise ValueError("checkpoint_every must be >= 1")
    data = _as_2d(signal)
    n_samples, n_channels = data.shape
    path = Path(checkpoint_path)

    source_checksum = compute_source_checksum(data)
    aggregate = StreamAggregate.empty(n_channels)
    offset = 0
    completed = 0
    resumed = False
    checkpoints_written = 0

    if resume and path.exists():
        existing = load_checkpoint(path)
        validate_resume(
            existing,
            data,
            chunk_size=chunk_size,
            overlap=overlap,
            backend=backend,
            check_finite=check_finite,
        )
        aggregate = restore_aggregate(existing.aggregate_state)
        offset = int(existing.current_offset)
        completed = int(existing.completed_window_count)
        resumed = True

    summaries: Optional[List[Any]] = [] if summarize is not None else None
    history: Optional[List[Any]] = [] if store_history else None
    work: Optional[np.ndarray] = None
    if transform is not None:
        work = np.empty((chunk_size, n_channels), dtype=np.float64)

    peak_bytes: Optional[int] = None
    new_windows = 0
    interrupted = False

    def _maybe_track():
        nonlocal peak_bytes
        if not track_memory:
            return None
        from tools.streaming.bounded import MemoryTelemetry

        return MemoryTelemetry()

    mem_cm = _maybe_track()

    def _run_loop() -> None:
        nonlocal offset, completed, checkpoints_written, new_windows, interrupted
        for next_offset, window in _iter_windows_with_overlap(data, chunk_size, overlap, offset):
            m = window.shape[0]
            if transform is not None:
                assert work is not None
                out = work[:m]
                values = np.asarray(transform(window, out), dtype=np.float64)
                if values.ndim != 2 or values.shape[1] != n_channels:
                    raise ValueError("transform must return a (m, n_channels) array")
            else:
                values = window
            if check_finite and not np.all(np.isfinite(values)):
                raise ValueError(f"non-finite value at window ending offset {next_offset}")
            aggregate.update(values)
            if summaries is not None:
                summaries.append(summarize(completed, values))
            if history is not None:
                history.append(np.array(values, dtype=np.float64, copy=True))
            offset = next_offset
            completed += 1
            new_windows += 1

            if completed % checkpoint_every == 0:
                cp = build_checkpoint(
                    signal=data,
                    aggregate=aggregate,
                    chunk_size=chunk_size,
                    overlap=overlap,
                    current_offset=offset,
                    completed_window_count=completed,
                    backend=backend,
                    provenance_label=provenance_label,
                    source_checksum=source_checksum,
                    include_timestamp=include_timestamp,
                    check_finite=check_finite,
                )
                write_checkpoint(path, cp)
                checkpoints_written += 1

            if interrupt_after_windows is not None and new_windows >= interrupt_after_windows:
                # Ensure a checkpoint exists at the interrupt boundary.
                if completed % checkpoint_every != 0:
                    cp = build_checkpoint(
                        signal=data,
                        aggregate=aggregate,
                        chunk_size=chunk_size,
                        overlap=overlap,
                        current_offset=offset,
                        completed_window_count=completed,
                        backend=backend,
                        provenance_label=provenance_label,
                        source_checksum=source_checksum,
                        include_timestamp=include_timestamp,
                        check_finite=check_finite,
                    )
                    write_checkpoint(path, cp)
                    checkpoints_written += 1
                interrupted = True
                raise StreamInterrupt()

    try:
        if mem_cm is not None:
            with mem_cm:
                _run_loop()
            peak_bytes = mem_cm.peak_bytes
        else:
            _run_loop()
    except StreamInterrupt:
        pass

    if write_final_checkpoint and not interrupted and offset >= n_samples:
        cp = build_checkpoint(
            signal=data,
            aggregate=aggregate,
            chunk_size=chunk_size,
            overlap=overlap,
            current_offset=offset,
            completed_window_count=completed,
            backend=backend,
            provenance_label=provenance_label,
            source_checksum=source_checksum,
            include_timestamp=include_timestamp,
            check_finite=check_finite,
        )
        write_checkpoint(path, cp)
        checkpoints_written += 1

    # Prefer counting windows actually processed this session for n_chunks parity
    # with StreamResult: report total completed windows.
    stream = StreamResult(
        n_samples=n_samples,
        n_channels=n_channels,
        n_chunks=completed,
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
    return CheckpointedRunResult(
        stream=stream,
        checkpoints_written=checkpoints_written,
        resumed=resumed,
        final_checkpoint_path=str(path) if path.exists() else None,
        interrupted=interrupted,
    )


# Keep iter_chunks import used for API compatibility / callers that pair both.
_ = iter_chunks
