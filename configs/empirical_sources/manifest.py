"""Preregistered empirical-source manifest.

This module freezes operator-supplied identity, labels, exclusions, and
planned statistical outcomes. It does not download data, infer condition
labels, compute statistics, or treat a complete manifest as evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
import json
import math

SCHEMA = "NeuroTopologySim.EmpiricalSourceManifest.v1"
VALIDATOR_VERSION = "1.0.0"
STATES = frozenset({
    "VALID_PREREGISTRATION",
    "INCOMPLETE_PREREGISTRATION",
    "AMBIGUOUS_CONDITIONS",
    "INVALID_PROVENANCE",
    "SYNTHETIC_DEMO_ONLY",
    "UNAVAILABLE_SOURCE",
})
ORIGIN_LABELS = frozenset({
    "empirical_local",
    "synthetic_demo",
    "external_solver",
    "unavailable",
})
REQUIRED_FIELDS = (
    "dataset_identifier",
    "source_url",
    "local_root",
    "subject_identifiers",
    "condition_labels",
    "pairing_key",
    "expected_sampling_rate_hz",
    "channel_count_range",
    "montage_requirement",
    "minimum_paired_subject_count",
    "exclusion_rules",
    "primary_outcome_metrics",
    "secondary_outcomes",
    "null_models",
    "multiplicity_correction",
    "stopping_rule",
    "missing_data_rule",
    "synthetic_data_policy",
    "provenance_requirements",
)


class ManifestError(ValueError):
    """Malformed empirical-source manifest."""


@dataclass
class ManifestReport:
    status: str
    reasons: list[str]
    missing_fields: list[str]
    dataset_identifier: str | None
    origin: str
    n_subjects: int
    n_condition_labels: int
    pairing_key: str | None
    schema: str = SCHEMA
    validator_version: str = VALIDATOR_VERSION
    scientific_status: str = "preregistration_only"
    evidence_claim_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return json_safe(
            {
                "schema": SCHEMA,
                "validator_version": self.validator_version,
                "status": self.status,
                "reasons": list(self.reasons),
                "missing_fields": list(self.missing_fields),
                "dataset_identifier": self.dataset_identifier,
                "origin": self.origin,
                "n_subjects": self.n_subjects,
                "n_condition_labels": self.n_condition_labels,
                "pairing_key": self.pairing_key,
                "scientific_status": "preregistration_only",
                "evidence_claim_allowed": False,
                "statistics_computed": False,
                "data_downloaded": False,
            }
        )


def json_safe(value: Any, path: str = "$") -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ManifestError(f"{path} is not a finite JSON number")
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, list):
        return [json_safe(item, f"{path}[{index}]") for index, item in enumerate(value)]
    if isinstance(value, tuple):
        return [json_safe(item, f"{path}[{index}]") for index, item in enumerate(value)]
    if isinstance(value, Mapping):
        return {
            str(key): json_safe(item, f"{path}.{key}")
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    raise ManifestError(f"{path} is not JSON-serializable ({type(value).__name__})")


def serialize_report(report: ManifestReport) -> str:
    return json.dumps(report.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _finite(name: str, value: Any) -> float | None:
    if value is None or value == "":
        return None
    number = float(value)
    if not math.isfinite(number):
        raise ManifestError(f"{name} must be a finite number")
    return number


def _load_document(source: Mapping[str, Any] | str | Path) -> dict[str, Any]:
    if isinstance(source, Mapping):
        return dict(source)
    path = Path(source)
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml
        except ImportError as exc:
            raise ManifestError("pyyaml is required to load YAML manifests") from exc
        raw = yaml.safe_load(text)
    else:
        raw = json.loads(text)
    if not isinstance(raw, Mapping):
        raise ManifestError("manifest root must be a mapping")
    return dict(raw)


def _range_ok(name: str, value: Any) -> bool:
    if not isinstance(value, Mapping):
        return False
    minimum = _finite(f"{name}.min", value.get("min"))
    maximum = _finite(f"{name}.max", value.get("max"))
    if minimum is None or maximum is None:
        return False
    return minimum > 0 and maximum >= minimum


def validate_manifest(source: Mapping[str, Any] | str | Path) -> ManifestReport:
    """Validate a preregistration manifest. Never downloads or analyzes data."""
    document = _load_document(source)
    reasons: list[str] = []
    missing = [key for key in REQUIRED_FIELDS if key not in document or document.get(key) in (None, "", [], {})]
    dataset_id = _text(document.get("dataset_identifier"))
    source_url = _text(document.get("source_url"))
    local_root = _text(document.get("local_root"))
    origin = _text(document.get("origin")) or "unavailable"
    if origin not in ORIGIN_LABELS:
        reasons.append(f"origin {origin!r} is not recognized")
        origin = "unavailable"

    subjects = [_text(item) for item in _as_list(document.get("subject_identifiers"))]
    subjects = [item for item in subjects if item]
    labels = [_text(item) for item in _as_list(document.get("condition_labels"))]
    labels = [item for item in labels if item]
    pairing_key = _text(document.get("pairing_key"))
    inferred = document.get("inferred_condition_mapping")
    filename_rules = document.get("filename_condition_rules")
    synthetic_policy = document.get("synthetic_data_policy")
    if isinstance(synthetic_policy, Mapping):
        policy_text = _text(synthetic_policy.get("policy")) or ""
        treat_as_empirical = bool(synthetic_policy.get("treat_as_empirical"))
    else:
        policy_text = _text(synthetic_policy) or ""
        treat_as_empirical = False

    if inferred or filename_rules:
        reasons.append("condition labels must be operator-supplied; filename inference is rejected")
    if len(set(labels)) < 2 and labels:
        reasons.append("fewer than two explicit condition labels")

    rate_ok = _range_ok("expected_sampling_rate_hz", document.get("expected_sampling_rate_hz"))
    if document.get("expected_sampling_rate_hz") is not None and not rate_ok:
        reasons.append("sample-rate constraints are unknown or invalid")
    if document.get("channel_count_range") is not None and not _range_ok("channel_count_range", document.get("channel_count_range")):
        reasons.append("channel-count range is unknown or invalid")

    min_pairs = document.get("minimum_paired_subject_count")
    pairs_value = _finite("minimum_paired_subject_count", min_pairs) if min_pairs not in (None, "") else None
    if pairs_value is not None and pairs_value < 1:
        reasons.append("minimum_paired_subject_count must be >= 1")

    if treat_as_empirical:
        reasons.append("synthetic data marked empirical")

    unavailable = origin == "unavailable" or (not dataset_id and not source_url and not local_root)
    synthetic_origin = origin == "synthetic_demo" or policy_text.lower() in {"synthetic_only", "demo_only"}

    status = "VALID_PREREGISTRATION"
    if unavailable:
        status = "UNAVAILABLE_SOURCE"
        reasons.append("source identity is unavailable")
    elif synthetic_origin:
        status = "SYNTHETIC_DEMO_ONLY"
        reasons.append("synthetic or demo source cannot be an empirical preregistration PASS")
    elif treat_as_empirical:
        status = "INVALID_PROVENANCE"
    elif inferred or filename_rules or (not labels or len(set(labels)) < 2):
        status = "AMBIGUOUS_CONDITIONS"
        if not labels:
            reasons.append("condition labels are missing or ambiguous")
    elif not rate_ok:
        status = "INVALID_PROVENANCE"
        reasons.append("sample-rate constraints are unspecified")
    elif missing or not pairing_key or not subjects:
        status = "INCOMPLETE_PREREGISTRATION"
        if not pairing_key:
            reasons.append("pairing key is missing")
        if not subjects:
            reasons.append("subject identifiers are missing")
        if "exclusion_rules" in missing:
            reasons.append("exclusion rules are unspecified")
        if "multiplicity_correction" in missing:
            reasons.append("multiplicity correction is missing")
        if "missing_data_rule" in missing:
            reasons.append("missing-data policy is unstated")
    elif not _text(document.get("multiplicity_correction")):
        status = "INCOMPLETE_PREREGISTRATION"
        reasons.append("multiplicity correction is missing")

    if status == "VALID_PREREGISTRATION":
        reasons.append("manifest is a preregistration artifact, not empirical evidence")

    return ManifestReport(
        status=status,
        reasons=list(dict.fromkeys(reasons)),
        missing_fields=missing,
        dataset_identifier=dataset_id,
        origin=origin,
        n_subjects=len(subjects),
        n_condition_labels=len(set(labels)),
        pairing_key=pairing_key,
    )
