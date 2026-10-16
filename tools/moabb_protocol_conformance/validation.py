"""Validate protocol manifests for offline conformance only."""
from __future__ import annotations

from typing import Any, Dict, List, Mapping

from tools.moabb_protocol_conformance.leakage import assess_subject_leakage
from tools.moabb_protocol_conformance.metadata import reject_fabricated_counts
from tools.moabb_protocol_conformance.schema import (
    EVALUATION_METRICS,
    FORBIDDEN_CLAIM_PHRASES,
    KNOWN_SPLIT_POLICIES,
    UNITS_OF_ANALYSIS,
    ConformanceStatus,
    MetadataTrust,
)


def _scan_forbidden(blob: str) -> List[str]:
    lowered = blob.lower()
    return [f"forbidden_claim:{phrase}" for phrase in FORBIDDEN_CLAIM_PHRASES if phrase in lowered]


def validate_protocol_manifest(manifest: Mapping[str, Any]) -> Dict[str, Any]:
    """Return conformance verdict without claiming scientific validity."""
    violations: List[str] = []
    warnings: List[str] = []

    if manifest.get("schema_version") != "NeuroTopology.MoabbProtocolManifest.v1":
        violations.append("schema_mismatch")
    if manifest.get("evidence_class") != "protocol_conformance_only":
        violations.append("evidence_class_mismatch")
    if manifest.get("benchmark_executed") is True:
        violations.append("benchmark_executed_claim")
    if manifest.get("scientific_validation_claimed") is True:
        violations.append("scientific_validation_claimed")
    if manifest.get("local_data_available") is True and (
        (manifest.get("dataset") or {}).get("local_availability") or {}
    ).get("trust") != MetadataTrust.VERIFIED.value:
        violations.append("local_availability_fabricated")

    protocol = manifest.get("protocol") or {}
    unit = protocol.get("unit_of_analysis")
    if unit not in UNITS_OF_ANALYSIS:
        violations.append("missing_or_invalid_unit_of_analysis")
    split_policy = protocol.get("split_policy")
    if split_policy not in KNOWN_SPLIT_POLICIES:
        violations.append("missing_or_invalid_split_policy")
    metric = protocol.get("evaluation_metric")
    if metric not in EVALUATION_METRICS or metric == "unspecified":
        violations.append("missing_or_invalid_evaluation_metric")
    if "exclusions" not in protocol:
        violations.append("exclusions_not_declared")
    elif not isinstance(protocol.get("exclusions"), list):
        violations.append("exclusions_must_be_list")

    dataset = manifest.get("dataset") or {}
    if not (dataset.get("dataset_identifier") or {}).get("value"):
        violations.append("missing_dataset_identifier")

    license_block = dataset.get("license_access") or {}
    if license_block.get("trust") == MetadataTrust.CONFLICTING.value:
        violations.append("conflicting_license_or_access_metadata")
    if license_block.get("license") == "unknown":
        warnings.append("license_unknown")
    if license_block.get("access_status") == "unknown":
        warnings.append("access_status_unknown")

    event = dataset.get("event_label_mapping") or {}
    if event.get("trust") == MetadataTrust.UNKNOWN.value:
        warnings.append("event_labels_unknown")
    if protocol.get("requires_labels") and not (event.get("labels") or []):
        violations.append("absent_labels_required_by_protocol")

    violations.extend(reject_fabricated_counts(protocol))

    leakage = assess_subject_leakage(
        split_policy=str(split_policy or "unspecified"),
        train_subject_ids=protocol.get("train_subject_ids"),
        test_subject_ids=protocol.get("test_subject_ids"),
        unit_of_analysis=unit,
    )
    if leakage["status"] == "failed":
        violations.append("subject_leakage")
        violations.extend(f"leakage:{item}" for item in leakage["findings"])
    elif leakage["status"] == "incomplete":
        violations.append("incomplete_split_declaration")
        violations.extend(f"leakage:{item}" for item in leakage["findings"])
    elif leakage["status"] == "inconclusive":
        warnings.append("leakage_inconclusive")
        warnings.extend(f"leakage:{item}" for item in leakage["findings"])

    claims_blob = " ".join(
        [
            str(manifest.get("notes") or ""),
            str(protocol.get("notes") or ""),
            str(manifest.get("result_summary") or ""),
        ]
    )
    violations.extend(_scan_forbidden(claims_blob))

    if any(v.startswith("subject_leakage") or v == "subject_leakage" for v in violations):
        status = ConformanceStatus.FAILED.value
    elif any(v.startswith("conflicting_") for v in violations) or "local_availability_fabricated" in violations:
        status = ConformanceStatus.BLOCKED.value
    elif violations:
        status = ConformanceStatus.INCOMPLETE.value
    elif warnings and any(w.startswith("leakage_inconclusive") for w in warnings):
        status = ConformanceStatus.INCONCLUSIVE.value
    else:
        status = ConformanceStatus.CONFORMING.value

    return {
        "ok": status == ConformanceStatus.CONFORMING.value,
        "status": status,
        "violations": violations,
        "warnings": warnings,
        "leakage": leakage,
        "claims": {
            "benchmark_executed": False,
            "local_data_available_asserted": False,
            "scientific_validation_claimed": False,
            "result_is": "protocol_described_conformance_only",
        },
    }
