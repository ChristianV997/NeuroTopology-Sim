"""Strict, serializable contracts at the signal/adaptor boundary.

The contracts deliberately contain no imports of MNE, SciPy, LSL, BrainFlow,
NWB, or other optional packages.  NumPy is imported only when a signal array
is validated.  Raw arrays are never embedded in canonical metadata JSON;
callers must store them separately and pass a binary reference to
``serialize_signal_chunk``.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import math
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Any, Mapping, Sequence


class InteropValidationError(ValueError):
    """Raised when an interoperability object violates its contract."""


class QualityStatus(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"
    ERROR = "ERROR"


class AdapterStatus(str, Enum):
    INTEGRATED = "integrated"
    EMULATE = "emulate"
    REFERENCE = "reference"
    UNAVAILABLE = "unavailable"


def _numpy() -> Any:
    """Load NumPy at point of use, with an actionable error if absent."""
    try:
        import numpy as np
    except ImportError as exc:  # pragma: no cover - exercised in minimal envs
        raise InteropValidationError(
            "NumPy is required to validate SignalChunk arrays"
        ) from exc
    return np


def _require_text(value: Any, field_name: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value.strip()):
        raise InteropValidationError(f"{field_name} must be a non-empty string")
    return value


def _validate_sha256(value: str | None, field_name: str) -> str | None:
    if value is None or value == "":
        return value
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-fA-F]{64}", value) is None:
        raise InteropValidationError(f"{field_name} must be a 64-character SHA-256 hex digest")
    return value.lower()


def normalize_relative_path(value: str | Path, field_name: str = "path") -> str:
    """Return a canonical POSIX relative path, rejecting traversal/absolutes."""
    if isinstance(value, Path):
        raw = value.as_posix()
    elif isinstance(value, str):
        raw = value.replace("\\", "/")
    else:
        raise InteropValidationError(f"{field_name} must be a path string")
    if not raw or "\x00" in raw:
        raise InteropValidationError(f"{field_name} must be a non-empty relative path")
    if raw.startswith("/") or raw.startswith("//") or re.match(r"^[A-Za-z]:", raw):
        raise InteropValidationError(f"{field_name} must be relative, got {value!r}")
    parts = [part for part in PurePosixPath(raw).parts if part not in ("", ".")]
    if not parts or any(part == ".." for part in parts):
        raise InteropValidationError(f"{field_name} must not contain parent traversal")
    return "/".join(parts)


def json_safe(value: Any) -> Any:
    """Convert metadata values to strict JSON values without swallowing arrays."""
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("non-finite floats are not JSON-safe")
        return value
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return value.as_posix()
    if dataclasses.is_dataclass(value):
        return json_safe(dataclasses.asdict(value))
    if isinstance(value, Mapping):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(item) for item in value]
    # Import NumPy only when a caller actually gives us a NumPy value.
    try:
        np = _numpy()
    except InteropValidationError:
        np = None
    if np is not None:
        if isinstance(value, np.ndarray):
            raise TypeError("binary NumPy arrays require a separate array reference")
        if isinstance(value, np.generic):
            return json_safe(value.item())
    raise TypeError(f"value of type {type(value).__name__} is not JSON-safe")


def canonical_json(value: Any) -> str:
    """Serialize metadata deterministically and reject non-finite values."""
    return json.dumps(
        json_safe(value),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def sha256_file(path: str | Path, *, chunk_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(chunk_size), b""):
            digest.update(block)
    return digest.hexdigest()


def stable_hash(value: Any) -> str:
    return sha256_text(canonical_json(value))


def stable_id(value: Any, *, prefix: str = "", length: int = 16) -> str:
    if length <= 0 or length > 64:
        raise ValueError("length must be between 1 and 64")
    return f"{prefix}{stable_hash(value)[:length]}"


def _normalise_names(names: Sequence[str], field_name: str, expected: int) -> tuple[str, ...]:
    values = tuple(names)
    if len(values) != expected:
        raise InteropValidationError(
            f"{field_name} length {len(values)} does not match channel count {expected}"
        )
    if any(not isinstance(name, str) or not name.strip() for name in values):
        raise InteropValidationError(f"{field_name} must contain non-empty strings")
    return values


def _normalise_units(units: str | Sequence[str], channels: int) -> tuple[str, ...]:
    if isinstance(units, str):
        values = (units,) * channels
    else:
        values = tuple(units)
    return _normalise_names(values, "units", channels)


@dataclass
class SignalChunk:
    """A chunk of raw or preprocessed signal in ``(channels, samples)`` order."""

    data: Any
    timestamps: Any
    sample_rate_hz: float
    channel_names: Sequence[str]
    units: str | Sequence[str]
    source_id: str
    recording_id: str
    chunk_index: int
    start_sample: int
    source_sha256: str | None = None
    montage_name: str = ""
    montage_coordinates: Any | None = None
    dropped_samples: int = 0
    warnings: Sequence[str] = field(default_factory=tuple)
    allow_duplicate_channels: bool = False

    def __post_init__(self) -> None:
        np = _numpy()
        data = np.asarray(self.data)
        timestamps = np.asarray(self.timestamps)
        if data.ndim != 2:
            raise InteropValidationError("data must have shape (channels, samples); no transpose is implied")
        if timestamps.ndim != 1:
            raise InteropValidationError("timestamps must have shape (samples,)")
        channels, samples = data.shape
        if channels <= 0 or samples <= 0:
            raise InteropValidationError("data must contain at least one channel and one sample")
        if timestamps.shape != (samples,):
            raise InteropValidationError(
                f"timestamps shape {timestamps.shape} does not match sample count {samples}"
            )
        try:
            if not bool(np.all(np.isfinite(data))):
                raise InteropValidationError("data must contain only finite values")
            if not bool(np.all(np.isfinite(timestamps))):
                raise InteropValidationError("timestamps must contain only finite values")
        except TypeError as exc:
            raise InteropValidationError("data and timestamps must be numeric arrays") from exc
        try:
            sample_rate = float(self.sample_rate_hz)
        except (TypeError, ValueError) as exc:
            raise InteropValidationError("sample_rate_hz must be a finite positive number") from exc
        if not math.isfinite(sample_rate) or sample_rate <= 0:
            raise InteropValidationError("sample_rate_hz must be a finite positive number")
        if samples > 1 and not bool(np.all(np.diff(timestamps) > 0)):
            raise InteropValidationError("timestamps must be strictly increasing")
        names = _normalise_names(self.channel_names, "channel_names", channels)
        if not self.allow_duplicate_channels and len(set(names)) != len(names):
            raise InteropValidationError("channel_names must be unique unless explicitly allowed")
        units = _normalise_units(self.units, channels)
        _require_text(self.source_id, "source_id")
        _require_text(self.recording_id, "recording_id")
        _require_text(self.montage_name, "montage_name", allow_empty=True)
        _validate_sha256(self.source_sha256, "source_sha256")
        if not isinstance(self.chunk_index, int) or isinstance(self.chunk_index, bool) or self.chunk_index < 0:
            raise InteropValidationError("chunk_index must be a non-negative integer")
        if not isinstance(self.start_sample, int) or isinstance(self.start_sample, bool) or self.start_sample < 0:
            raise InteropValidationError("start_sample must be a non-negative integer")
        if not isinstance(self.dropped_samples, int) or isinstance(self.dropped_samples, bool) or self.dropped_samples < 0:
            raise InteropValidationError("dropped_samples must be a non-negative integer")
        warnings = tuple(self.warnings)
        if any(not isinstance(item, str) for item in warnings):
            raise InteropValidationError("warnings must contain strings")
        coordinates = None if self.montage_coordinates is None else np.asarray(self.montage_coordinates)
        if coordinates is not None:
            if coordinates.shape != (channels, 3):
                raise InteropValidationError(
                    f"montage_coordinates must have shape ({channels}, 3); no transpose is implied"
                )
            try:
                if not bool(np.all(np.isfinite(coordinates))):
                    raise InteropValidationError("montage_coordinates must contain only finite values")
            except TypeError as exc:
                raise InteropValidationError("montage_coordinates must be numeric") from exc
        self.data = data
        self.timestamps = timestamps
        self.sample_rate_hz = sample_rate
        self.channel_names = names
        self.units = units
        self.source_sha256 = _validate_sha256(self.source_sha256, "source_sha256")
        self.warnings = warnings
        self.montage_coordinates = coordinates

    @property
    def shape(self) -> tuple[int, int]:
        return tuple(self.data.shape)

    def to_metadata_dict(self, *, array_reference: Mapping[str, Any] | None = None) -> dict[str, Any]:
        metadata: dict[str, Any] = {
            "schema_version": "signal_chunk_v1",
            "shape": list(self.shape),
            "sample_rate_hz": self.sample_rate_hz,
            "channel_names": list(self.channel_names),
            "units": list(self.units),
            "source_id": self.source_id,
            "recording_id": self.recording_id,
            "chunk_index": self.chunk_index,
            "start_sample": self.start_sample,
            "source_sha256": self.source_sha256,
            "montage_name": self.montage_name,
            "montage_coordinates": None if self.montage_coordinates is None else self.montage_coordinates.tolist(),
            "dropped_samples": self.dropped_samples,
            "warnings": list(self.warnings),
            "timestamps": self.timestamps.tolist(),
        }
        if array_reference is not None:
            metadata["array_reference"] = json_safe(array_reference)
        return metadata

    def to_dict(self, *, include_data: bool = False, array_reference: Mapping[str, Any] | None = None) -> dict[str, Any]:
        payload = self.to_metadata_dict(array_reference=array_reference)
        if include_data:
            payload["data"] = self.data.tolist()
        return payload

    @property
    def stable_id(self) -> str:
        return stable_id(self.to_metadata_dict(), prefix="chunk-")


@dataclass
class RecordingManifest:
    """Metadata and provenance for one recording; no raw samples are embedded."""

    dataset_id: str
    recording_id: str
    source_path: str | Path
    source_sha256: str | None
    file_format: str
    channel_count: int
    sample_rate_hz: float
    duration_s: float | None
    channel_names: Sequence[str]
    units: str | Sequence[str]
    montage_metadata: Mapping[str, Any] = field(default_factory=dict)
    preprocessing_history: Sequence[Any] = field(default_factory=tuple)
    data_mode: str = "unknown"
    provenance_status: str = "unknown"
    software_versions: Mapping[str, str] = field(default_factory=dict)
    warnings: Sequence[str] = field(default_factory=tuple)
    errors: Sequence[str] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        self.dataset_id = _require_text(self.dataset_id, "dataset_id")
        self.recording_id = _require_text(self.recording_id, "recording_id")
        self.source_path = normalize_relative_path(self.source_path, "source_path")
        self.source_sha256 = _validate_sha256(self.source_sha256, "source_sha256")
        self.file_format = _require_text(self.file_format, "file_format")
        if not isinstance(self.channel_count, int) or isinstance(self.channel_count, bool) or self.channel_count <= 0:
            raise InteropValidationError("channel_count must be a positive integer")
        try:
            self.sample_rate_hz = float(self.sample_rate_hz)
        except (TypeError, ValueError) as exc:
            raise InteropValidationError("sample_rate_hz must be a finite positive number") from exc
        if not math.isfinite(self.sample_rate_hz) or self.sample_rate_hz <= 0:
            raise InteropValidationError("sample_rate_hz must be a finite positive number")
        if self.duration_s is not None:
            try:
                self.duration_s = float(self.duration_s)
            except (TypeError, ValueError) as exc:
                raise InteropValidationError("duration_s must be finite and non-negative") from exc
            if not math.isfinite(self.duration_s) or self.duration_s < 0:
                raise InteropValidationError("duration_s must be finite and non-negative")
        self.channel_names = _normalise_names(self.channel_names, "channel_names", self.channel_count)
        if len(set(self.channel_names)) != len(self.channel_names):
            raise InteropValidationError("channel_names must be unique")
        self.units = _normalise_units(self.units, self.channel_count)
        self.data_mode = _require_text(self.data_mode, "data_mode")
        self.provenance_status = _require_text(self.provenance_status, "provenance_status")
        self.montage_metadata = json_safe(dict(self.montage_metadata))
        self.preprocessing_history = tuple(self.preprocessing_history)
        self.software_versions = {str(k): _require_text(v, f"software_versions[{k!r}]") for k, v in self.software_versions.items()}
        self.warnings = tuple(self.warnings)
        self.errors = tuple(self.errors)
        if any(not isinstance(item, str) for item in (*self.warnings, *self.errors)):
            raise InteropValidationError("warnings and errors must contain strings")

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "recording_manifest_v1",
            "dataset_id": self.dataset_id,
            "recording_id": self.recording_id,
            "source_path": self.source_path,
            "source_sha256": self.source_sha256,
            "file_format": self.file_format,
            "channel_count": self.channel_count,
            "sample_rate_hz": self.sample_rate_hz,
            "duration_s": self.duration_s,
            "channel_names": list(self.channel_names),
            "units": list(self.units),
            "montage_metadata": self.montage_metadata,
            "preprocessing_history": list(self.preprocessing_history),
            "data_mode": self.data_mode,
            "provenance_status": self.provenance_status,
            "software_versions": self.software_versions,
            "warnings": list(self.warnings),
            "errors": list(self.errors),
        }


@dataclass
class AdapterCapability:
    adapter_name: str
    supported_formats: Sequence[str] = field(default_factory=tuple)
    dependency: str = ""
    availability: bool = False
    streaming_support: bool = False
    montage_support: bool = False
    write_support: bool = False
    network_requirement: str = "none"
    status: AdapterStatus | str = AdapterStatus.UNAVAILABLE

    def __post_init__(self) -> None:
        _require_text(self.adapter_name, "adapter_name")
        self.supported_formats = tuple(_require_text(item, "supported_formats item") for item in self.supported_formats)
        self.dependency = _require_text(self.dependency, "dependency", allow_empty=True)
        self.network_requirement = _require_text(self.network_requirement, "network_requirement")
        try:
            self.status = AdapterStatus(self.status)
        except ValueError as exc:
            raise InteropValidationError(f"unknown adapter status: {self.status!r}") from exc
        if not isinstance(self.availability, bool):
            raise InteropValidationError("availability must be boolean")
        if self.status is AdapterStatus.UNAVAILABLE and self.availability:
            raise InteropValidationError("unavailable adapters cannot report availability=true")
        if self.availability and self.status is AdapterStatus.UNAVAILABLE:
            raise InteropValidationError("available adapters need an integrated, emulate, or reference status")

    def to_dict(self) -> dict[str, Any]:
        return {
            "adapter_name": self.adapter_name,
            "supported_formats": list(self.supported_formats),
            "dependency": self.dependency,
            "availability": self.availability,
            "streaming_support": self.streaming_support,
            "montage_support": self.montage_support,
            "write_support": self.write_support,
            "network_requirement": self.network_requirement,
            "status": self.status.value,
        }


@dataclass
class QualityReport:
    """Explicit quality outcome; it never infers a scientific result from metadata."""

    status: QualityStatus | str
    checks: Mapping[str, Any] = field(default_factory=dict)
    errors: Sequence[str] = field(default_factory=tuple)
    warnings: Sequence[str] = field(default_factory=tuple)
    metrics: Mapping[str, Any] = field(default_factory=dict)
    provenance: Mapping[str, Any] = field(default_factory=dict)
    artifact_paths: Sequence[str | Path] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        try:
            status_value = self.status.value if isinstance(self.status, QualityStatus) else str(self.status).upper()
            self.status = QualityStatus(status_value)
        except ValueError as exc:
            raise InteropValidationError(f"unknown quality status: {self.status!r}") from exc
        self.checks = dict(self.checks)
        self.metrics = dict(self.metrics)
        self.provenance = dict(self.provenance)
        self.errors = tuple(self.errors)
        self.warnings = tuple(self.warnings)
        if any(not isinstance(item, str) for item in (*self.errors, *self.warnings)):
            raise InteropValidationError("errors and warnings must contain strings")
        self.artifact_paths = tuple(normalize_relative_path(path, "artifact_paths item") for path in self.artifact_paths)
        # The global K guardrail is checked when a report carries K evidence;
        # generic adapter quality reports remain independent of scientific claims.
        if self.status is QualityStatus.PASS and "K" in self.metrics:
            try:
                k_value = float(self.metrics["K"])
            except (TypeError, ValueError) as exc:
                raise InteropValidationError("K must be a finite number") from exc
            if not math.isfinite(k_value) or k_value <= 100:
                raise InteropValidationError("PASS requires K > 100")

    @classmethod
    def from_run_record(cls, record: Any) -> "QualityReport":
        """Map a canonical RunRecordV1 to quality metadata without replacing it."""
        payload = record.to_dict() if hasattr(record, "to_dict") else dict(record)
        raw_status = payload.get("verdict")
        errors: list[str] = []
        if raw_status is None:
            status = QualityStatus.INCONCLUSIVE
            errors.append("RunRecordV1 has no verdict")
        else:
            try:
                status = QualityStatus(str(raw_status).upper())
            except ValueError:
                status = QualityStatus.ERROR
                errors.append(f"Unsupported RunRecordV1 verdict: {raw_status!r}")
        artifacts = payload.get("artifacts") or {}
        artifact_paths = tuple(artifacts.values()) if isinstance(artifacts, Mapping) else tuple(artifacts)
        provenance = {
            "source": payload.get("source"),
            "schema_version": payload.get("schema_version"),
            "run_id": payload.get("run_id"),
            "dataset_id": payload.get("dataset_id"),
            "data_mode": payload.get("data_mode"),
            "claim_type": payload.get("claim_type"),
            "layer": payload.get("layer"),
        }
        return cls(
            status=status,
            checks={"run_record_v1": True},
            errors=errors,
            metrics=payload.get("metrics") or {},
            provenance=provenance,
            artifact_paths=artifact_paths,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "quality_report_v1",
            "status": self.status.value,
            "checks": self.checks,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "metrics": self.metrics,
            "provenance": self.provenance,
            "artifact_paths": list(self.artifact_paths),
        }


def serialize_signal_chunk(
    chunk: SignalChunk, *, array_reference: Mapping[str, Any] | None = None
) -> str:
    """Serialize chunk metadata and an optional external binary-array reference."""
    return canonical_json(chunk.to_metadata_dict(array_reference=array_reference))


__all__ = [
    "AdapterCapability",
    "AdapterStatus",
    "InteropValidationError",
    "QualityReport",
    "QualityStatus",
    "RecordingManifest",
    "SignalChunk",
    "canonical_json",
    "json_safe",
    "normalize_relative_path",
    "serialize_signal_chunk",
    "sha256_bytes",
    "sha256_file",
    "sha256_text",
    "stable_hash",
    "stable_id",
]
