"""Batch 2 release-readiness security harness (engineering evidence only).

This package audits network defaults, unsafe remote materialization patterns,
path containment, subprocess isolation, finite JSON, evidence-boundary
invariants, and incomplete artifact states. It never certifies scientific
validity: ``security_pass`` is not ``scientific_pass``.
"""
from __future__ import annotations

from tools.release_readiness.batch2_security.schema import (
    EVIDENCE_CLASS,
    SCHEMA_VERSION,
    ThreatClass,
)
from tools.release_readiness.batch2_security.runner import run_security_suite

__all__ = [
    "EVIDENCE_CLASS",
    "SCHEMA_VERSION",
    "ThreatClass",
    "run_security_suite",
]
