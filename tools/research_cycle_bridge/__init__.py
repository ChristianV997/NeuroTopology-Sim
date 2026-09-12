"""Research Cycle Bridge package linking simulation artifacts to canonical research-cycle ledgers, evidence graphs, and release evaluation."""
from __future__ import annotations

from tools.research_cycle_bridge.adapters import (
    adapt_bridge_to_claims,
    adapt_bridge_to_release_bundle,
    adapt_simulation_lineage,
)
from tools.research_cycle_bridge.builder import build_research_cycle_bridge
from tools.research_cycle_bridge.models import (
    BRIDGE_SCHEMA_VERSION,
    EVIDENCE_GRAPH_SCHEMA,
    BridgeContractError,
    BridgeDataMode,
    BridgeEvidenceClass,
    BridgeRecordStatus,
    EvidenceGraph,
    EvidenceGraphEdge,
    EvidenceGraphNode,
    ResearchCycleBridgeRecord,
    canonical_hash,
    dumps_finite,
    finite_value,
    verify_bridge_checksum,
)
from tools.research_cycle_bridge.validator import (
    BridgeValidationError,
    validate_bridge_record,
)

__all__ = [
    "BRIDGE_SCHEMA_VERSION",
    "EVIDENCE_GRAPH_SCHEMA",
    "BridgeContractError",
    "BridgeValidationError",
    "BridgeRecordStatus",
    "BridgeDataMode",
    "BridgeEvidenceClass",
    "EvidenceGraphNode",
    "EvidenceGraphEdge",
    "EvidenceGraph",
    "ResearchCycleBridgeRecord",
    "finite_value",
    "canonical_hash",
    "dumps_finite",
    "verify_bridge_checksum",
    "validate_bridge_record",
    "build_research_cycle_bridge",
    "adapt_simulation_lineage",
    "adapt_bridge_to_release_bundle",
    "adapt_bridge_to_claims",
]
