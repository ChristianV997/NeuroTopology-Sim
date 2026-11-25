"""Synthetic pipeline replay and structural conformance harness."""
from __future__ import annotations

from .checker import evaluate_boundary
from .contracts import (
    BoundaryReport,
    BoundaryStatus,
    ReplayExitCode,
    ReplayReport,
    ReplayStatus,
    StageMetadata,
)

__all__ = [
    "BoundaryReport",
    "BoundaryStatus",
    "ReplayExitCode",
    "ReplayReport",
    "ReplayStatus",
    "StageMetadata",
    "SyntheticPipelineReplayRunner",
    "evaluate_boundary",
]


def __getattr__(name: str):
    if name == "SyntheticPipelineReplayRunner":
        from .runner import SyntheticPipelineReplayRunner
        return SyntheticPipelineReplayRunner
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
