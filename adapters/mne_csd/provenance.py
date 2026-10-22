"""Provenance records for CSD transforms (finite, JSON-serializable)."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union

from .constants import (
    DOCUMENTED_OUTPUT_UNIT,
    DOCUMENTED_OUTPUT_UNIT_SOURCE,
    MNE_API_DOC_URL,
    MNE_LICENSE,
    MNE_LICENSE_URL,
    MNE_SOURCE_URL,
    NOT_SOURCE_LOCALIZATION,
    TRANSFORM_KIND,
)


@dataclass(frozen=True)
class ChannelCoordinateReport:
    name: str
    ch_type: str
    xyz_m: Optional[Tuple[float, float, float]]
    usable: bool
    reason: Optional[str] = None


@dataclass(frozen=True)
class CSDProvenance:
    """Explicit metadata for one CSD application."""

    transform_kind: str
    not_source_localization: str
    mne_version: Optional[str]
    mne_available: bool
    mne_license: str
    mne_license_url: str
    mne_api_doc_url: str
    mne_source_url: str
    api_function: str
    parameters: Dict[str, Any]
    channel_types_requested: Dict[str, str]
    channels_selected: List[str]
    channels_excluded: List[str]
    channels_dropped_report: List[str]
    coordinate_frame: Optional[str]
    coordinates_m: Dict[str, Tuple[float, float, float]]
    sphere_model: Union[str, Tuple[float, float, float, float]]
    sphere_note: str
    input_units: Optional[str]
    output_units: Optional[str]
    output_units_status: str  # "documented" | "unknown"
    output_units_source: Optional[str]
    reference_policy: str
    channel_order: List[str]
    warnings: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        # Tuples become lists in asdict; keep JSON-friendly structure.
        return data


def build_provenance(
    *,
    mne_version: Optional[str],
    mne_available: bool,
    parameters: Mapping[str, Any],
    channel_types_requested: Mapping[str, str],
    channels_selected: Sequence[str],
    channels_excluded: Sequence[str],
    channels_dropped_report: Sequence[str],
    coordinate_frame: Optional[str],
    coordinates_m: Mapping[str, Sequence[float]],
    sphere_model: Union[str, Sequence[float]],
    input_units: Optional[str],
    output_units: Optional[str],
    output_units_status: str,
    output_units_source: Optional[str],
    channel_order: Sequence[str],
    warnings: Optional[Sequence[str]] = None,
) -> CSDProvenance:
    if isinstance(sphere_model, str):
        sphere: Union[str, Tuple[float, float, float, float]] = sphere_model
        sphere_note = (
            "sphere='auto' requests MNE's digitization-based spherical head model fit "
            "(center + radius in meters). Exact fitted values come from MNE at runtime."
            if sphere_model == "auto"
            else f"sphere model string: {sphere_model}"
        )
    else:
        vals = tuple(float(v) for v in sphere_model)
        if len(vals) != 4:
            raise ValueError("sphere sequence must be (x, y, z, r) in meters")
        sphere = (vals[0], vals[1], vals[2], vals[3])
        sphere_note = "explicit sphere (x, y, z, r) in meters forwarded to MNE"

    coords = {
        name: (float(xyz[0]), float(xyz[1]), float(xyz[2]))
        for name, xyz in coordinates_m.items()
    }
    return CSDProvenance(
        transform_kind=TRANSFORM_KIND,
        not_source_localization=NOT_SOURCE_LOCALIZATION,
        mne_version=mne_version,
        mne_available=mne_available,
        mne_license=MNE_LICENSE,
        mne_license_url=MNE_LICENSE_URL,
        mne_api_doc_url=MNE_API_DOC_URL,
        mne_source_url=MNE_SOURCE_URL,
        api_function="mne.preprocessing.compute_current_source_density",
        parameters=dict(parameters),
        channel_types_requested=dict(channel_types_requested),
        channels_selected=list(channels_selected),
        channels_excluded=list(channels_excluded),
        channels_dropped_report=list(channels_dropped_report),
        coordinate_frame=coordinate_frame,
        coordinates_m=coords,
        sphere_model=sphere,
        sphere_note=sphere_note,
        input_units=input_units,
        output_units=output_units,
        output_units_status=output_units_status,
        output_units_source=output_units_source,
        reference_policy=(
            "adapter_does_not_call_set_eeg_reference; "
            "MNE CSD applies a reference-free spherical-spline Laplacian transform"
        ),
        channel_order=list(channel_order),
        warnings=list(warnings or ()),
    )


def documented_output_units() -> Tuple[str, str, str]:
    """Return (unit, status, source) from upstream MNE documentation/source."""
    return DOCUMENTED_OUTPUT_UNIT, "documented", DOCUMENTED_OUTPUT_UNIT_SOURCE
