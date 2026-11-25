"""Provenance-aware recording-quality gate for local EEG/MEG containers.

Scientific guardrails:
- Header validation is not independent empirical validation.
- Synthetic data is never empirical evidence.
- No clinical claims.
- No label inference: never infer awake, sedated, meditation, or task states
  from filenames or directory structures.
- Strict memory boundedness: inspect only headers and bounded sample chunks;
  never preload entire high-density recordings into memory.
"""
from __future__ import annotations

import datetime
from enum import Enum
import hashlib
import importlib.util
import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Sequence
import numpy as np


class RecordingQualityState(str, Enum):
    """Explicit recording quality and capability states."""
    VALIDATED_EMPIRICAL_LOCAL = "VALIDATED_EMPIRICAL_LOCAL"
    VALIDATED_SYNTHETIC_ONLY = "VALIDATED_SYNTHETIC_ONLY"
    INCOMPLETE_METADATA = "INCOMPLETE_METADATA"
    INVALID_RECORDING = "INVALID_RECORDING"
    MISSING_OPTIONAL_DEPENDENCY = "MISSING_OPTIONAL_DEPENDENCY"
    UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
    UNAVAILABLE_FILE = "UNAVAILABLE_FILE"


class QualityIssue(str, Enum):
    """Catalog of known quality validation failure causes."""
    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    UNSUPPORTED_EXTENSION = "UNSUPPORTED_EXTENSION"
    CORRUPTED_FILE = "CORRUPTED_FILE"
    NON_FINITE_SAMPLE_VALUES = "NON_FINITE_SAMPLE_VALUES"
    DUPLICATE_CHANNEL_NAMES = "DUPLICATE_CHANNEL_NAMES"
    ZERO_CHANNELS = "ZERO_CHANNELS"
    INVALID_SAMPLING_FREQUENCY = "INVALID_SAMPLING_FREQUENCY"
    INVALID_DURATION = "INVALID_DURATION"
    MISSING_COMPANION_FILE = "MISSING_COMPANION_FILE"
    MISSING_MANDATORY_METADATA = "MISSING_MANDATORY_METADATA"
    MISSING_DEPENDENCY = "MISSING_DEPENDENCY"


SUPPORTED_FORMATS: dict[str, str] = {
    ".fif": "FIF",
    ".fif.gz": "FIF_GZ",
    ".edf": "EDF",
    ".bdf": "BDF",
    ".vhdr": "BRAINVISION",
    ".vmrk": "BRAINVISION_MARKER",
    ".eeg": "BRAINVISION_DATA",
}

SYNTHETIC_KEYWORDS = (
    "synthetic",
    "simulated",
    "mock",
    "demo_fixture",
    "test_fixture",
    "dummy",
    "phantom",
)


@dataclass
class InspectionLimits:
    """Explicit inspection constraints preserving bounded memory footprint."""
    max_bounded_samples: int
    inspected_samples: int
    preload: bool = False


@dataclass
class MontageCoverage:
    """Montage electrode coordinate coverage metrics."""
    montage_available: bool
    total_channels: int
    channels_with_coordinates: int
    coverage_ratio: float | None
    coordinate_frame: str | None


@dataclass
class ProvenanceInfo:
    """Provenance origin, SHA-256 digest, and verification context."""
    origin_path: str
    sha256: str | None
    provenance_hint: str
    is_synthetic: bool
    supplied_labels: dict[str, str] = field(default_factory=dict)


@dataclass
class CompanionFileInfo:
    """Companion file metadata for multipart formats such as BrainVision."""
    role: str
    filename: str
    resolved_path: str | None
    exists: bool
    sha256: str | None


@dataclass
class RecordingMetadata:
    """Extracted physical and topological channel metadata."""
    source_format: str
    sampling_rate_hz: float | None
    channel_count: int | None
    channel_names: list[str]
    duration_s: float | None
    bad_channels: list[str]
    montage: MontageCoverage | None
    companion_files: list[CompanionFileInfo] = field(default_factory=list)


@dataclass
class RecordingQualityReport:
    """Structured, provenance-aware recording quality report with null-safe JSON guarantees."""
    schema_version: str = "v1.0.0"
    target_path: str = ""
    quality_state: str = RecordingQualityState.UNAVAILABLE_FILE.value
    passed_validation: bool = False
    is_synthetic: bool = False
    issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: RecordingMetadata | None = None
    provenance: ProvenanceInfo | None = None
    inspection_limits: InspectionLimits | None = None
    missing_dependencies: list[str] = field(default_factory=list)
    report_timestamp_utc: str = ""
    report_checksum_sha256: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Convert report to sanitized dictionary rejecting NaN and Inf."""
        def _sanitize(val: Any) -> Any:
            if isinstance(val, (str, int, bool)):
                return val
            if val is None:
                return None
            if isinstance(val, float):
                if math.isnan(val) or math.isinf(val):
                    raise ValueError(f"Non-compliant float encountered in report: {val}")
                return val
            if isinstance(val, Enum):
                return val.value
            if isinstance(val, (list, tuple)):
                return [_sanitize(x) for x in val]
            if isinstance(val, dict):
                return {str(k): _sanitize(v) for k, v in val.items()}
            if hasattr(val, "__dataclass_fields__"):
                return {k: _sanitize(getattr(val, k)) for k in val.__dataclass_fields__}
            return str(val)

        return _sanitize(self)

    def to_json(self, indent: int = 2) -> str:
        """Produce deterministic, null-safe JSON with sha256 checksum."""
        d = self.to_dict()
        # Compute deterministic checksum without checksum field
        d_for_hash = dict(d)
        d_for_hash["report_checksum_sha256"] = ""
        canonical_bytes = json.dumps(
            d_for_hash,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
            ensure_ascii=True,
        ).encode("utf-8")
        checksum = hashlib.sha256(canonical_bytes).hexdigest()
        d["report_checksum_sha256"] = checksum
        self.report_checksum_sha256 = checksum
        return json.dumps(d, indent=indent, sort_keys=True, allow_nan=False)


def compute_file_sha256(path: Path) -> str:
    """Compute SHA-256 digest of a file in 1MB chunks."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify_report_checksum(report_dict: dict[str, Any]) -> bool:
    """Verify integrity of a serialized RecordingQualityReport dictionary."""
    reported = report_dict.get("report_checksum_sha256", "")
    if not reported:
        return False
    d = dict(report_dict)
    d["report_checksum_sha256"] = ""
    canonical_bytes = json.dumps(
        d,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        ensure_ascii=True,
    ).encode("utf-8")
    expected = hashlib.sha256(canonical_bytes).hexdigest()
    return reported == expected


def _detect_synthetic_markers(path: Path, raw_obj: Any = None) -> bool:
    """Detect synthetic or demonstration signatures in path, info, or annotations."""
    path_str = str(path).lower()
    for kw in SYNTHETIC_KEYWORDS:
        if kw in path_str:
            return True

    if raw_obj is not None:
        # Check annotations if present
        try:
            annotations = getattr(raw_obj, "annotations", None)
            if annotations is not None:
                descriptions = getattr(annotations, "description", [])
                for desc in descriptions:
                    desc_str = str(desc).lower()
                    for kw in SYNTHETIC_KEYWORDS:
                        if kw in desc_str:
                            return True
        except Exception:
            pass

        # Check description in info
        try:
            info = getattr(raw_obj, "info", {})
            description = info.get("description", "")
            if description:
                desc_str = str(description).lower()
                for kw in SYNTHETIC_KEYWORDS:
                    if kw in desc_str:
                        return True
        except Exception:
            pass

    return False


def _parse_brainvision_header(vhdr_path: Path) -> tuple[str | None, str | None, float | None, int | None, list[str]]:
    """Lightweight text parser for BrainVision .vhdr files without loading data."""
    data_file: str | None = None
    marker_file: str | None = None
    sampling_interval_us: float | None = None
    n_channels: int | None = None
    channel_names: list[str] = []

    current_section = ""
    with vhdr_path.open("r", encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith(";"):
                continue
            if line.startswith("[") and line.endswith("]"):
                current_section = line[1:-1].strip().lower()
                continue

            if "=" in line:
                key, val = line.split("=", 1)
                key = key.strip()
                val = val.strip()

                if current_section == "common infos":
                    k_lower = key.lower()
                    if k_lower == "datafile":
                        data_file = val
                    elif k_lower == "markerfile":
                        marker_file = val
                    elif k_lower == "samplinginterval":
                        try:
                            sampling_interval_us = float(val)
                        except ValueError:
                            pass
                    elif k_lower == "numberofchannels":
                        try:
                            n_channels = int(val)
                        except ValueError:
                            pass

                elif current_section == "channel infos":
                    if key.lower().startswith("ch"):
                        # Format: Ch1=name,ref,res,unit
                        parts = val.split(",")
                        ch_name = parts[0].strip() if parts else key
                        channel_names.append(ch_name)

    sfreq = (1e6 / sampling_interval_us) if sampling_interval_us and sampling_interval_us > 0 else None
    return data_file, marker_file, sfreq, n_channels, channel_names


def inspect_recording_quality(
    target_path: str | Path,
    *,
    provenance_hint: str = "auto",
    bounded_samples: int = 512,
    supplied_labels: dict[str, str] | None = None,
    mne_override: Any | None = None,
) -> RecordingQualityReport:
    """Evaluate recording quality for a local EEG/MEG container under strict memory bounds.

    Parameters:
        target_path: Path to target recording file or BIDS directory container.
        provenance_hint: One of 'auto', 'empirical', 'synthetic'.
        bounded_samples: Maximum number of sample frames to inspect for finiteness.
        supplied_labels: Explicit operator or manifest labels. Labels are never
                         inferred from filenames or paths.
        mne_override: Optional MNE module injection for testing dependency handling.
    """
    timestamp_utc = datetime.datetime.now(datetime.timezone.utc).isoformat()
    path = Path(target_path)

    # Strictly preserve supplied labels; never infer awake/sedated/meditation/task
    preserved_labels = dict(supplied_labels) if supplied_labels is not None else {}

    # File existence check
    if not path.exists():
        return RecordingQualityReport(
            target_path=str(path),
            quality_state=RecordingQualityState.UNAVAILABLE_FILE.value,
            passed_validation=False,
            is_synthetic=False,
            issues=[f"{QualityIssue.FILE_NOT_FOUND.value}: Path does not exist: {path}"],
            provenance=ProvenanceInfo(
                origin_path=str(path),
                sha256=None,
                provenance_hint=provenance_hint,
                is_synthetic=False,
                supplied_labels=preserved_labels,
            ),
            inspection_limits=InspectionLimits(max_bounded_samples=bounded_samples, inspected_samples=0),
            report_timestamp_utc=timestamp_utc,
        )

    # Container vs Single File dispatch
    if path.is_dir():
        return _inspect_bids_container(
            path,
            provenance_hint=provenance_hint,
            bounded_samples=bounded_samples,
            supplied_labels=preserved_labels,
            timestamp_utc=timestamp_utc,
            mne_override=mne_override,
        )

    # Format recognition
    ext = path.suffix.lower()
    full_name_lower = path.name.lower()
    if full_name_lower.endswith(".fif.gz"):
        ext = ".fif.gz"

    if ext not in SUPPORTED_FORMATS:
        return RecordingQualityReport(
            target_path=str(path),
            quality_state=RecordingQualityState.UNSUPPORTED_FORMAT.value,
            passed_validation=False,
            is_synthetic=False,
            issues=[f"{QualityIssue.UNSUPPORTED_EXTENSION.value}: Extension '{ext}' is not supported."],
            provenance=ProvenanceInfo(
                origin_path=str(path),
                sha256=compute_file_sha256(path),
                provenance_hint=provenance_hint,
                is_synthetic=False,
                supplied_labels=preserved_labels,
            ),
            inspection_limits=InspectionLimits(max_bounded_samples=bounded_samples, inspected_samples=0),
            report_timestamp_utc=timestamp_utc,
        )

    # Redirect .vmrk or .eeg to companion .vhdr if found
    if ext in (".vmrk", ".eeg"):
        vhdr_candidate = path.with_suffix(".vhdr")
        if vhdr_candidate.is_file():
            path = vhdr_candidate
            ext = ".vhdr"
        else:
            return RecordingQualityReport(
                target_path=str(path),
                quality_state=RecordingQualityState.INVALID_RECORDING.value,
                passed_validation=False,
                is_synthetic=False,
                issues=[f"{QualityIssue.MISSING_COMPANION_FILE.value}: BrainVision companion header {vhdr_candidate.name} not found."],
                provenance=ProvenanceInfo(
                    origin_path=str(path),
                    sha256=compute_file_sha256(path),
                    provenance_hint=provenance_hint,
                    is_synthetic=False,
                    supplied_labels=preserved_labels,
                ),
                inspection_limits=InspectionLimits(max_bounded_samples=bounded_samples, inspected_samples=0),
                report_timestamp_utc=timestamp_utc,
            )

    # Resolve MNE module
    mne = mne_override
    if mne is None:
        if importlib.util.find_spec("mne") is not None:
            import mne as mne_mod
            mne = mne_mod

    if ext == ".vhdr":
        return _inspect_brainvision(
            path,
            provenance_hint=provenance_hint,
            bounded_samples=bounded_samples,
            supplied_labels=preserved_labels,
            timestamp_utc=timestamp_utc,
            mne=mne,
        )
    elif ext in (".edf", ".bdf"):
        return _inspect_edf_bdf(
            path,
            ext=ext,
            provenance_hint=provenance_hint,
            bounded_samples=bounded_samples,
            supplied_labels=preserved_labels,
            timestamp_utc=timestamp_utc,
            mne=mne,
        )
    elif ext in (".fif", ".fif.gz"):
        return _inspect_fif(
            path,
            provenance_hint=provenance_hint,
            bounded_samples=bounded_samples,
            supplied_labels=preserved_labels,
            timestamp_utc=timestamp_utc,
            mne=mne,
        )
    else:
        return RecordingQualityReport(
            target_path=str(path),
            quality_state=RecordingQualityState.UNSUPPORTED_FORMAT.value,
            passed_validation=False,
            is_synthetic=False,
            issues=[f"{QualityIssue.UNSUPPORTED_EXTENSION.value}: Unhandled extension '{ext}'."],
            provenance=ProvenanceInfo(
                origin_path=str(path),
                sha256=compute_file_sha256(path),
                provenance_hint=provenance_hint,
                is_synthetic=False,
                supplied_labels=preserved_labels,
            ),
            inspection_limits=InspectionLimits(max_bounded_samples=bounded_samples, inspected_samples=0),
            report_timestamp_utc=timestamp_utc,
        )


def _inspect_brainvision(
    path: Path,
    *,
    provenance_hint: str,
    bounded_samples: int,
    supplied_labels: dict[str, str],
    timestamp_utc: str,
    mne: Any | None,
) -> RecordingQualityReport:
    """Memory-bounded inspection for BrainVision triplet (.vhdr, .vmrk, .eeg)."""
    file_sha256 = compute_file_sha256(path)
    issues: list[str] = []
    warnings: list[str] = []
    companion_infos: list[CompanionFileInfo] = []

    # Parse header text
    try:
        data_fname, marker_fname, sfreq_hdr, n_chan_hdr, ch_names_hdr = _parse_brainvision_header(path)
    except Exception as exc:
        return RecordingQualityReport(
            target_path=str(path),
            quality_state=RecordingQualityState.INVALID_RECORDING.value,
            passed_validation=False,
            is_synthetic=False,
            issues=[f"{QualityIssue.CORRUPTED_FILE.value}: Failed to parse .vhdr header: {exc}"],
            provenance=ProvenanceInfo(
                origin_path=str(path),
                sha256=file_sha256,
                provenance_hint=provenance_hint,
                is_synthetic=False,
                supplied_labels=supplied_labels,
            ),
            inspection_limits=InspectionLimits(max_bounded_samples=bounded_samples, inspected_samples=0),
            report_timestamp_utc=timestamp_utc,
        )

    # Check companion data file
    data_path: Path | None = None
    if data_fname:
        candidate_data = path.parent / data_fname
        data_exists = candidate_data.is_file()
        d_sha = compute_file_sha256(candidate_data) if data_exists else None
        companion_infos.append(
            CompanionFileInfo(
                role="data",
                filename=data_fname,
                resolved_path=str(candidate_data) if data_exists else None,
                exists=data_exists,
                sha256=d_sha,
            )
        )
        if not data_exists:
            issues.append(f"{QualityIssue.MISSING_COMPANION_FILE.value}: DataFile '{data_fname}' referenced in header does not exist.")
        else:
            data_path = candidate_data
    else:
        issues.append(f"{QualityIssue.MISSING_MANDATORY_METADATA.value}: No DataFile entry specified in .vhdr header.")

    # Check companion marker file
    if marker_fname:
        candidate_marker = path.parent / marker_fname
        marker_exists = candidate_marker.is_file()
        m_sha = compute_file_sha256(candidate_marker) if marker_exists else None
        companion_infos.append(
            CompanionFileInfo(
                role="marker",
                filename=marker_fname,
                resolved_path=str(candidate_marker) if marker_exists else None,
                exists=marker_exists,
                sha256=m_sha,
            )
        )
        if not marker_exists:
            issues.append(f"{QualityIssue.MISSING_COMPANION_FILE.value}: MarkerFile '{marker_fname}' referenced in header does not exist.")

    # If companion files are missing, recording is invalid
    if issues:
        return RecordingQualityReport(
            target_path=str(path),
            quality_state=RecordingQualityState.INVALID_RECORDING.value,
            passed_validation=False,
            is_synthetic=False,
            issues=issues,
            warnings=warnings,
            metadata=RecordingMetadata(
                source_format="BRAINVISION",
                sampling_rate_hz=sfreq_hdr,
                channel_count=n_chan_hdr,
                channel_names=ch_names_hdr,
                duration_s=None,
                bad_channels=[],
                montage=None,
                companion_files=companion_infos,
            ),
            provenance=ProvenanceInfo(
                origin_path=str(path),
                sha256=file_sha256,
                provenance_hint=provenance_hint,
                is_synthetic=False,
                supplied_labels=supplied_labels,
            ),
            inspection_limits=InspectionLimits(max_bounded_samples=bounded_samples, inspected_samples=0),
            report_timestamp_utc=timestamp_utc,
        )

    # If MNE is missing, report capability state
    if mne is None:
        return RecordingQualityReport(
            target_path=str(path),
            quality_state=RecordingQualityState.MISSING_OPTIONAL_DEPENDENCY.value,
            passed_validation=False,
            is_synthetic=False,
            issues=[f"{QualityIssue.MISSING_DEPENDENCY.value}: Optional dependency 'mne' is required to inspect BrainVision signals."],
            missing_dependencies=["mne"],
            metadata=RecordingMetadata(
                source_format="BRAINVISION",
                sampling_rate_hz=sfreq_hdr,
                channel_count=n_chan_hdr,
                channel_names=ch_names_hdr,
                duration_s=None,
                bad_channels=[],
                montage=None,
                companion_files=companion_infos,
            ),
            provenance=ProvenanceInfo(
                origin_path=str(path),
                sha256=file_sha256,
                provenance_hint=provenance_hint,
                is_synthetic=False,
                supplied_labels=supplied_labels,
            ),
            inspection_limits=InspectionLimits(max_bounded_samples=bounded_samples, inspected_samples=0),
            report_timestamp_utc=timestamp_utc,
        )

    # Read bounded chunk via MNE with preload=False
    try:
        raw = mne.io.read_raw_brainvision(str(path), preload=False, verbose="ERROR")
    except Exception as exc:
        return RecordingQualityReport(
            target_path=str(path),
            quality_state=RecordingQualityState.INVALID_RECORDING.value,
            passed_validation=False,
            is_synthetic=False,
            issues=[f"{QualityIssue.CORRUPTED_FILE.value}: MNE failed to open BrainVision file: {exc}"],
            provenance=ProvenanceInfo(
                origin_path=str(path),
                sha256=file_sha256,
                provenance_hint=provenance_hint,
                is_synthetic=False,
                supplied_labels=supplied_labels,
            ),
            inspection_limits=InspectionLimits(max_bounded_samples=bounded_samples, inspected_samples=0),
            report_timestamp_utc=timestamp_utc,
        )

    return _validate_opened_raw(
        raw=raw,
        path=path,
        source_format="BRAINVISION",
        file_sha256=file_sha256,
        bounded_samples=bounded_samples,
        provenance_hint=provenance_hint,
        supplied_labels=supplied_labels,
        timestamp_utc=timestamp_utc,
        companion_infos=companion_infos,
    )


def _inspect_edf_bdf(
    path: Path,
    *,
    ext: str,
    provenance_hint: str,
    bounded_samples: int,
    supplied_labels: dict[str, str],
    timestamp_utc: str,
    mne: Any | None,
) -> RecordingQualityReport:
    """Memory-bounded inspection for EDF and BDF containers."""
    file_sha256 = compute_file_sha256(path)
    fmt_name = "EDF" if ext == ".edf" else "BDF"

    if mne is None:
        return RecordingQualityReport(
            target_path=str(path),
            quality_state=RecordingQualityState.MISSING_OPTIONAL_DEPENDENCY.value,
            passed_validation=False,
            is_synthetic=False,
            issues=[f"{QualityIssue.MISSING_DEPENDENCY.value}: Optional dependency 'mne' is required to inspect {fmt_name} files."],
            missing_dependencies=["mne"],
            provenance=ProvenanceInfo(
                origin_path=str(path),
                sha256=file_sha256,
                provenance_hint=provenance_hint,
                is_synthetic=False,
                supplied_labels=supplied_labels,
            ),
            inspection_limits=InspectionLimits(max_bounded_samples=bounded_samples, inspected_samples=0),
            report_timestamp_utc=timestamp_utc,
        )

    try:
        if ext == ".bdf":
            raw = mne.io.read_raw_bdf(str(path), preload=False, verbose="ERROR")
        else:
            raw = mne.io.read_raw_edf(str(path), preload=False, verbose="ERROR")
    except Exception as exc:
        return RecordingQualityReport(
            target_path=str(path),
            quality_state=RecordingQualityState.INVALID_RECORDING.value,
            passed_validation=False,
            is_synthetic=False,
            issues=[f"{QualityIssue.CORRUPTED_FILE.value}: Failed to open {fmt_name} file: {exc}"],
            provenance=ProvenanceInfo(
                origin_path=str(path),
                sha256=file_sha256,
                provenance_hint=provenance_hint,
                is_synthetic=False,
                supplied_labels=supplied_labels,
            ),
            inspection_limits=InspectionLimits(max_bounded_samples=bounded_samples, inspected_samples=0),
            report_timestamp_utc=timestamp_utc,
        )

    return _validate_opened_raw(
        raw=raw,
        path=path,
        source_format=fmt_name,
        file_sha256=file_sha256,
        bounded_samples=bounded_samples,
        provenance_hint=provenance_hint,
        supplied_labels=supplied_labels,
        timestamp_utc=timestamp_utc,
        companion_infos=[],
    )


def _inspect_fif(
    path: Path,
    *,
    provenance_hint: str,
    bounded_samples: int,
    supplied_labels: dict[str, str],
    timestamp_utc: str,
    mne: Any | None,
) -> RecordingQualityReport:
    """Memory-bounded inspection for Neuromag FIF containers."""
    file_sha256 = compute_file_sha256(path)
    if mne is None:
        return RecordingQualityReport(
            target_path=str(path),
            quality_state=RecordingQualityState.MISSING_OPTIONAL_DEPENDENCY.value,
            passed_validation=False,
            is_synthetic=False,
            issues=[f"{QualityIssue.MISSING_DEPENDENCY.value}: Optional dependency 'mne' is required to inspect FIF files."],
            missing_dependencies=["mne"],
            provenance=ProvenanceInfo(
                origin_path=str(path),
                sha256=file_sha256,
                provenance_hint=provenance_hint,
                is_synthetic=False,
                supplied_labels=supplied_labels,
            ),
            inspection_limits=InspectionLimits(max_bounded_samples=bounded_samples, inspected_samples=0),
            report_timestamp_utc=timestamp_utc,
        )

    try:
        raw = mne.io.read_raw_fif(str(path), preload=False, verbose="ERROR")
    except Exception as exc:
        return RecordingQualityReport(
            target_path=str(path),
            quality_state=RecordingQualityState.INVALID_RECORDING.value,
            passed_validation=False,
            is_synthetic=False,
            issues=[f"{QualityIssue.CORRUPTED_FILE.value}: Failed to open FIF file: {exc}"],
            provenance=ProvenanceInfo(
                origin_path=str(path),
                sha256=file_sha256,
                provenance_hint=provenance_hint,
                is_synthetic=False,
                supplied_labels=supplied_labels,
            ),
            inspection_limits=InspectionLimits(max_bounded_samples=bounded_samples, inspected_samples=0),
            report_timestamp_utc=timestamp_utc,
        )

    return _validate_opened_raw(
        raw=raw,
        path=path,
        source_format="FIF",
        file_sha256=file_sha256,
        bounded_samples=bounded_samples,
        provenance_hint=provenance_hint,
        supplied_labels=supplied_labels,
        timestamp_utc=timestamp_utc,
        companion_infos=[],
    )


def _validate_opened_raw(
    raw: Any,
    path: Path,
    source_format: str,
    file_sha256: str,
    bounded_samples: int,
    provenance_hint: str,
    supplied_labels: dict[str, str],
    timestamp_utc: str,
    companion_infos: list[CompanionFileInfo],
) -> RecordingQualityReport:
    """Validate common metrics and bounded samples on an opened MNE raw object without preload."""
    issues: list[str] = []
    warnings: list[str] = []

    # Sampling frequency
    sfreq = float(raw.info.get("sfreq", 0.0))
    if sfreq <= 0.0 or math.isnan(sfreq) or math.isinf(sfreq):
        issues.append(f"{QualityIssue.INVALID_SAMPLING_FREQUENCY.value}: Non-positive sampling rate: {sfreq}")

    # Channel count and names
    channel_names = list(raw.ch_names)
    channel_count = len(channel_names)
    if channel_count == 0:
        issues.append(f"{QualityIssue.ZERO_CHANNELS.value}: Container has zero channels.")

    # Channel uniqueness
    seen_channels: set[str] = set()
    duplicates: set[str] = set()
    for name in channel_names:
        if name in seen_channels:
            duplicates.add(name)
        seen_channels.add(name)
    if duplicates:
        issues.append(
            f"{QualityIssue.DUPLICATE_CHANNEL_NAMES.value}: Duplicate channel names found: {sorted(duplicates)}"
        )

    # Duration
    n_times = int(getattr(raw, "n_times", 0))
    duration_s = (n_times / sfreq) if (sfreq > 0.0 and n_times >= 0) else None
    if n_times <= 0:
        issues.append(f"{QualityIssue.INVALID_DURATION.value}: Total samples count is non-positive: {n_times}")

    # Bounded samples finiteness inspection
    inspected_samples = min(n_times, bounded_samples) if n_times > 0 else 0
    if inspected_samples > 0 and channel_count > 0:
        try:
            chunk = np.asarray(raw.get_data(start=0, stop=inspected_samples), dtype=float)
            if chunk.shape != (channel_count, inspected_samples):
                warnings.append(
                    f"Unexpected chunk shape: expected ({channel_count}, {inspected_samples}), got {chunk.shape}"
                )
            if not np.all(np.isfinite(chunk)):
                issues.append(
                    f"{QualityIssue.NON_FINITE_SAMPLE_VALUES.value}: Non-finite values (NaN or Inf) found in inspected chunk."
                )
        except Exception as exc:
            issues.append(f"{QualityIssue.CORRUPTED_FILE.value}: Failed reading bounded sample chunk: {exc}")

    # Montage coverage
    montage = getattr(raw, "get_montage", lambda: None)()
    montage_coverage: MontageCoverage | None = None
    if montage is not None:
        try:
            pos_dict = montage.get_positions().get("ch_pos", {})
            channels_with_coords = sum(
                1 for ch in channel_names if ch in pos_dict and not np.isnan(pos_dict[ch]).any()
            )
            cov_ratio = float(channels_with_coords) / float(channel_count) if channel_count > 0 else 0.0
            coord_frame = montage.get_positions().get("coord_frame", "unknown")
            montage_coverage = MontageCoverage(
                montage_available=True,
                total_channels=channel_count,
                channels_with_coordinates=channels_with_coords,
                coverage_ratio=cov_ratio,
                coordinate_frame=coord_frame,
            )
        except Exception:
            montage_coverage = MontageCoverage(
                montage_available=True,
                total_channels=channel_count,
                channels_with_coordinates=0,
                coverage_ratio=0.0,
                coordinate_frame="unknown",
            )
    else:
        montage_coverage = MontageCoverage(
            montage_available=False,
            total_channels=channel_count,
            channels_with_coordinates=0,
            coverage_ratio=None,
            coordinate_frame=None,
        )

    # Bad channels
    bad_channels = list(raw.info.get("bads", []))

    # Provenance determination
    has_synthetic_markers = _detect_synthetic_markers(path, raw_obj=raw)
    if provenance_hint == "synthetic":
        is_synthetic = True
    elif provenance_hint == "empirical":
        if has_synthetic_markers:
            warnings.append("Explicit synthetic marker found in file despite empirical hint; flagging contamination.")
            is_synthetic = True
        else:
            is_synthetic = False
    else:  # 'auto'
        is_synthetic = has_synthetic_markers

    # Decide state
    if issues:
        quality_state = RecordingQualityState.INVALID_RECORDING.value
        passed = False
    elif is_synthetic:
        quality_state = RecordingQualityState.VALIDATED_SYNTHETIC_ONLY.value
        passed = True
    else:
        quality_state = RecordingQualityState.VALIDATED_EMPIRICAL_LOCAL.value
        passed = True

    return RecordingQualityReport(
        schema_version="v1.0.0",
        target_path=str(path),
        quality_state=quality_state,
        passed_validation=passed,
        is_synthetic=is_synthetic,
        issues=issues,
        warnings=warnings,
        metadata=RecordingMetadata(
            source_format=source_format,
            sampling_rate_hz=sfreq if sfreq > 0.0 else None,
            channel_count=channel_count,
            channel_names=channel_names,
            duration_s=duration_s,
            bad_channels=bad_channels,
            montage=montage_coverage,
            companion_files=companion_infos,
        ),
        provenance=ProvenanceInfo(
            origin_path=str(path),
            sha256=file_sha256,
            provenance_hint=provenance_hint,
            is_synthetic=is_synthetic,
            supplied_labels=supplied_labels,
        ),
        inspection_limits=InspectionLimits(
            max_bounded_samples=bounded_samples,
            inspected_samples=inspected_samples,
            preload=False,
        ),
        missing_dependencies=[],
        report_timestamp_utc=timestamp_utc,
    )


def _inspect_bids_container(
    bids_root: Path,
    *,
    provenance_hint: str,
    bounded_samples: int,
    supplied_labels: dict[str, str],
    timestamp_utc: str,
    mne_override: Any | None,
) -> RecordingQualityReport:
    """Inspect local BIDS container directory structure and recordings."""
    issues: list[str] = []
    warnings: list[str] = []

    desc_file = bids_root / "dataset_description.json"
    if not desc_file.is_file():
        return RecordingQualityReport(
            target_path=str(bids_root),
            quality_state=RecordingQualityState.INCOMPLETE_METADATA.value,
            passed_validation=False,
            is_synthetic=False,
            issues=[f"{QualityIssue.MISSING_MANDATORY_METADATA.value}: BIDS dataset_description.json missing in {bids_root}."],
            provenance=ProvenanceInfo(
                origin_path=str(bids_root),
                sha256=None,
                provenance_hint=provenance_hint,
                is_synthetic=False,
                supplied_labels=supplied_labels,
            ),
            inspection_limits=InspectionLimits(max_bounded_samples=bounded_samples, inspected_samples=0),
            report_timestamp_utc=timestamp_utc,
        )

    try:
        with desc_file.open("r", encoding="utf-8") as f:
            desc_data = json.load(f)
    except Exception as exc:
        return RecordingQualityReport(
            target_path=str(bids_root),
            quality_state=RecordingQualityState.INVALID_RECORDING.value,
            passed_validation=False,
            is_synthetic=False,
            issues=[f"{QualityIssue.CORRUPTED_FILE.value}: Corrupted dataset_description.json: {exc}"],
            provenance=ProvenanceInfo(
                origin_path=str(bids_root),
                sha256=compute_file_sha256(desc_file),
                provenance_hint=provenance_hint,
                is_synthetic=False,
                supplied_labels=supplied_labels,
            ),
            inspection_limits=InspectionLimits(max_bounded_samples=bounded_samples, inspected_samples=0),
            report_timestamp_utc=timestamp_utc,
        )

    if "Name" not in desc_data or "BIDSVersion" not in desc_data:
        issues.append(f"{QualityIssue.MISSING_MANDATORY_METADATA.value}: dataset_description.json lacks Name or BIDSVersion.")

    # Find recordings inside BIDS container
    recording_candidates: list[Path] = []
    for ext in (".fif", ".edf", ".bdf", ".vhdr"):
        recording_candidates.extend(bids_root.rglob(f"sub-*{ext}"))

    if not recording_candidates:
        issues.append(f"{QualityIssue.MISSING_MANDATORY_METADATA.value}: No EEG/MEG recording files found in BIDS container.")
        return RecordingQualityReport(
            target_path=str(bids_root),
            quality_state=RecordingQualityState.INCOMPLETE_METADATA.value,
            passed_validation=False,
            is_synthetic=False,
            issues=issues,
            warnings=warnings,
            provenance=ProvenanceInfo(
                origin_path=str(bids_root),
                sha256=compute_file_sha256(desc_file),
                provenance_hint=provenance_hint,
                is_synthetic=False,
                supplied_labels=supplied_labels,
            ),
            inspection_limits=InspectionLimits(max_bounded_samples=bounded_samples, inspected_samples=0),
            report_timestamp_utc=timestamp_utc,
        )

    # Check synthetic indicators in BIDS dataset description or path
    bids_synthetic = _detect_synthetic_markers(bids_root)
    desc_str = json.dumps(desc_data).lower()
    for kw in SYNTHETIC_KEYWORDS:
        if kw in desc_str:
            bids_synthetic = True

    if provenance_hint == "synthetic":
        is_synthetic = True
    elif provenance_hint == "empirical":
        is_synthetic = bids_synthetic
        if bids_synthetic:
            warnings.append("Synthetic markers detected in BIDS description despite empirical hint.")
    else:
        is_synthetic = bids_synthetic

    # Inspect first recording file as bounded representative
    rep_file = recording_candidates[0]
    sub_report = inspect_recording_quality(
        rep_file,
        provenance_hint="synthetic" if is_synthetic else provenance_hint,
        bounded_samples=bounded_samples,
        supplied_labels=supplied_labels,
        mne_override=mne_override,
    )

    if not sub_report.passed_validation:
        issues.extend(sub_report.issues)
        state = sub_report.quality_state
        passed = False
    else:
        state = RecordingQualityState.VALIDATED_SYNTHETIC_ONLY.value if is_synthetic else RecordingQualityState.VALIDATED_EMPIRICAL_LOCAL.value
        passed = True

    return RecordingQualityReport(
        schema_version="v1.0.0",
        target_path=str(bids_root),
        quality_state=state,
        passed_validation=passed,
        is_synthetic=is_synthetic,
        issues=issues,
        warnings=warnings + sub_report.warnings,
        metadata=sub_report.metadata,
        provenance=ProvenanceInfo(
            origin_path=str(bids_root),
            sha256=compute_file_sha256(desc_file),
            provenance_hint=provenance_hint,
            is_synthetic=is_synthetic,
            supplied_labels=supplied_labels,
        ),
        inspection_limits=InspectionLimits(
            max_bounded_samples=bounded_samples,
            inspected_samples=sub_report.inspection_limits.inspected_samples if sub_report.inspection_limits else 0,
            preload=False,
        ),
        missing_dependencies=sub_report.missing_dependencies,
        report_timestamp_utc=timestamp_utc,
    )
