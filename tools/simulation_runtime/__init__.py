"""Measured runtime helpers for real simulation paths.

The helpers in this package preserve the public simulation APIs.  They are
performance implementations only; their outputs remain candidate telemetry,
not scientific evidence.
"""

from .topology_metrics import audit_snapshot_reuse

__all__ = ["audit_snapshot_reuse"]
