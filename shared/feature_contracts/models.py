"""Typed data models and schemas for canonical, provenance-rich feature contracts.

Supports PSD, pairwise FC, triadic FC, higher-order spectra, physiology,
spatial phase topology, graph persistence, directed hypergraphs, and behavioral labels.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import math
from typing import Any, Sequence


class FeatureFamily(str, Enum):
    """Registered canonical feature families."""
    PSD = "psd"
    CROSS_SPECTRUM = "cross_spectrum"
    PAIRWISE_FC = "pairwise_fc"
    TRIADIC_FC = "triadic_fc"
    HIGHER_ORDER_SPECTRA = "higher_order_spectra"
    RESPIRATION = "respiration"
    ECG_HRV = "ecg_hrv"
    SPATIAL_PHASE_CHARGE = "spatial_phase_charge"
    GRAPH_BETA_1 = "graph_beta_1"
    DIRECTED_HYPERGRAPH = "directed_hypergraph"
    BEHAVIORAL_TRANSITION_LABELS = "behavioral_transition_labels"


class CoordinateStatus(str, Enum):
    """Physical or geometric coordinate availability."""
    THREE_D_MONTAGE = "3d_montage"
    TWO_D_PLANAR = "2d_planar"
    TOPOLOGICAL_ABSTRACT = "topological_abstract"
    MISSING = "missing"


class EvidenceClass(str, Enum):
    """Epistemic evidence classification tier."""
    EMPIRICAL_FEATURE = "empirical_feature"
    COMPUTATIONAL_MODEL = "computational_model"
    SYNTHETIC_SCAFFOLDING = "synthetic_scaffolding"
    DESCRIPTIVE_TOPOLOGY_ONLY = "descriptive_topology_only"


@dataclass
class FrequencyBand:
    """Frequency band specification for spectral and cross-frequency features."""
    low_hz: float
    high_hz: float
    band_name: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "low_hz": self.low_hz,
            "high_hz": self.high_hz,
            "band_name": self.band_name,
        }


@dataclass
class TimeWindow:
    """Time window specification in seconds relative to recording onset."""
    start_s: float
    duration_s: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "start_s": self.start_s,
            "duration_s": self.duration_s,
        }


@dataclass
class CanonicalFeatureRecord:
    """Versioned canonical feature record with rich provenance, units, and axes."""
    feature_family: str
    feature_name: str
    mathematical_definition: str
    units: str
    schema_version: str = "NeuroTopologySim.CanonicalFeatureRecord.v1"
    frequency_band: dict[str, Any] | None = None
    time_window: dict[str, Any] | None = None
    sampling_rate_hz: float | None = None
    channel_node_identity: list[str] = field(default_factory=list)
    coordinate_status: str = CoordinateStatus.MISSING.value
    montage_coordinates: list[list[float]] | None = None
    subject: str | None = None
    session: str | None = None
    run: str | None = None
    condition_label: str | None = None
    provenance_checksum: str = ""
    preprocessing: list[str] = field(default_factory=list)
    missingness: float | None = None
    uncertainty: dict[str, Any] | None = None
    is_synthetic: bool = False
    evidence_class: str = EvidenceClass.EMPIRICAL_FEATURE.value
    axes: list[str] = field(default_factory=list)
    shape: list[int] = field(default_factory=list)
    values: Any = None
    checksum: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serializes record to safe dictionary with null for missing values."""
        return _safe_dict({
            "schema_version": self.schema_version,
            "feature_family": str(self.feature_family),
            "feature_name": self.feature_name,
            "mathematical_definition": self.mathematical_definition,
            "units": self.units,
            "frequency_band": self.frequency_band,
            "time_window": self.time_window,
            "sampling_rate_hz": self.sampling_rate_hz,
            "channel_node_identity": list(self.channel_node_identity),
            "coordinate_status": str(self.coordinate_status),
            "montage_coordinates": self.montage_coordinates,
            "subject": self.subject,
            "session": self.session,
            "run": self.run,
            "condition_label": self.condition_label,
            "provenance_checksum": self.provenance_checksum,
            "preprocessing": list(self.preprocessing),
            "missingness": self.missingness,
            "uncertainty": self.uncertainty,
            "is_synthetic": self.is_synthetic,
            "evidence_class": str(self.evidence_class),
            "axes": list(self.axes),
            "shape": list(self.shape),
            "values": self.values,
            "checksum": self.checksum,
        })


@dataclass
class CanonicalFeatureBundle:
    """Bundle collection of canonical feature records for a session or run."""
    bundle_id: str
    records: list[CanonicalFeatureRecord] = field(default_factory=list)
    schema_version: str = "NeuroTopologySim.CanonicalFeatureBundle.v1"
    subject: str | None = None
    session: str | None = None
    run: str | None = None
    condition_label: str | None = None
    is_synthetic: bool = False
    provenance_checksum: str = ""
    bundle_checksum: str = ""

    def to_dict(self) -> dict[str, Any]:
        return _safe_dict({
            "schema_version": self.schema_version,
            "bundle_id": self.bundle_id,
            "subject": self.subject,
            "session": self.session,
            "run": self.run,
            "condition_label": self.condition_label,
            "is_synthetic": self.is_synthetic,
            "provenance_checksum": self.provenance_checksum,
            "records": [r.to_dict() for r in self.records],
            "bundle_checksum": self.bundle_checksum,
        })


def _safe_dict(val: Any) -> Any:
    """Recursively replaces non-finite floats with None and enforces JSON compliance."""
    if isinstance(val, float):
        return val if math.isfinite(val) else None
    if isinstance(val, (int, str, bool)) or val is None:
        return val
    if isinstance(val, dict):
        return {str(k): _safe_dict(v) for k, v in val.items()}
    if isinstance(val, (list, tuple)):
        return [_safe_dict(x) for x in val]
    return str(val)
