"""Replay audits for checkpointed bounded streaming.

Compares a clean run against an interrupted-then-resumed run and emits a
JSON-safe audit report (checksums, aggregates, optional memory metadata).
Does not materialize full trajectories and does not modify
``bounded.py`` / ``adaptive.py`` / ``memory_telemetry.py``.

Scientific-integrity note: synthetic fixtures here are reproducibility
scaffolding only — never scientific evidence.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional, Union

import numpy as np

from tools.streaming.bounded import bounded_stream
from tools.streaming.checkpoints import (
    CHECKPOINT_SCHEMA_VERSION,
    CheckpointedRunResult,
    checkpointed_bounded_stream,
    compute_source_checksum,
    load_checkpoint,
)

__all__ = [
    "ReplayAuditReport",
    "make_fixture",
    "run_clean",
    "run_interrupted_resume",
    "aggregates_equal",
    "build_replay_audit",
    "json_safe_report",
]

PathLike = Union[str, Path]


def make_fixture(
    n_samples: int = 8000,
    n_channels: int = 6,
    seed: int = 0,
) -> np.ndarray:
    """Deterministic synthetic ``(n_samples, n_channels)`` float64 signal."""
    rng = np.random.default_rng(seed)
    return rng.standard_normal((n_samples, n_channels)).astype(np.float64)


def _json_safe(value: Any) -> Any:
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


def _aggregate_dict(stream_result) -> Dict[str, Any]:
    return {
        "count": int(stream_result.count),
        "mean": [float(x) for x in np.asarray(stream_result.mean, dtype=np.float64)],
        "variance": [float(x) for x in np.asarray(stream_result.variance, dtype=np.float64)],
        "minimum": [float(x) for x in np.asarray(stream_result.minimum, dtype=np.float64)],
        "maximum": [float(x) for x in np.asarray(stream_result.maximum, dtype=np.float64)],
        "checksum": float(stream_result.checksum),
        "n_chunks": int(stream_result.n_chunks),
        "chunk_size": int(stream_result.chunk_size),
        "peak_bytes": None if stream_result.peak_bytes is None else int(stream_result.peak_bytes),
    }


def aggregates_equal(a, b, *, atol: float = 0.0, rtol: float = 0.0) -> bool:
    """True when two stream results match bit-for-bit (default) or within tol."""
    if a.count != b.count:
        return False
    if a.checksum != b.checksum and not np.isclose(a.checksum, b.checksum, atol=atol, rtol=rtol):
        return False
    return (
        np.allclose(a.mean, b.mean, atol=atol, rtol=rtol)
        and np.allclose(a.variance, b.variance, atol=atol, rtol=rtol)
        and np.array_equal(a.minimum, b.minimum)
        and np.array_equal(a.maximum, b.maximum)
    )


def run_clean(
    signal: np.ndarray,
    chunk_size: int,
    checkpoint_path: PathLike,
    *,
    overlap: int = 0,
    track_memory: bool = False,
    provenance_label: str = "replay-clean",
    backend: str = "numpy",
) -> CheckpointedRunResult:
    """Full checkpointed run with no interruption."""
    return checkpointed_bounded_stream(
        signal,
        chunk_size,
        checkpoint_path,
        overlap=overlap,
        resume=False,
        track_memory=track_memory,
        provenance_label=provenance_label,
        backend=backend,
        write_final_checkpoint=True,
    )


def run_interrupted_resume(
    signal: np.ndarray,
    chunk_size: int,
    checkpoint_path: PathLike,
    *,
    interrupt_after_windows: int,
    overlap: int = 0,
    track_memory: bool = False,
    provenance_label: str = "replay-resume",
    backend: str = "numpy",
) -> Dict[str, CheckpointedRunResult]:
    """Interrupt after ``interrupt_after_windows``, then resume to completion."""
    path = Path(checkpoint_path)
    if path.exists():
        path.unlink()
    first = checkpointed_bounded_stream(
        signal,
        chunk_size,
        path,
        overlap=overlap,
        resume=False,
        track_memory=track_memory,
        provenance_label=provenance_label,
        backend=backend,
        interrupt_after_windows=interrupt_after_windows,
        write_final_checkpoint=False,
    )
    second = checkpointed_bounded_stream(
        signal,
        chunk_size,
        path,
        overlap=overlap,
        resume=True,
        track_memory=track_memory,
        provenance_label=provenance_label,
        backend=backend,
        write_final_checkpoint=True,
    )
    return {"interrupted": first, "resumed": second}


@dataclass
class ReplayAuditReport:
    """Structured comparison of clean vs interrupted/resumed runs."""

    schema_version: str
    source_checksum: str
    chunk_size: int
    overlap: int
    n_samples: int
    n_channels: int
    clean: Dict[str, Any]
    interrupted: Dict[str, Any]
    resumed: Dict[str, Any]
    reference_bounded: Optional[Dict[str, Any]]
    equivalence: Dict[str, Any]
    memory_metadata: Dict[str, Any]
    checkpoint_schema_version: str
    provenance_label: str

    def to_dict(self) -> Dict[str, Any]:
        return json_safe_report(self)


def json_safe_report(report: ReplayAuditReport) -> Dict[str, Any]:
    return _json_safe(
        {
            "schema_version": report.schema_version,
            "checkpoint_schema_version": report.checkpoint_schema_version,
            "source_checksum": report.source_checksum,
            "chunk_size": report.chunk_size,
            "overlap": report.overlap,
            "n_samples": report.n_samples,
            "n_channels": report.n_channels,
            "provenance_label": report.provenance_label,
            "clean": report.clean,
            "interrupted": report.interrupted,
            "resumed": report.resumed,
            "reference_bounded": report.reference_bounded,
            "equivalence": report.equivalence,
            "memory_metadata": report.memory_metadata,
        }
    )


def build_replay_audit(
    signal: np.ndarray,
    chunk_size: int,
    work_dir: PathLike,
    *,
    interrupt_after_windows: int,
    overlap: int = 0,
    track_memory: bool = True,
    compare_bounded_reference: bool = True,
    provenance_label: str = "streaming-replay-audit",
    backend: str = "numpy",
) -> ReplayAuditReport:
    """Execute clean + interrupted/resume paths and build an audit report."""
    work = Path(work_dir)
    work.mkdir(parents=True, exist_ok=True)
    clean_path = work / "clean.ckpt.json"
    resume_path = work / "resume.ckpt.json"
    if clean_path.exists():
        clean_path.unlink()
    if resume_path.exists():
        resume_path.unlink()

    clean = run_clean(
        signal,
        chunk_size,
        clean_path,
        overlap=overlap,
        track_memory=track_memory,
        provenance_label=f"{provenance_label}:clean",
        backend=backend,
    )
    parts = run_interrupted_resume(
        signal,
        chunk_size,
        resume_path,
        interrupt_after_windows=interrupt_after_windows,
        overlap=overlap,
        track_memory=track_memory,
        provenance_label=f"{provenance_label}:resume",
        backend=backend,
    )
    interrupted = parts["interrupted"]
    resumed = parts["resumed"]

    ref_dict = None
    ref_equal = None
    if compare_bounded_reference and overlap == 0:
        ref = bounded_stream(signal, chunk_size, track_memory=track_memory)
        ref_dict = _aggregate_dict(ref)
        ref_equal = aggregates_equal(clean.stream, ref)

    eq_clean_resume = aggregates_equal(clean.stream, resumed.stream)
    ckpt = load_checkpoint(resume_path) if resume_path.exists() else None

    memory_metadata = {
        "clean_peak_bytes": clean.stream.peak_bytes,
        "interrupted_peak_bytes": interrupted.stream.peak_bytes,
        "resumed_peak_bytes": resumed.stream.peak_bytes,
        "reference_bounded_peak_bytes": None if ref_dict is None else ref_dict.get("peak_bytes"),
        "note": (
            "tracemalloc peak when track_memory=True; process RSS is out of scope "
            "here (see tools.streaming.memory_telemetry). Peaks are not absolute "
            "guarantees of process RSS."
        ),
    }

    data = np.asarray(signal)
    n_samples, n_channels = (data.shape[0], 1) if data.ndim == 1 else data.shape

    return ReplayAuditReport(
        schema_version="1.0",
        source_checksum=compute_source_checksum(data),
        chunk_size=int(chunk_size),
        overlap=int(overlap),
        n_samples=int(n_samples),
        n_channels=int(n_channels),
        clean={
            "aggregates": _aggregate_dict(clean.stream),
            "checkpoints_written": clean.checkpoints_written,
            "resumed": clean.resumed,
            "interrupted": clean.interrupted,
        },
        interrupted={
            "aggregates": _aggregate_dict(interrupted.stream),
            "checkpoints_written": interrupted.checkpoints_written,
            "resumed": interrupted.resumed,
            "interrupted": interrupted.interrupted,
            "completed_window_count": interrupted.stream.n_chunks,
        },
        resumed={
            "aggregates": _aggregate_dict(resumed.stream),
            "checkpoints_written": resumed.checkpoints_written,
            "resumed": resumed.resumed,
            "interrupted": resumed.interrupted,
            "final_aggregate_state_checksum": (
                None if ckpt is None else ckpt.aggregate_state_checksum
            ),
        },
        reference_bounded=ref_dict,
        equivalence={
            "clean_vs_resumed": bool(eq_clean_resume),
            "clean_vs_bounded_reference": ref_equal,
            "checksum_clean": float(clean.stream.checksum),
            "checksum_resumed": float(resumed.stream.checksum),
            "checksum_interrupted_partial": float(interrupted.stream.checksum),
        },
        memory_metadata=memory_metadata,
        checkpoint_schema_version=CHECKPOINT_SCHEMA_VERSION,
        provenance_label=provenance_label,
    )
