"""Type definitions and enumerations for the Awareness Studio evidence graph.

Defines all 9 required node types, 10 edge types, evidence classifications,
epistemic statuses, diagnostic codes, and scientific safety labels.
Stdlib-only, no heavy dependencies.
"""
from __future__ import annotations

import enum


class NodeType(str, enum.Enum):
    """The 9 required graph node types."""
    SOURCE_SNAPSHOT = "source_snapshot"
    EVIDENCE_RECORD = "evidence_record"
    CLAIM = "claim"
    HYPOTHESIS = "hypothesis"
    EXPERIMENT = "experiment"
    RUN = "run"
    ARTIFACT = "artifact"
    VALIDATION = "validation"
    THEORY_REVISION = "theory_revision"


class EdgeType(str, enum.Enum):
    """The 10 required graph edge types."""
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    TESTS = "tests"
    GENERATED_BY = "generated_by"
    DERIVED_FROM = "derived_from"
    VALIDATES = "validates"
    REVISES = "revises"
    SUPERSEDES = "supersedes"
    BLOCKED_BY = "blocked_by"
    REFERENCES = "references"


class EvidenceClass(str, enum.Enum):
    """Classification of evidence rigor and origin."""
    SYNTHETIC = "synthetic"
    PROXY = "proxy"
    EMPIRICAL = "empirical"
    FORMAL = "formal"
    UNKNOWN = "unknown"


class NodeStatus(str, enum.Enum):
    """Operational and epistemic status of an entity in the graph."""
    PROPOSED = "proposed"
    ACTIVE = "active"
    PROVISIONAL = "provisional"
    INCONCLUSIVE = "inconclusive"
    REVIEW_REQUIRED = "review_required"
    SUPPORTED = "supported"
    WEAKENED = "weakened"
    FALSIFIED = "falsified"
    CONTRADICTED = "contradicted"
    SUPERSEDED = "superseded"
    REJECTED = "rejected"
    BLOCKED = "blocked"


class DiagnosticSeverity(str, enum.Enum):
    """Severity levels for graph diagnostics."""
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class DiagnosticCode(str, enum.Enum):
    """Machine-readable diagnostic issue codes."""
    ORPHAN_ARTIFACT = "orphan_artifact"
    ORPHAN_NODE = "orphan_node"
    DANGLING_EDGE_TARGET = "dangling_edge_target"
    DANGLING_EDGE_SOURCE = "dangling_edge_source"
    DUPLICATE_NODE_EXACT = "duplicate_node_exact"
    DUPLICATE_NODE_CONTENT_MISMATCH = "duplicate_node_content_mismatch"
    DUPLICATE_EDGE = "duplicate_edge"
    CONFLICTING_STATUS = "conflicting_status"
    UNSUPPORTED_PROMOTION = "unsupported_promotion"
    SYNTHETIC_FORMAL_VIOLATION = "synthetic_formal_violation"
    PROXY_FORMAL_VIOLATION = "proxy_formal_violation"
    SUPERSEDED_UNLINKED = "superseded_unlinked"
    EMPIRICAL_CLAIM_WITHOUT_VERIFICATION = "empirical_claim_without_verification"


class SafetyLabel(str, enum.Enum):
    """Scientific safety and epistemic boundary labels."""
    NO_CLINICAL_CLAIM = "NO_CLINICAL_CLAIM"
    NO_ONTOLOGY_PROMOTION = "NO_ONTOLOGY_PROMOTION"
    NON_PROMOTED = "NON_PROMOTED"
    SYNTHETIC_ONLY = "SYNTHETIC_ONLY"
    PROXY_METRIC = "PROXY_METRIC"
    PROVISIONAL = "PROVISIONAL"
    INCONCLUSIVE = "INCONCLUSIVE"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"
