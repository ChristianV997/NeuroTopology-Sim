"""Synthetic pipeline replay and structural conformance harness."""
from __future__ import annotations

from .checker import evaluate_boundary
from .contracts import BoundaryReport, BoundaryStatus, ReplayReport, ReplayStatus, StageMetadata
from .runner import SyntheticPipelineReplayRunner

__all__ = [
    "BoundaryReport",
    "BoundaryStatus",
    "ReplayReport",
    "ReplayStatus",
    "StageMetadata",
    "SyntheticPipelineReplayRunner",
    "evaluate_boundary",
]
