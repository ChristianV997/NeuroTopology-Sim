"""Typed data structures and contracts for multimodal physiology streaming.

Scientific guardrails:
- Physiological coupling is a candidate mechanism, not proof of a mental-state transition.
- Do not describe respiration or parasympathetic activity as equivalent to calmness,
  detachment, equanimity, or liberation.
- Synthetic data is never empirical evidence.
- No label inference: never infer awake, sedated, meditation, jhāna, task, or arousal
  states from filenames or paths.
- Strict null-safe JSON serialization rejecting NaN and Infinity.
"""
from __future__ import annotations

from enum import Enum
import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from typing import Any, Sequence
import numpy as np


class PhysiologyChannelType(str, Enum):
    """Canonical multimodal channel classifications."""
    EEG = "EEG"
    ECG = "ECG"
    RESPIRATION = "RESPIRATION"
    GSR_EDA = "GSR_EDA"
    PPG = "PPG"
    EMG = "EMG"
    EOG = "EOG"
    TEMPERATURE = "TEMPERATURE"
    OTHER_PHYSIOLOGY = "OTHER_PHYSIOLOGY"


class AlignmentMode(str, Enum):
    """Operation mode for clock alignment and resampling."""
    CAUSAL = "CAUSAL"
    NONCAUSAL = "NONCAUSAL"


class PhysiologyCapabilityState(str, Enum):
    """Explicit capability states for multimodal stream ingestion."""
    AVAILABLE = "AVAILABLE"
    MISSING_OPTIONAL_DEPENDENCY = "MISSING_OPTIONAL_DEPENDENCY"
    UNSUPPORTED_FORMAT = "UNSUPPORTED_FORMAT"
    UNAVAILABLE_FILE = "UNAVAILABLE_FILE"
    MALFORMED_METADATA = "MALFORMED_METADATA"


@dataclass
class ChannelInfo:
    """Channel-level descriptive metadata and calibration metrics."""
    name: str
    channel_type: str
    original_sfreq_hz: float
    aligned_sfreq_hz: float
    units: str
    is_bad: bool = False
    montage_coordinates: tuple[float, float, float] | None = None


@dataclass
class ResamplingMetadata:
    """Provenance for channel-specific resampling operations."""
    source_sfreq_hz: float
    target_sfreq_hz: float
    ratio: float
    method: str
    interpolated: bool


@dataclass
class ClockAlignmentInfo:
    """Multimodal clock alignment and synchronization diagnostics."""
    common_clock_sfreq_hz: float
    alignment_mode: str
    clock_drift_detected: bool = False
    clock_drift_warning: str | None = None
    resampling: dict[str, ResamplingMetadata] = field(default_factory=dict)
    missing_channels: list[str] = field(default_factory=list)


@dataclass
class PhysiologyChunk:
    """A memory-bounded, time-aligned window of multimodal physiological signals."""
    chunk_index: int
    start_sample: int
    end_sample: int
    start_time_s: float
    end_time_s: float
    timestamps: list[float]
    channel_names: list[str]
    channel_types: list[str]
    units: dict[str, str]
    sample_rate_hz: float
    data: np.ndarray
    finite_status: bool
    bad_channel_flags: dict[str, bool]
    source_checksum: str
    provenance_origin: str
    is_synthetic: bool
    supplied_labels: dict[str, str] = field(default_factory=dict)
    clock_alignment: ClockAlignmentInfo | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert chunk metadata and summary to serializable dict without full array."""
        return {
            "chunk_index": self.chunk_index,
            "start_sample": self.start_sample,
            "end_sample": self.end_sample,
            "start_time_s": self.start_time_s,
            "end_time_s": self.end_time_s,
            "sample_rate_hz": self.sample_rate_hz,
            "n_channels": len(self.channel_names),
            "n_samples": int(self.data.shape[1]) if self.data.ndim == 2 else 0,
            "channel_names": self.channel_names,
            "channel_types": self.channel_types,
            "units": self.units,
            "finite_status": self.finite_status,
            "bad_channel_flags": self.bad_channel_flags,
            "source_checksum": self.source_checksum,
            "provenance_origin": self.provenance_origin,
            "is_synthetic": self.is_synthetic,
            "supplied_labels": self.supplied_labels,
        }


@dataclass
class RespiratoryFeatures:
    """Bounded, feature-ready respiratory summaries."""
    respiratory_rate_bpm: float | None
    inspiratory_duration_s: float | None
    expiratory_duration_s: float | None
    ie_ratio: float | None
    respiratory_phase_rad: float | None


@dataclass
class CardiacFeatures:
    """Bounded, feature-ready cardiac and HRV-compatible metrics."""
    heart_rate_bpm: float | None
    rr_intervals_ms: list[float] | None
    rmssd_ms: float | None
    sdnn_ms: float | None


@dataclass
class QualityMetrics:
    """Data quality and synchronization assessments."""
    signal_quality_index: float | None
    missingness_ratio: float
    synchronization_quality_index: float | None
    finite_ratio: float


@dataclass
class PhysiologySummary:
    """High-level bounded summary of multimodal physiology recording."""
    schema_version: str = "v1.0.0"
    source_file: str = ""
    source_checksum: str = ""
    is_synthetic: bool = False
    capability_state: str = PhysiologyCapabilityState.AVAILABLE.value
    supplied_labels: dict[str, str] = field(default_factory=dict)
    clock_alignment: ClockAlignmentInfo | None = None
    channels: list[ChannelInfo] = field(default_factory=list)
    respiration: RespiratoryFeatures | None = None
    cardiac: CardiacFeatures | None = None
    quality: QualityMetrics | None = None
    total_samples: int = 0
    duration_s: float | None = None
    warnings: list[str] = field(default_factory=list)
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
                    raise ValueError(f"Non-compliant float encountered in physiology report: {val}")
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
        """Produce deterministic, null-safe JSON with SHA-256 report checksum."""
        d = self.to_dict()
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


def verify_physiology_report_checksum(report_dict: dict[str, Any]) -> bool:
    """Verify cryptographic integrity of a serialized PhysiologySummary dictionary."""
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
