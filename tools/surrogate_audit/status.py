"""Audit statuses — never scientific VALIDATED."""
from __future__ import annotations

from enum import Enum


class EvidenceClass(str, Enum):
    SYNTHETIC_ONLY = "SYNTHETIC_ONLY"


class AuditStatus(str, Enum):
    """Engineering audit outcome for a spectral/marginal contract check."""

    MET = "MET"
    UNMET = "UNMET"
    NOT_APPLICABLE = "NOT_APPLICABLE"
    INVALID_INPUT = "INVALID_INPUT"
