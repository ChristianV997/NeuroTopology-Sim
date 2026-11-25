"""Research Cycle Contract Compatibility Layer.

Provides typed schemas, bidirectional adapters, validation policies,
and deterministic serialization between the hypothesis registry,
Awareness Studio research-cycle orchestrator, and experiment ledgers.
"""
from __future__ import annotations

from .adapters import (
    awareness_node_to_hypothesis,
    cycle_input_to_registry_bundle,
    hypothesis_to_awareness_node,
    ledger_row_to_evidence,
    plan_and_evidence_to_ledger_row,
    registry_bundle_to_cycle_input,
)
from .models import (
    AwarenessHypothesisNodeV1,
    AwarenessStudioCycleInputV1,
    EvidenceUpdateV1,
    ExperimentLedgerRowV1,
    ExperimentPlanV1,
    HypothesisRecordV1,
    MigrationWarning,
    PredictionRecordV1,
    RejectionReasonCode,
    SupportedFeatureFamily,
)
from .rejection import (
    ContractCompatibilityError,
    ContractRejectionError,
    validate_evidence_contract,
    validate_hypothesis_contract,
    validate_ledger_row_contract,
)
from .serialization import (
    compute_checksum,
    load_contract_json,
    save_contract_json,
    to_canonical_json,
    verify_checksum,
)
from .version_negotiator import (
    get_supported_schema_versions,
    negotiate_contract_version,
)

__all__ = [
    "HypothesisRecordV1",
    "ExperimentPlanV1",
    "PredictionRecordV1",
    "EvidenceUpdateV1",
    "AwarenessHypothesisNodeV1",
    "AwarenessStudioCycleInputV1",
    "ExperimentLedgerRowV1",
    "MigrationWarning",
    "RejectionReasonCode",
    "SupportedFeatureFamily",
    "ContractCompatibilityError",
    "ContractRejectionError",
    "validate_hypothesis_contract",
    "validate_evidence_contract",
    "validate_ledger_row_contract",
    "hypothesis_to_awareness_node",
    "awareness_node_to_hypothesis",
    "plan_and_evidence_to_ledger_row",
    "ledger_row_to_evidence",
    "registry_bundle_to_cycle_input",
    "cycle_input_to_registry_bundle",
    "negotiate_contract_version",
    "get_supported_schema_versions",
    "compute_checksum",
    "verify_checksum",
    "to_canonical_json",
    "save_contract_json",
    "load_contract_json",
]
