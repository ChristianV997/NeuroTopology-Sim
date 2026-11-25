"""Local-first dataset provenance contract.

Synthetic demonstrations, proxy files, and incomplete local recordings cannot
be treated as independently validated empirical evidence. This module never
downloads data, never opens sockets, and never mutates RunRecordV1.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping
import hashlib
import json
import math

SCHEMA = "NeuroTopologySim.DatasetProvenance.v1"
VALIDATOR_VERSION = "1.0.0"
ATTACHMENT_KEY = "dataset_provenance"
SUPPORTED_FORMATS = frozenset({".npy", ".npz"})
ORIGIN_LABELS = frozenset({
    "synthetic_demo",
    "empirical_local",
    "external_solver",
    "unavailable",
})
REQUIRED_METADATA_FIELDS = (
    "dataset_identifier",
    "condition_label",
    "subject_id",
    "session_id",
    "local_path",
    "file_format",
    "channel_count",
    "sample_count",
    "sampling_rate_hz",
    "units",
    "montage_source",
    "origin",
)
REQUIRED_UNITS = ("time", "sampling_frequency", "amplitude")
ALLOWED_STATUSES = frozenset({
    "PASS_SYNTHETIC",
    "PASS_EMPIRICAL_LOCAL",
    "PASS_EXTERNAL_SOLVER",
    "FAIL",
    "INCOMPLETE",
    "UNAVAILABLE",
})


class ProvenanceError(ValueError):
    """Malformed provenance input or JSON."""


@dataclass
class ProvenanceRecord:
    dataset_identifier: str | None
    condition_label: str | None
    subject_id: str | None
    session_id: str | None
    local_path: str | None
    file_checksum_sha256: str | None
    file_format: str | None
    channel_count: int | None
    sample_count: int | None
    sampling_rate_hz: float | None
    units: dict[str, str]
    montage_source: str | None
    montage_channels: list[str]
    acquisition_metadata: dict[str, Any]
    preprocessing_steps: list[str]
    filtering_bands_hz: dict[str, float | None]
    tda_configuration: dict[str, Any]
    source_url: str | None
    license: str | None
    access_metadata: dict[str, Any]
    origin: str
    acquisition_timestamp: str | None
    validator_version: str = VALIDATOR_VERSION
    validation_status: str = "INCOMPLETE"
    missing_fields: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    evidence_claim_allowed: bool = False
    observed_channel_count: int | None = None
    observed_sample_count: int | None = None
    data_finite: bool | None = None
    checksum_ok: bool | None = None
    schema: str = SCHEMA

    def to_dict(self) -> dict[str, Any]:
        return json_safe(
            {
                "schema": SCHEMA,
                "validator_version": self.validator_version,
                "dataset_identifier": _empty_to_null(self.dataset_identifier),
                "condition_label": _empty_to_null(self.condition_label),
                "subject_id": _empty_to_null(self.subject_id),
                "session_id": _empty_to_null(self.session_id),
                "local_path": _empty_to_null(self.local_path),
                "file_checksum_sha256": _empty_to_null(self.file_checksum_sha256),
                "file_format": _empty_to_null(self.file_format),
                "channel_count": self.channel_count,
                "sample_count": self.sample_count,
                "sampling_rate_hz": self.sampling_rate_hz,
                "units": dict(self.units),
                "montage_source": _empty_to_null(self.montage_source),
                "montage_channels": list(self.montage_channels),
                "acquisition_metadata": dict(self.acquisition_metadata),
                "preprocessing_steps": list(self.preprocessing_steps),
                "filtering_bands_hz": dict(self.filtering_bands_hz),
                "tda_configuration": dict(self.tda_configuration),
                "source_url": _empty_to_null(self.source_url),
                "license": _empty_to_null(self.license),
                "access_metadata": dict(self.access_metadata),
                "origin": self.origin,
                "acquisition_timestamp": _empty_to_null(self.acquisition_timestamp),
                "validation_status": self.validation_status,
                "missing_fields": list(self.missing_fields),
                "warnings": list(self.warnings),
                "evidence_claim_allowed": bool(self.evidence_claim_allowed),
                "observed_channel_count": self.observed_channel_count,
                "observed_sample_count": self.observed_sample_count,
                "data_finite": self.data_finite,
                "checksum_ok": self.checksum_ok,
            }
        )


def _empty_to_null(value: str | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def json_safe(value: Any, path: str = "$") -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ProvenanceError(f"{path} is not a finite JSON number")
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
    raise ProvenanceError(f"{path} is not JSON-serializable ({type(value).__name__})")


def serialize_record(record: ProvenanceRecord | Mapping[str, Any]) -> str:
    payload = record.to_dict() if isinstance(record, ProvenanceRecord) else json_safe(dict(record))
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(chunk_size)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _load_array(path: Path):
    import numpy as np

    suffix = path.suffix.lower()
    if suffix == ".npy":
        return np.load(path, mmap_mode="r")
    if suffix == ".npz":
        with np.load(path) as bundle:
            keys = list(bundle.files)
            if not keys:
                raise ProvenanceError("NPZ input contains no arrays")
            preferred = next((key for key in ("data", "signals", "recording") if key in bundle), keys[0])
            return np.asarray(bundle[preferred])
    raise ProvenanceError(f"unsupported local format {suffix}; convert offline to .npy/.npz")


def _missing(declaration: Mapping[str, Any]) -> list[str]:
    missing: list[str] = []
    for key in REQUIRED_METADATA_FIELDS:
        value = declaration.get(key)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(key)
    units = declaration.get("units") or {}
    if not isinstance(units, Mapping):
        missing.append("units")
    else:
        for key in REQUIRED_UNITS:
            if not units.get(key):
                missing.append(f"units.{key}")
    origin = declaration.get("origin")
    if origin not in ORIGIN_LABELS:
        missing.append("origin")
    return missing


def _declared_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number


def _declared_float(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def validate_declaration(declaration: Mapping[str, Any]) -> ProvenanceRecord:
    """Validate a local declaration. Never fetches source_url."""
    warnings: list[str] = []
    origin = str(declaration.get("origin") or "unavailable")
    if origin not in ORIGIN_LABELS:
        origin = "unavailable"
        warnings.append("origin is not a recognized label")
    if declaration.get("source_url"):
        warnings.append("source_url is metadata only; no download was attempted")

    local_path = _empty_to_null(declaration.get("local_path"))
    path = Path(local_path) if local_path else None
    missing = _missing(declaration)
    declared_format = _empty_to_null(declaration.get("file_format"))
    declared_checksum = _empty_to_null(declaration.get("file_checksum_sha256"))
    declared_channels = _declared_int(declaration.get("channel_count"))
    declared_samples = _declared_int(declaration.get("sample_count"))
    sampling_rate = _declared_float(declaration.get("sampling_rate_hz"))
    units = dict(declaration.get("units") or {})
    montage_channels = list(declaration.get("montage_channels") or [])
    filtering = dict(declaration.get("filtering_bands_hz") or {})
    tda_configuration = dict(declaration.get("tda_configuration") or {})

    record = ProvenanceRecord(
        dataset_identifier=_empty_to_null(declaration.get("dataset_identifier")),
        condition_label=_empty_to_null(declaration.get("condition_label")),
        subject_id=_empty_to_null(declaration.get("subject_id")),
        session_id=_empty_to_null(declaration.get("session_id")),
        local_path=str(path) if path is not None else None,
        file_checksum_sha256=declared_checksum,
        file_format=declared_format,
        channel_count=declared_channels,
        sample_count=declared_samples,
        sampling_rate_hz=sampling_rate,
        units=units,
        montage_source=_empty_to_null(declaration.get("montage_source")),
        montage_channels=[str(item) for item in montage_channels],
        acquisition_metadata=dict(declaration.get("acquisition_metadata") or {}),
        preprocessing_steps=[str(item) for item in declaration.get("preprocessing_steps") or []],
        filtering_bands_hz=filtering,
        tda_configuration=tda_configuration,
        source_url=_empty_to_null(declaration.get("source_url")),
        license=_empty_to_null(declaration.get("license")),
        access_metadata=dict(declaration.get("access_metadata") or {}),
        origin=origin,
        acquisition_timestamp=_empty_to_null(declaration.get("acquisition_timestamp")),
        missing_fields=missing,
        warnings=warnings,
    )

    if origin == "unavailable" or path is None:
        record.validation_status = "UNAVAILABLE"
        record.evidence_claim_allowed = False
        if "local_path" not in record.missing_fields:
            record.missing_fields.append("local_path")
        record.missing_fields = sorted(set(record.missing_fields))
        return record

    if not path.is_file():
        record.validation_status = "FAIL"
        record.warnings.append(f"local file is missing: {path}")
        record.evidence_claim_allowed = False
        return record

    suffix = path.suffix.lower()
    if declared_format and declared_format.lower() not in {suffix, suffix.lstrip(".")}:
        record.warnings.append("declared file_format does not match local suffix")
    if suffix not in SUPPORTED_FORMATS:
        record.validation_status = "FAIL"
        record.warnings.append(f"unsupported format {suffix}; offline conversion to .npy/.npz is required")
        record.evidence_claim_allowed = False
        return record
    record.file_format = suffix.lstrip(".")

    actual_checksum = sha256_file(path)
    if declared_checksum:
        record.checksum_ok = actual_checksum.lower() == declared_checksum.lower()
        if not record.checksum_ok:
            record.validation_status = "FAIL"
            record.warnings.append("SHA-256 checksum mismatch")
            record.file_checksum_sha256 = actual_checksum
            record.evidence_claim_allowed = False
            return record
    else:
        record.warnings.append("checksum was computed locally because none was declared")
    record.file_checksum_sha256 = actual_checksum
    record.checksum_ok = True if declared_checksum else None

    if sampling_rate is None or sampling_rate <= 0:
        record.validation_status = "FAIL"
        record.warnings.append("sampling_rate_hz must be a positive finite value")
        record.evidence_claim_allowed = False
        return record

    try:
        array = _load_array(path)
    except Exception as exc:
        record.validation_status = "FAIL"
        record.warnings.append(f"local array could not be read: {type(exc).__name__}: {exc}")
        record.evidence_claim_allowed = False
        return record

    import numpy as np

    if getattr(array, "ndim", None) != 2:
        record.validation_status = "FAIL"
        record.warnings.append(f"expected 2D (samples, channels); received shape {getattr(array, 'shape', None)}")
        record.evidence_claim_allowed = False
        return record

    observed_samples, observed_channels = (int(array.shape[0]), int(array.shape[1]))
    record.observed_sample_count = observed_samples
    record.observed_channel_count = observed_channels
    if declared_samples is not None and declared_samples != observed_samples:
        record.validation_status = "FAIL"
        record.warnings.append("declared sample_count does not match local array")
        record.evidence_claim_allowed = False
        return record
    if declared_channels is not None and declared_channels != observed_channels:
        record.validation_status = "FAIL"
        record.warnings.append("declared channel_count does not match local array")
        record.evidence_claim_allowed = False
        return record
    record.sample_count = observed_samples
    record.channel_count = observed_channels

    if observed_channels < 1 or observed_samples < 2:
        record.validation_status = "FAIL"
        record.warnings.append("channel_count must be >= 1 and sample_count must be >= 2")
        record.evidence_claim_allowed = False
        return record

    finite = bool(np.all(np.isfinite(np.asarray(array))))
    record.data_finite = finite
    if not finite:
        record.validation_status = "FAIL"
        record.warnings.append("recording contains NaN or Inf values")
        record.evidence_claim_allowed = False
        return record

    if not record.montage_source:
        record.missing_fields.append("montage_source")
    if record.montage_channels and len(record.montage_channels) != observed_channels:
        record.warnings.append("montage channel list length does not match observed channel_count")
        record.missing_fields.append("montage_channels")
    if not record.montage_channels:
        record.warnings.append("montage channel list is empty")
        record.missing_fields.append("montage_channels")

    record.missing_fields = sorted(set(record.missing_fields))
    record.missing_fields = [name for name in record.missing_fields if name != "file_checksum_sha256"]

    required_still_missing = [
        name for name in record.missing_fields
        if name in REQUIRED_METADATA_FIELDS or name.startswith("units.")
    ]
    incomplete_montage = "montage_source" in record.missing_fields or "montage_channels" in record.missing_fields

    if origin == "synthetic_demo":
        record.validation_status = "PASS_SYNTHETIC"
        record.evidence_claim_allowed = False
        record.warnings.append("synthetic_demo cannot support formal empirical evidence claims")
        return record
    if origin == "external_solver":
        record.validation_status = "PASS_EXTERNAL_SOLVER"
        record.evidence_claim_allowed = False
        record.warnings.append("external_solver output is not independently acquired empirical data")
        return record
    if origin != "empirical_local":
        record.validation_status = "UNAVAILABLE"
        record.evidence_claim_allowed = False
        return record
    if required_still_missing or incomplete_montage:
        record.validation_status = "INCOMPLETE"
        record.evidence_claim_allowed = False
        record.warnings.append("missing provenance blocks formal evidence claims")
        return record

    record.validation_status = "PASS_EMPIRICAL_LOCAL"
    record.evidence_claim_allowed = True
    return record


def attach_provenance(
    existing_sidecar: Mapping[str, Any] | None,
    record: ProvenanceRecord | Mapping[str, Any],
) -> dict[str, Any]:
    """Attach provenance beside a run without mutating RunRecordV1."""
    payload = dict(existing_sidecar or {})
    if "schema_version" in payload or "run_kind" in payload:
        raise ProvenanceError("refusing to write into a RunRecordV1-shaped mapping; use a sidecar")
    body = record.to_dict() if isinstance(record, ProvenanceRecord) else json_safe(dict(record))
    payload[ATTACHMENT_KEY] = body
    return json_safe(payload)


def write_sidecar(record: ProvenanceRecord, run_dir: str | Path) -> Path:
    directory = Path(run_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "dataset_provenance.json"
    path.write_text(serialize_record(record) + "\n", encoding="utf-8")
    return path


def consumer_view(record: ProvenanceRecord) -> dict[str, Any]:
    """Compact view for Bayesian falsification, topology, and reports."""
    return json_safe(
        {
            "schema": SCHEMA,
            "origin": record.origin,
            "validation_status": record.validation_status,
            "evidence_claim_allowed": record.evidence_claim_allowed,
            "dataset_identifier": record.dataset_identifier,
            "condition_label": record.condition_label,
            "subject_id": record.subject_id,
            "session_id": record.session_id,
            "sampling_rate_hz": record.sampling_rate_hz,
            "channel_count": record.channel_count,
            "sample_count": record.sample_count,
            "units": record.units,
            "filtering_bands_hz": record.filtering_bands_hz,
            "tda_configuration": record.tda_configuration,
            "warnings": record.warnings,
            "missing_fields": record.missing_fields,
        }
    )
