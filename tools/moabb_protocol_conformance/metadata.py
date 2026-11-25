"""Map candidate / fixture metadata into verified-vs-unknown fields.

Never invents sample counts, labels, licenses, participant counts, or
availability. Absent values stay unknown.
"""
from __future__ import annotations

import math
from typing import Any, Dict, List, Mapping, Optional

from tools.moabb_protocol_conformance.schema import MetadataTrust


def _as_optional_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"unknown", "none", "null"}:
        return None
    return text


def _as_optional_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    try:
        if isinstance(value, float) and (not math.isfinite(value) or not value.is_integer()):
            return None
        number = int(value)
    except (TypeError, ValueError):
        return None
    if number < 0:
        return None
    return number


def _trust(present: bool, *, conflicting: bool = False) -> str:
    if conflicting:
        return MetadataTrust.CONFLICTING.value
    return MetadataTrust.VERIFIED.value if present else MetadataTrust.UNKNOWN.value


def extract_dataset_fields(source: Mapping[str, Any]) -> Dict[str, Any]:
    """Normalize a DatasetCandidateRecordV1 dict or fixture entry."""
    metadata_issues: List[str] = []
    # Candidate record shape
    dataset_id = _as_optional_str(
        source.get("source_dataset_id") or source.get("code") or source.get("dataset_id")
    )
    task = None
    tasks = source.get("task_labels") or []
    if isinstance(tasks, list) and tasks:
        task = _as_optional_str(tasks[0])
    if task is None:
        task = _as_optional_str(source.get("paradigm") or source.get("task"))

    modalities = source.get("modalities")
    if not modalities:
        modality = _as_optional_str(source.get("modality"))
        modalities = [modality] if modality else []
    modalities = [str(m) for m in modalities if str(m).strip()]

    condition_labels = source.get("condition_labels") or []
    if not condition_labels and isinstance(source.get("event_id"), dict):
        condition_labels = sorted(str(k) for k in source["event_id"].keys())
    condition_labels = [str(c) for c in condition_labels if str(c).strip()]

    count_inputs = {
        "subject_count": source.get("subject_count"),
        "session_count": source.get("session_count") if source.get("session_count") is not None else source.get("n_sessions"),
        "channel_count": source.get("channel_count") if source.get("channel_count") is not None else source.get("n_channels"),
    }
    normalized_counts = {key: _as_optional_int(value) for key, value in count_inputs.items()}
    for key, value in count_inputs.items():
        if value is not None and normalized_counts[key] is None:
            metadata_issues.append(f"invalid_{key}")
    subject_count = normalized_counts["subject_count"]
    session_count = normalized_counts["session_count"]
    channel_count = normalized_counts["channel_count"]
    subject_ids = (
        source.get("subject_ids")
        if isinstance(source.get("subject_ids"), list)
        else None
    )
    if (
        subject_count is not None
        and subject_ids is not None
        and len(subject_ids) != subject_count
    ):
        metadata_issues.append("conflicting_subject_count")
    raw_channels = source.get("channels")
    supplied_channel_count = len(raw_channels) if isinstance(raw_channels, list) else None
    channels = raw_channels
    if channels is not None and not isinstance(channels, list):
        channels = None
    if isinstance(channels, list):
        channels = [str(c) for c in channels if str(c).strip()] or None
    if (
        channel_count is not None
        and supplied_channel_count is not None
        and (supplied_channel_count != channel_count or len(channels or []) != channel_count)
    ):
        metadata_issues.append("conflicting_channel_count")

    sampling_rate_hz = source.get("sampling_rate_hz")
    if sampling_rate_hz is not None:
        try:
            if isinstance(sampling_rate_hz, bool):
                raise ValueError("boolean is not a sampling rate")
            sampling_rate_hz = float(sampling_rate_hz)
            if not math.isfinite(sampling_rate_hz) or sampling_rate_hz <= 0:
                raise ValueError("sampling rate must be finite and positive")
        except (TypeError, ValueError):
            sampling_rate_hz = None
            metadata_issues.append("invalid_sampling_rate_hz")

    license_value = _as_optional_str(source.get("license")) or "unknown"
    access_status = _as_optional_str(source.get("access_status")) or "unknown"
    license_risk = _as_optional_str(source.get("license_risk")) or (
        "unknown_high" if license_value == "unknown" else None
    )

    # Conflicting: explicit "unknown" license_risk with a concrete license claim of proprietary, etc.
    license_conflict = False
    if license_value == "unknown" and license_risk not in (None, "unknown_high"):
        license_conflict = True
    if access_status == "unknown" and source.get("access_status_claimed_public") is True:
        license_conflict = True

    event_label_mapping_source = _as_optional_str(
        source.get("event_label_mapping_source")
        or (source.get("metadata") or {}).get("event_label_mapping_source")
    )
    if event_label_mapping_source is None and condition_labels:
        if isinstance(source.get("event_id"), dict):
            event_label_mapping_source = "fixture_or_candidate_event_id"
        elif source.get("condition_labels"):
            event_label_mapping_source = "fixture_or_candidate_condition_labels"

    # Availability is never invented: only record when explicitly supplied.
    local_availability = source.get("local_availability")
    if local_availability is not None:
        local_availability = _as_optional_str(local_availability) or "unknown"
    else:
        local_availability = "unknown"

    return {
        "dataset_identifier": {
            "value": dataset_id,
            "trust": _trust(dataset_id is not None),
        },
        "task": {"value": task, "trust": _trust(task is not None)},
        "modality": {
            "value": modalities[0] if modalities else None,
            "all": modalities,
            "trust": _trust(bool(modalities)),
        },
        "subjects": {
            "count": subject_count,
            "subject_ids": subject_ids,
            "trust": _trust(
                subject_count is not None or subject_ids is not None,
                conflicting="conflicting_subject_count" in metadata_issues,
            ),
        },
        "sessions": {
            "count": session_count,
            "trust": _trust(session_count is not None),
        },
        "channels": {
            "count": channel_count,
            "names": channels,
            "trust": _trust(
                channel_count is not None or channels is not None,
                conflicting="conflicting_channel_count" in metadata_issues,
            ),
        },
        "event_label_mapping": {
            "labels": condition_labels or None,
            "source": event_label_mapping_source,
            "trust": _trust(bool(condition_labels)),
        },
        "sampling": {
            "sampling_rate_hz": sampling_rate_hz,
            "trust": _trust(sampling_rate_hz is not None),
        },
        "license_access": {
            "license": license_value,
            "license_risk": license_risk or "unknown_high",
            "access_status": access_status,
            "trust": (
                MetadataTrust.CONFLICTING.value
                if license_conflict
                else _trust(license_value != "unknown" and access_status != "unknown")
            ),
        },
        "local_availability": {
            "value": local_availability,
            "trust": _trust(local_availability != "unknown"),
        },
        "candidate_id": _as_optional_str(source.get("candidate_id")),
        "source_catalog": _as_optional_str(source.get("source_catalog")) or "moabb",
        "provenance": _as_optional_str(source.get("provenance")),
        "metadata_issues": metadata_issues,
    }


def reject_fabricated_counts(protocol_fields: Mapping[str, Any]) -> List[str]:
    """Return violation codes when callers try to invent counts/labels."""
    violations: List[str] = []
    invented = protocol_fields.get("invented_fields") or protocol_fields.get("fabricated")
    if invented:
        violations.append("fabricated_metadata_flag")
    # Hard reject known fabrication markers
    for key in ("fabricated_subject_count", "fabricated_sample_count", "fabricated_labels"):
        if protocol_fields.get(key):
            violations.append(key)
    sample_count = protocol_fields.get("sample_count")
    if sample_count is not None and protocol_fields.get("sample_count_source") in (None, "", "invented"):
        violations.append("sample_count_without_source")
    return violations
