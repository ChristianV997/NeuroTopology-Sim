"""Awareness Studio research-cycle evidence graph projection subsystem.

Provides deterministic read-only projections connecting literature, claims,
hypotheses, experiments, runs, artifacts, validations, and theory revisions.
Pure standard library, offline, and tamper-evident.
"""
from __future__ import annotations

from .builder import EvidenceGraphBuilder
from .diagnostics import run_graph_diagnostics
from .loader import (
    load_from_dict,
    load_from_jsonl,
    load_manifest_file,
)
from .models import (
    EvidenceGraph,
    GraphDiagnostic,
    GraphEdge,
    GraphNode,
    GraphSummary,
    compute_content_checksum,
)
from .research_cycle_adapter import manifest_from_ledger
from .serialization import (
    save_graph,
    to_awareness_summary,
    to_json,
    to_markdown,
)
from .types import (
    DiagnosticCode,
    DiagnosticSeverity,
    EdgeType,
    EvidenceClass,
    NodeStatus,
    NodeType,
    SafetyLabel,
)

__all__ = [
    "NodeType",
    "EdgeType",
    "EvidenceClass",
    "NodeStatus",
    "DiagnosticSeverity",
    "DiagnosticCode",
    "SafetyLabel",
    "GraphNode",
    "GraphEdge",
    "GraphDiagnostic",
    "GraphSummary",
    "EvidenceGraph",
    "EvidenceGraphBuilder",
    "run_graph_diagnostics",
    "load_from_dict",
    "load_from_jsonl",
    "load_manifest_file",
    "to_json",
    "to_markdown",
    "to_awareness_summary",
    "save_graph",
    "compute_content_checksum",
    "manifest_from_ledger",
]
