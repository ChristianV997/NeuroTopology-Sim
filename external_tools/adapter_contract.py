"""AdapterContractV1 -- the schema an adapter for an external tool must
satisfy before it is allowed to write into this repository's canonical
artifact schemas.

This is the bridge contract that lets an MNE/BIDS/fMRIPrep/MOABB (etc.)
adapter emit `DatasetRecordV1`/`ArtifactRecordV1`/`TransitionRecordV1`/
`PhaseSpaceCoordinateV1`/`EvidenceBundleV1`/`EvidenceReportV1` artifacts
without polluting any of those schemas with tool-specific fields, and
without silently exceeding the claim/evidence ceilings those schemas
already enforce. See docs/external_tool_integration_strategy.md.

The first real adapter satisfying this contract is `adapters.mne_bids`
(see docs/mne_bids_adapter.md); its own `AdapterContractV1` entry lives in
`external_tools/adapter_contracts_seed.json`, loaded via
`load_adapter_contracts()` below -- a separate file from
`external_tools/registry_seed.json` (which holds `ExternalToolRecordV1`
entries only), so that adding an adapter contract never requires touching
the already-committed, already-tested tool registry seed.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Union

from external_tools.validation import ExternalToolValidationError, validate_adapter_contract

_SCHEMA_VERSION = "1"

_DEFAULT_FORBIDDEN_OUTPUTS: tuple[str, ...] = (
    "clinical_claim",
    "diagnostic_claim",
    "treatment_claim",
    "consciousness_biomarker_claim",
    "spiritual_attainment_claim",
    "mechanistic_causal_claim",
)

_DEFAULT_VALIDATION_REQUIREMENTS: tuple[str, ...] = ("fail_closed_if_required_metadata_missing",)


def compute_adapter_id(*, tool_id: str, adapter_name: str) -> str:
    """Stable sha256[:16] over the adapter's identity fields.

    Mirrors `benchmarks.artifact_registry.compute_artifact_id`: excludes
    implementation_status, limitations, and all other mutable/free-text
    fields -- two contracts describing the same tool+adapter pairing
    always produce the same ID regardless of how their non-identity
    fields are later edited.
    """
    basis = {"tool_id": tool_id, "adapter_name": adapter_name}
    canonical = json.dumps(basis, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


@dataclass
class AdapterContractV1:
    schema_version: str = _SCHEMA_VERSION
    adapter_id: str = ""
    tool_id: str = ""
    adapter_name: str = ""
    integration_mode: str = ""
    input_artifact_kinds: list[str] = field(default_factory=list)
    output_artifact_kinds: list[str] = field(default_factory=list)
    output_targets: list[str] = field(default_factory=list)
    feature_namespaces: list[str] = field(default_factory=list)
    required_dependencies: list[str] = field(default_factory=list)
    optional_dependencies: list[str] = field(default_factory=list)
    license_constraints: list[str] = field(default_factory=list)
    provenance_requirements: list[str] = field(default_factory=lambda: list(("source_tool_version",)))
    validation_requirements: list[str] = field(default_factory=lambda: list(_DEFAULT_VALIDATION_REQUIREMENTS))
    forbidden_outputs: list[str] = field(default_factory=lambda: list(_DEFAULT_FORBIDDEN_OUTPUTS))
    allowed_claim_scope_ceiling: str = "exploratory_metric"
    evidence_level_ceiling: str = "L0_computational_artifact"
    implementation_status: str = "planned"
    limitations: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def make(cls, *, tool_id: str, adapter_name: str, **kwargs: Any) -> "AdapterContractV1":
        adapter_id = compute_adapter_id(tool_id=tool_id, adapter_name=adapter_name)
        return cls(adapter_id=adapter_id, tool_id=tool_id, adapter_name=adapter_name, **kwargs)

    def recompute_id(self) -> str:
        return compute_adapter_id(tool_id=self.tool_id, adapter_name=self.adapter_name)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "adapter_id": self.adapter_id,
            "tool_id": self.tool_id,
            "adapter_name": self.adapter_name,
            "integration_mode": self.integration_mode,
            "input_artifact_kinds": list(self.input_artifact_kinds),
            "output_artifact_kinds": list(self.output_artifact_kinds),
            "output_targets": list(self.output_targets),
            "feature_namespaces": list(self.feature_namespaces),
            "required_dependencies": list(self.required_dependencies),
            "optional_dependencies": list(self.optional_dependencies),
            "license_constraints": list(self.license_constraints),
            "provenance_requirements": list(self.provenance_requirements),
            "validation_requirements": list(self.validation_requirements),
            "forbidden_outputs": list(self.forbidden_outputs),
            "allowed_claim_scope_ceiling": self.allowed_claim_scope_ceiling,
            "evidence_level_ceiling": self.evidence_level_ceiling,
            "implementation_status": self.implementation_status,
            "limitations": list(self.limitations),
            "metadata": dict(self.metadata or {}),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AdapterContractV1":
        return cls(
            schema_version=d.get("schema_version", _SCHEMA_VERSION),
            adapter_id=d.get("adapter_id", ""),
            tool_id=d.get("tool_id", ""),
            adapter_name=d.get("adapter_name", ""),
            integration_mode=d.get("integration_mode", ""),
            input_artifact_kinds=list(d.get("input_artifact_kinds") or []),
            output_artifact_kinds=list(d.get("output_artifact_kinds") or []),
            output_targets=list(d.get("output_targets") or []),
            feature_namespaces=list(d.get("feature_namespaces") or []),
            required_dependencies=list(d.get("required_dependencies") or []),
            optional_dependencies=list(d.get("optional_dependencies") or []),
            license_constraints=list(d.get("license_constraints") or []),
            provenance_requirements=list(d.get("provenance_requirements") or []),
            validation_requirements=list(d.get("validation_requirements") or []),
            forbidden_outputs=list(d.get("forbidden_outputs") or []),
            allowed_claim_scope_ceiling=d.get("allowed_claim_scope_ceiling", "exploratory_metric"),
            evidence_level_ceiling=d.get("evidence_level_ceiling", "L0_computational_artifact"),
            implementation_status=d.get("implementation_status", "planned"),
            limitations=list(d.get("limitations") or []),
            metadata=dict(d.get("metadata") or {}),
        )

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=False)

    @classmethod
    def from_json(cls, text: str) -> "AdapterContractV1":
        return cls.from_dict(json.loads(text))

    def write_json(self, path: Union[str, Path]) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(self.to_json() + "\n", encoding="utf-8")
        return path

    def validate(self) -> list[str]:
        return validate_adapter_contract(self)

    def validate_or_raise(self) -> None:
        errors = self.validate()
        if errors:
            raise ExternalToolValidationError("; ".join(errors))


_ADAPTER_CONTRACTS_SCHEMA = "NeuroTopologySim.AdapterContractRegistry.v1"


class AdapterContractRegistryError(ValueError):
    """Raised for adapter-contracts-file-level problems (missing file, bad shape, ...)."""


def load_adapter_contracts(path: Union[str, Path]) -> dict[str, "AdapterContractV1"]:
    """Load `{adapter_id: AdapterContractV1}` from an adapter-contracts seed
    file (schema `NeuroTopologySim.AdapterContractRegistry.v1`), e.g.
    `external_tools/adapter_contracts_seed.json`. Deliberately not a method
    on `ExternalToolRegistry` -- adapter contracts are a distinct artifact
    kind stored in their own file, not merged into the tool registry.
    """
    path = Path(path)
    if not path.exists():
        raise AdapterContractRegistryError(f"adapter contracts file does not exist: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return {
        c["adapter_id"]: AdapterContractV1.from_dict(c) for c in data.get("adapter_contracts") or []
    }


def save_adapter_contracts(contracts: dict[str, "AdapterContractV1"], path: Union[str, Path]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": _ADAPTER_CONTRACTS_SCHEMA,
        "adapter_contracts": [contracts[k].to_dict() for k in sorted(contracts)],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    return path
