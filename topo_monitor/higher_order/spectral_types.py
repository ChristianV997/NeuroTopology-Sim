"""Typed, JSON-safe records for bounded higher-order spectral analysis."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Optional

SCHEMA_VERSION = "NeuroTopologySim.HigherOrderSpectra.v1"


def _clean(value: Any) -> Any:
    """Convert dataclasses/NumPy scalars into strict-JSON-compatible values."""
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, dict):
        return {str(key): _clean(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_clean(item) for item in value]
    return value


@dataclass(frozen=True)
class FrequencyAxis:
    frequencies_hz: tuple[float, ...]
    resolution_hz: float
    nyquist_hz: float
    units: str = "Hz"

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(frozen=True)
class SegmentConfiguration:
    segment_length: int = 256
    n_fft: int = 256
    overlap: float = 0.5
    taper: str = "hann"
    demean: bool = True
    detrend: str = "constant"
    frequency_bins: int = 32
    trispectrum_slices: int = 4
    max_channels: int = 8
    memory_budget_bytes: int = 64 * 1024 * 1024
    max_surrogates: int = 32

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(frozen=True)
class Provenance:
    source: str
    sampling_rate_hz: float
    synthetic: bool
    checksum_sha256: str
    n_channels: int
    n_samples: int
    frequency_units: str = "Hz"

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(frozen=True)
class BispectrumSummary:
    frequency_axis: FrequencyAxis
    magnitude: tuple[tuple[Optional[float], ...], ...]
    bicoherence: tuple[tuple[Optional[float], ...], ...]
    segment_count: int
    channel_count: int
    normalization: str

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(frozen=True)
class TrispectrumSlice:
    frequency_axis: FrequencyAxis
    slice_frequencies_hz: tuple[float, ...]
    magnitude: tuple[tuple[tuple[Optional[float], ...], ...], ...]
    segment_count: int
    normalization: str
    representation: str = "selected_two_dimensional_slices"

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(frozen=True)
class Modulogram:
    carrier_axis: FrequencyAxis
    modulation_axis: FrequencyAxis
    magnitude: tuple[tuple[Optional[float], ...], ...]
    segment_count: int
    normalization: str
    representation: str = "reduced_carrier_modulation_map"

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(frozen=True)
class SurrogateComparison:
    method: str
    seed: int
    surrogate_count: int
    observed: Optional[float]
    surrogate_mean: Optional[float]
    surrogate_std: Optional[float]
    standardized_difference: Optional[float]
    empirical_p_value: Optional[float]
    block_length: Optional[int] = None

    def to_dict(self) -> dict[str, Any]:
        return _clean(asdict(self))


@dataclass(frozen=True)
class HigherOrderSpectralReport:
    schema_version: str
    provenance: Provenance
    segment_configuration: SegmentConfiguration
    bispectrum: Optional[BispectrumSummary]
    trispectrum: Optional[TrispectrumSlice]
    modulogram: Optional[Modulogram]
    comparisons: dict[str, Any] = field(default_factory=dict)
    surrogates: tuple[SurrogateComparison, ...] = ()
    diagnostics: dict[str, Any] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        return _clean(result)
