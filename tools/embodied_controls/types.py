"""Data types, schemas, and contracts for embodied-control alignment.

Scientific guardrails:
- Embodied variables are candidate explanatory features, moderators, covariates,
  or possible intervention targets; they are not proven causal mechanisms.
- Do not label:
  - parasympathetic activity as calmness;
  - slow breathing as equanimity;
  - reward sensitivity as detachment;
  - autonomic change as liberation.
- No claim of causal mediation.
- Synthetic data is never empirical evidence.
- Strict null-safe JSON serialization rejecting NaN and Infinity.
"""
from __future__ import annotations

from enum import Enum
import hashlib
import json
import math
from dataclasses import asdict, dataclass, field
from typing import Any, Mapping, Sequence
import numpy as np


class AlignmentQualityState(str, Enum):
    """Quality classification of the multimodal alignment."""
    PASS = "PASS"
    DEGRADED = "DEGRADED"
    FAIL = "FAIL"
    INCONCLUSIVE = "INCONCLUSIVE"


class EvidenceClass(str, Enum):
    """Explicit evidence categorization."""
    SYNTHETIC_CONTROL = "SYNTHETIC_CONTROL"
    EMPIRICAL_CANDIDATE = "EMPIRICAL_CANDIDATE"
    INCONCLUSIVE = "INCONCLUSIVE"
    NOT_SUPPORTED = "NOT_SUPPORTED"


class VariableRole(str, Enum):
    """Epistemological role of an embodied physiological variable."""
    CANDIDATE_PREDICTOR = "candidate_predictor"
    MODERATOR = "moderator"
    COVARIATE = "covariate"
    INTERVENTION_VARIABLE = "possible_intervention_variable"


class ConfoundControlType(str, Enum):
    """Types of empirical confound controls."""
    CIRCULAR_SHIFT = "circular_shift"
    BLOCK_SHIFT = "block_shift"
    MATCHED_VARIANCE = "matched_variance"
    CONDITION_PRESERVING_PERMUTATION = "condition_preserving_permutation"


class InterpolationMethod(str, Enum):
    """Resampling and clock interpolation method."""
    CAUSAL_LINEAR = "causal_linear"
    LINEAR = "linear"
    NEAREST = "nearest"
    IDENTITY = "identity"


BANNED_ASSERTION_KEYWORDS = (
    "calmness",
    "equanimity",
    "detachment",
    "liberation",
    "causal mediation",
    "proven causal",
    "consciousness proven",
    "soul proven",
    "afterlife proven",
    "jhāna proven",
    "jhana proven",
)


def validate_no_banned_assertions(text: str) -> None:
    """Validate that text contains no unscientific or metaphysical assertions."""
    t_lower = text.lower()
    for phrase in BANNED_ASSERTION_KEYWORDS:
        if phrase in t_lower:
            raise ValueError(
                f"Banned assertion detected in embodied-control metadata: '{phrase}'. "
                "Embodied variables are candidate explanatory features, not proven causal mechanisms."
            )


@dataclass
class ResamplingRecord:
    """Provenance for a single channel's sample-rate conversion."""
    channel_name: str
    source_sfreq_hz: float
    target_sfreq_hz: float
    ratio: float
    method: str
    interpolated: bool


@dataclass
class ClockDriftDiagnostics:
    """Diagnostics for inter-sensor clock drift and discontinuity."""
    estimated_drift_ppm: float
    drift_detected: bool
    clock_discontinuity_s: float
    warning: str | None = None


@dataclass
class LagCandidate:
    """Candidate temporal lag between neural and autonomic features."""
    lag_s: float
    cross_correlation: float
    mutual_information: float | None = None
    is_peak: bool = False


@dataclass
class AlignmentMetadata:
    """Comprehensive alignment diagnostics and provenance for a time window."""
    common_clock_hz: float
    start_time_s: float
    end_time_s: float
    window_overlap_s: float
    overlap_ratio: float
    interpolation_method: str
    clock_drift: ClockDriftDiagnostics
    resampling: list[ResamplingRecord] = field(default_factory=list)
    lag_candidates: list[LagCandidate] = field(default_factory=list)
    optimal_lag_s: float = 0.0
    missingness_ratio: float = 0.0
    missing_channels: list[str] = field(default_factory=list)
    signal_quality_state: str = AlignmentQualityState.PASS.value


@dataclass
class RespiratoryWindowFeatures:
    """Feature-ready respiratory descriptors in a window."""
    respiratory_phase_rad: float | None
    respiratory_rate_bpm: float | None
    inspiratory_duration_s: float | None
    expiratory_duration_s: float | None
    ie_ratio: float | None
    cycle_count: int
    variable_role: str = VariableRole.CANDIDATE_PREDICTOR.value

    def __post_init__(self) -> None:
        validate_no_banned_assertions(self.variable_role)


@dataclass
class CardiacWindowFeatures:
    """Feature-ready cardiac and HRV descriptors in a window."""
    heart_rate_bpm: float | None
    rr_intervals_ms: list[float] | None
    rmssd_ms: float | None
    sdnn_ms: float | None
    pnn50_pct: float | None
    r_peak_count: int
    variable_role: str = VariableRole.COVARIATE.value

    def __post_init__(self) -> None:
        validate_no_banned_assertions(self.variable_role)


@dataclass
class AutonomicProxyFeatures:
    """Autonomic proxy metrics (EDA / PPG / autonomic balance)."""
    eda_tonic_mean_us: float | None = None
    eda_phasic_peaks_count: int = 0
    autonomic_balance_proxy: float | None = None
    vagal_tone_proxy: float | None = None
    variable_role: str = VariableRole.MODERATOR.value

    def __post_init__(self) -> None:
        validate_no_banned_assertions(self.variable_role)


@dataclass
class NeuralWindowFeatures:
    """Time-aligned neural feature descriptors for an EEG window."""
    theta_power_rel: float | None = None
    alpha_power_rel: float | None = None
    beta_power_rel: float | None = None
    gamma_power_rel: float | None = None
    spectral_centroid_hz: float | None = None
    rms_amplitude_uv: float | None = None
    channel_count: int = 0


@dataclass
class AlignedWindowPair:
    """Paired neural-embodied window containing time-aligned features."""
    window_index: int
    window_id: str
    start_time_s: float
    end_time_s: float
    alignment: AlignmentMetadata
    neural: NeuralWindowFeatures
    respiration: RespiratoryWindowFeatures | None = None
    cardiac: CardiacWindowFeatures | None = None
    autonomic: AutonomicProxyFeatures | None = None
    variable_roles: dict[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for role in self.variable_roles.values():
            validate_no_banned_assertions(role)


@dataclass
class ConfoundControlResult:
    """Evaluation result for an empirical confound control perturbation."""
    control_type: str
    parameter_description: str
    perturbation_offset_s: float | None = None
    coupling_metric_name: str = "cross_correlation"
    original_coupling: float = 0.0
    perturbed_coupling: float = 0.0
    attenuation_ratio: float = 0.0
    retains_autocorrelation: bool = True
    surrogate_passed: bool = True


@dataclass
class EmbodiedControlAlignmentReport:
    """Complete, self-contained record of embodied-control alignment."""
    schema_version: str = "v1.0.0"
    report_timestamp: str = ""
    source_checksums: dict[str, str] = field(default_factory=dict)
    is_synthetic: bool = False
    evidence_class: str = EvidenceClass.SYNTHETIC_CONTROL.value
    alignment_quality_score: float = 1.0
    alignment_quality_state: str = AlignmentQualityState.PASS.value
    feature_units: dict[str, str] = field(default_factory=dict)
    variable_roles: dict[str, str] = field(default_factory=dict)
    n_windows_aligned: int = 0
    windows: list[AlignedWindowPair] = field(default_factory=list)
    confound_controls: list[ConfoundControlResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    report_checksum_sha256: str = ""

    def __post_init__(self) -> None:
        for r in self.variable_roles.values():
            validate_no_banned_assertions(r)

    def to_dict(self) -> dict[str, Any]:
        """Produce sanitized dictionary rejecting NaN, Inf, and non-finite floats."""
        def _sanitize(val: Any) -> Any:
            if isinstance(val, (str, int, bool)):
                return val
            if val is None:
                return None
            if isinstance(val, float):
                if math.isnan(val) or math.isinf(val):
                    raise ValueError(f"Non-compliant float encountered in alignment report: {val}")
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
        """Serialize report to deterministic, null-safe JSON with SHA-256 digest."""
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


def verify_embodied_control_report_checksum(report_dict: dict[str, Any]) -> bool:
    """Verify cryptographic SHA-256 integrity of an EmbodiedControlAlignmentReport."""
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
