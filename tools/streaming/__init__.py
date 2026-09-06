"""Streaming utilities for NeuroTopology-Sim.

Exposes the bounded, allocation-conscious streaming helpers. The S3
download/checkpoint skeleton in :mod:`tools.streaming.base_runner` is imported
lazily by its callers and intentionally not re-exported here (it pulls optional
boto3/awscli dependencies only when actually used).
"""
from __future__ import annotations

from .bounded import (
    MemoryTelemetry,
    StreamAggregate,
    StreamResult,
    bounded_stream,
    iter_chunks,
    iter_windows,
)

__all__ = [
    "MemoryTelemetry",
    "StreamAggregate",
    "StreamResult",
    "bounded_stream",
    "iter_chunks",
    "iter_windows",
]
