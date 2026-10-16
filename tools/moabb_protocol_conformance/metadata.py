"""Map candidate / fixture metadata into verified-vs-unknown fields.

Never invents sample counts, labels, licenses, participant counts, or
availability. Absent values stay unknown.
"""
from __future__ import annotations

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

    subject_count = _as_optional_int(source.get("subject_count"))
    session_count = _as_optional_int(source.get("session_count") or source.get("n_sessions"))
    channel_count = _as_optional_int(source.get("channel_count") or source.get("n_channels"))
    channels = source.get("channels")
    if channels is not None and not isinstance(channels, list):
        channels = None
    if isinstance(channels, list):
        channels = [str(c) for c in channels if str(c).strip()] or None

    sampling_rate_hz = source.get("sampling_rate_hz")
    if sampling_rate_hz is not None:
        try:
            sampling_rate_hz = float(sampling_rate_hz)
            if sampling_rate_hz != sampling_rate_hz or sampling_rate_hz <= 0:
                sampling_rate_hz = None
        except (TypeError, ValueError):
            sampling_rate_hz = None

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
            "subject_ids": source.get("subject_ids") if isinstance(source.get("subject_ids"), list) else None,
            "trust": _trust(subject_count is not None or isinstance(source.get("subject_ids"), list)),
        },
        "sessions": {
            "count": session_count,
            "trust": _trust(session_count is not None),
        },
        "channels": {
            "count": channel_count,
            "names": channels,
            "trust": _trust(channel_count is not None or channels is not None),
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
