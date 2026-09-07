"""Canonical sorting, null-safe serialization, and deterministic checksumming for feature contracts."""
from __future__ import annotations

import hashlib
import json
from typing import Any, Sequence

from .models import (
    CanonicalFeatureBundle,
    CanonicalFeatureRecord,
    _safe_dict,
)
from .validators import validate_feature_bundle, validate_feature_record


def canonical_sort_key(rec: CanonicalFeatureRecord) -> tuple[Any, ...]:
    """Provides a deterministic canonical sorting key for feature records."""
    sub = rec.subject or ""
    ses = rec.session or ""
    run = rec.run or ""
    cond = rec.condition_label or ""
    fam = rec.feature_family
    name = rec.feature_name
    t_start = rec.time_window.get("start_s", 0.0) if rec.time_window else 0.0
    f_low = rec.frequency_band.get("low_hz", 0.0) if rec.frequency_band else 0.0
    return (sub, ses, run, cond, fam, name, t_start, f_low)


def canonical_sort_records(records: Sequence[CanonicalFeatureRecord]) -> list[CanonicalFeatureRecord]:
    """Returns a new list of feature records sorted by canonical hierarchy."""
    return sorted(records, key=canonical_sort_key)


def compute_record_checksum(record: CanonicalFeatureRecord) -> str:
    """Computes a deterministic SHA-256 checksum over the canonicalized JSON record."""
    d = record.to_dict()
    d["checksum"] = ""
    safe_data = _safe_dict(d)
    canonical_bytes = json.dumps(safe_data, indent=2, sort_keys=True, allow_nan=False).encode("utf-8")
    return hashlib.sha256(canonical_bytes).hexdigest()


def compute_bundle_checksum(bundle: CanonicalFeatureBundle) -> str:
    """Computes a deterministic SHA-256 checksum over the canonicalized JSON bundle."""
    d = bundle.to_dict()
    d["bundle_checksum"] = ""
    # Ensure records within bundle are canonically sorted
    sorted_records = sorted(d.get("records", []), key=lambda r: (
        r.get("subject") or "",
        r.get("session") or "",
        r.get("run") or "",
        r.get("condition_label") or "",
        r.get("feature_family", ""),
        r.get("feature_name", ""),
        (r.get("time_window") or {}).get("start_s", 0.0),
        (r.get("frequency_band") or {}).get("low_hz", 0.0),
    ))
    d["records"] = sorted_records
    safe_data = _safe_dict(d)
    canonical_bytes = json.dumps(safe_data, indent=2, sort_keys=True, allow_nan=False).encode("utf-8")
    return hashlib.sha256(canonical_bytes).hexdigest()


def record_to_json(record: CanonicalFeatureRecord, *, validate: bool = True) -> str:
    """Serializes a feature record to canonical, null-safe JSON string."""
    if validate:
        validate_feature_record(record)
    checksum = compute_record_checksum(record)
    record.checksum = checksum
    d = record.to_dict()
    return json.dumps(d, indent=2, sort_keys=True, allow_nan=False) + "\n"


def bundle_to_json(bundle: CanonicalFeatureBundle, *, validate: bool = True) -> str:
    """Serializes a feature bundle to canonical, null-safe JSON string."""
    # Ensure records are sorted and carry individual checksums
    bundle.records = canonical_sort_records(bundle.records)
    for r in bundle.records:
        r.checksum = compute_record_checksum(r)
    if validate:
        validate_feature_bundle(bundle)
    checksum = compute_bundle_checksum(bundle)
    bundle.bundle_checksum = checksum
    d = bundle.to_dict()
    return json.dumps(d, indent=2, sort_keys=True, allow_nan=False) + "\n"


def record_from_dict(data: dict[str, Any], *, validate: bool = True) -> CanonicalFeatureRecord:
    """Instantiates and optionally validates a CanonicalFeatureRecord from a dictionary."""
    rec = CanonicalFeatureRecord(
        schema_version=data.get("schema_version", "NeuroTopologySim.CanonicalFeatureRecord.v1"),
        feature_family=data["feature_family"],
        feature_name=data["feature_name"],
        mathematical_definition=data["mathematical_definition"],
        units=data["units"],
        frequency_band=data.get("frequency_band"),
        time_window=data.get("time_window"),
        sampling_rate_hz=data.get("sampling_rate_hz"),
        channel_node_identity=list(data.get("channel_node_identity", [])),
        coordinate_status=data.get("coordinate_status", "missing"),
        montage_coordinates=data.get("montage_coordinates"),
        subject=data.get("subject"),
        session=data.get("session"),
        run=data.get("run"),
        condition_label=data.get("condition_label"),
        provenance_checksum=data.get("provenance_checksum", ""),
        preprocessing=list(data.get("preprocessing", [])),
        missingness=data.get("missingness"),
        uncertainty=data.get("uncertainty"),
        is_synthetic=bool(data.get("is_synthetic", False)),
        evidence_class=data.get("evidence_class", "empirical_feature"),
        axes=list(data.get("axes", [])),
        shape=list(data.get("shape", [])),
        values=data.get("values"),
        checksum=data.get("checksum", ""),
    )
    if validate:
        validate_feature_record(rec)
    return rec


def bundle_from_dict(data: dict[str, Any], *, validate: bool = True) -> CanonicalFeatureBundle:
    """Instantiates and optionally validates a CanonicalFeatureBundle from a dictionary."""
    records = [record_from_dict(r, validate=validate) for r in data.get("records", [])]
    bundle = CanonicalFeatureBundle(
        schema_version=data.get("schema_version", "NeuroTopologySim.CanonicalFeatureBundle.v1"),
        bundle_id=data["bundle_id"],
        subject=data.get("subject"),
        session=data.get("session"),
        run=data.get("run"),
        condition_label=data.get("condition_label"),
        is_synthetic=bool(data.get("is_synthetic", False)),
        provenance_checksum=data.get("provenance_checksum", ""),
        bundle_checksum=data.get("bundle_checksum", ""),
        records=records,
    )
    if validate:
        validate_feature_bundle(bundle)
    return bundle


def record_from_json(json_str: str, *, validate: bool = True) -> CanonicalFeatureRecord:
    """Parses and validates a CanonicalFeatureRecord from a JSON string."""
    data = json.loads(json_str)
    return record_from_dict(data, validate=validate)


def bundle_from_json(json_str: str, *, validate: bool = True) -> CanonicalFeatureBundle:
    """Parses and validates a CanonicalFeatureBundle from a JSON string."""
    data = json.loads(json_str)
    return bundle_from_dict(data, validate=validate)
