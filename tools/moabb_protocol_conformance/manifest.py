"""Build transparent MOABB benchmark-protocol manifests from metadata."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Mapping, Optional, Sequence

from dataset_importers.candidate_record import DatasetCandidateRecordV1

from tools.moabb_protocol_conformance.metadata import extract_dataset_fields
from tools.moabb_protocol_conformance.schema import (
    EVIDENCE_CLASS,
    PROTOCOL_SCHEMA_VERSION,
    PROVENANCE_LABEL,
)
from tools.moabb_protocol_conformance.serialization import dumps, json_safe, sha256_hex
from tools.moabb_protocol_conformance.validation import validate_protocol_manifest
from tools.moabb_protocol_conformance.upstream import UPSTREAM_REFERENCES


@dataclass
class ProtocolManifestV1:
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return json_safe(self.payload)

    def to_json(self, *, indent: Optional[int] = 2) -> str:
        return dumps(self.payload, indent=indent)

    @property
    def checksum_sha256(self) -> str:
        body = dict(self.payload)
        body.pop("manifest_checksum_sha256", None)
        return sha256_hex(body)


def _candidate_to_mapping(source: Mapping[str, Any] | DatasetCandidateRecordV1) -> Dict[str, Any]:
    if isinstance(source, DatasetCandidateRecordV1):
        return source.to_dict()
    return dict(source)


def build_protocol_manifest(
    source: Mapping[str, Any] | DatasetCandidateRecordV1,
    *,
    protocol_version: str,
    unit_of_analysis: str,
    split_policy: str,
    evaluation_metric: str,
    exclusions: Optional[Sequence[str]] = None,
    train_subject_ids: Optional[Sequence[str]] = None,
    test_subject_ids: Optional[Sequence[str]] = None,
    requires_labels: bool = True,
    notes: str = "",
    created_at: Optional[str] = None,
    protocol_extras: Optional[Mapping[str, Any]] = None,
) -> ProtocolManifestV1:
    """Compose a protocol manifest and attach a conformance verdict."""
    if exclusions is None:
        # Callers must pass exclusions explicitly (including []) to satisfy the contract.
        raise ValueError("exclusions must be explicitly provided (use [] if none)")

    candidate = _candidate_to_mapping(source)
    dataset_fields = extract_dataset_fields(candidate)
    ts = created_at or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    protocol = {
        "protocol_version": str(protocol_version).strip(),
        "unit_of_analysis": unit_of_analysis,
        "split_policy": split_policy,
        "evaluation_metric": evaluation_metric,
        "exclusions": list(exclusions),
        "train_subject_ids": list(train_subject_ids) if train_subject_ids is not None else None,
        "test_subject_ids": list(test_subject_ids) if test_subject_ids is not None else None,
        "requires_labels": bool(requires_labels),
        "notes": notes,
    }
    # Optional negative-test / audit markers (never invent values here).
    if protocol_extras:
        for key in (
            "sample_count",
            "sample_count_source",
            "invented_fields",
            "fabricated",
            "fabricated_subject_count",
            "fabricated_sample_count",
            "fabricated_labels",
        ):
            if key in protocol_extras:
                protocol[key] = protocol_extras[key]

    payload: Dict[str, Any] = {
        "schema_version": PROTOCOL_SCHEMA_VERSION,
        "evidence_class": EVIDENCE_CLASS,
        "provenance_label": PROVENANCE_LABEL,
        "created_at": ts,
        "benchmark_executed": False,
        "scientific_validation_claimed": False,
        "local_data_available": False,
        "network_accessed": False,
        "dataset": dataset_fields,
        "protocol": protocol,
        "upstream_references": UPSTREAM_REFERENCES,
        "compatibility": {
            "candidate_record_schema": "DatasetCandidateRecordV1",
            "source_catalog": dataset_fields.get("source_catalog"),
            "candidate_id": dataset_fields.get("candidate_id"),
            "moabb_importer": "dataset_importers.moabb_importer (read-only consumer)",
        },
        "notes": (
            "Protocol-described / conformance-only. No benchmark execution claim, "
            "no local-data-presence claim, and no scientific-validation claim."
        ),
    }

    # Checksum over payload without conformance (stable content hash of description).
    content_for_checksum = dict(payload)
    payload["manifest_checksum_sha256"] = sha256_hex(content_for_checksum)

    conformance = validate_protocol_manifest(payload)
    payload["conformance"] = conformance
    payload["result_summary"] = {
        "status": conformance["status"],
        "ok": conformance["ok"],
        "result_is": "protocol_described_conformance_only",
    }
    return ProtocolManifestV1(payload=json_safe(payload))


def build_from_candidate_dict(
    candidate: Mapping[str, Any],
    protocol_fields: Mapping[str, Any],
) -> ProtocolManifestV1:
    """Convenience wrapper used by CLI/tests."""
    extras = {
        key: protocol_fields[key]
        for key in (
            "sample_count",
            "sample_count_source",
            "invented_fields",
            "fabricated",
            "fabricated_subject_count",
            "fabricated_sample_count",
            "fabricated_labels",
        )
        if key in protocol_fields
    }
    return build_protocol_manifest(
        candidate,
        protocol_version=str(protocol_fields["protocol_version"]),
        unit_of_analysis=str(protocol_fields["unit_of_analysis"]),
        split_policy=str(protocol_fields["split_policy"]),
        evaluation_metric=str(protocol_fields["evaluation_metric"]),
        exclusions=list(protocol_fields["exclusions"]),
        train_subject_ids=protocol_fields.get("train_subject_ids"),
        test_subject_ids=protocol_fields.get("test_subject_ids"),
        requires_labels=bool(protocol_fields.get("requires_labels", True)),
        notes=str(protocol_fields.get("notes") or ""),
        created_at=protocol_fields.get("created_at"),
        protocol_extras=extras or None,
    )
