"""Schema constants for MOABB protocol-conformance manifests."""
from __future__ import annotations

from enum import Enum
from typing import FrozenSet, Tuple

PROTOCOL_SCHEMA_VERSION = "NeuroTopology.MoabbProtocolManifest.v1"
EVIDENCE_CLASS = "protocol_conformance_only"
PROVENANCE_LABEL = "offline_metadata_or_fixture_only"

# Referenced MOABB evaluation patterns (names only; package not imported).
# Source: NeuroTechX/moabb evaluations (BSD-3-Clause), inspected via public docs.
KNOWN_SPLIT_POLICIES: FrozenSet[str] = frozenset(
    {
        "within_session_kfold",
        "within_subject_session_pooled_kfold",
        "cross_session_leave_one_out",
        "cross_subject_leave_one_out",
        "custom_subject_holdout",
        "unspecified",
        "random_trial_split",  # always leakage-risk; cannot pass as conforming
    }
)

UNITS_OF_ANALYSIS: FrozenSet[str] = frozenset(
    {
        "subject",
        "session",
        "recording",
        "trial",
        "window",
    }
)

EVALUATION_METRICS: FrozenSet[str] = frozenset(
    {
        "accuracy",
        "balanced_accuracy",
        "roc_auc",
        "cohen_kappa",
        "f1",
        "unspecified",
    }
)

OWNED_PATH_PREFIXES: Tuple[str, ...] = (
    "tools/moabb_protocol_conformance/",
    "tests/tools/moabb_protocol_conformance/",
    "docs/tools/moabb_protocol_conformance.md",
)

FORBIDDEN_CLAIM_PHRASES: Tuple[str, ...] = (
    "benchmark ran",
    "benchmark completed",
    "scientifically validated",
    "data are locally available",
    "dataset downloaded",
    "proves consciousness",
    "clinical treatment",
)


class ConformanceStatus(str, Enum):
    CONFORMING = "conforming"
    INCOMPLETE = "incomplete"
    INCONCLUSIVE = "inconclusive"
    FAILED = "failed"
    BLOCKED = "blocked"


class MetadataTrust(str, Enum):
    VERIFIED = "verified"  # explicitly supplied and non-conflicting
    UNKNOWN = "unknown"  # absent / not independently verified
    CONFLICTING = "conflicting"  # contradictory inputs
