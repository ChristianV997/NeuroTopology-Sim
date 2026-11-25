"""Streaming paired-cohort topology execution and descriptive aggregation subsystem."""
from __future__ import annotations

from .executor import execute_cohort_topology
from .manifest_validator import validate_manifest_readiness
from .models import (
    CohortTopologyExecutionSummary,
    ConditionStreamSummary,
    ExecutionStatus,
    PairExecutionSummary,
    RefusalReasonCode,
    WindowMetrics,
)
from .streamer import RecordingStreamer, StreamMetadata
from .topology import compute_window_topology

__all__ = [
    "CohortTopologyExecutionSummary",
    "ConditionStreamSummary",
    "ExecutionStatus",
    "PairExecutionSummary",
    "RefusalReasonCode",
    "WindowMetrics",
    "RecordingStreamer",
    "StreamMetadata",
    "compute_window_topology",
    "execute_cohort_topology",
    "validate_manifest_readiness",
]
