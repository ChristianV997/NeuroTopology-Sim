"""Closed vocabularies and result types for the in-memory MNE signal-block boundary."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Mapping, Sequence

SCHEMA_VERSION = "MNE.InMemorySignalBlock.v1"

# MNE-Python is BSD-3-Clause (Copyright 2011-2025 MNE-Python authors).
# Documented Info keys used for optional extraction (stable docs, mne.Info):
# ch_names, chs[].kind/unit/unit_mul/loc, sfreq, bads, meas_date, highpass,
# lowpass, description, custom_ref_applied. We never invent missing fields.
MNE_LICENSE = "BSD-3-Clause"
MNE_DOCS_REF = "https://mne.tools/stable/generated/mne.Info.html"
MNE_LICENSE_REF = "https://github.com/mne-tools/mne-python/blob/main/LICENSE.txt"


class BlockStatus(str, Enum):
    CONVERTED = "converted"
    INCONCLUSIVE = "inconclusive"
    REJECTED = "rejected"
    ERROR = "error"


class ReasonCode(str, Enum):
    OK = "OK"
    EMPTY_BLOCK = "EMPTY_BLOCK"
    SHAPE_MISMATCH = "SHAPE_MISMATCH"
    NON_FINITE_VALUES = "NON_FINITE_VALUES"
    CHANNEL_ORDER_MISMATCH = "CHANNEL_ORDER_MISMATCH"
    MISSING_UNITS = "MISSING_UNITS"
    MISSING_REFERENCE = "MISSING_REFERENCE"
    MISSING_MONTAGE = "MISSING_MONTAGE"
    UNSUPPORTED_CHANNEL_TYPE = "UNSUPPORTED_CHANNEL_TYPE"
    EVENT_ALIGNMENT_MISMATCH = "EVENT_ALIGNMENT_MISMATCH"
    INPUT_MUTATION_FORBIDDEN = "INPUT_MUTATION_FORBIDDEN"
    MNE_UNAVAILABLE = "MNE_UNAVAILABLE"
    AMBIGUOUS_METADATA = "AMBIGUOUS_METADATA"
    MALFORMED_INPUT = "MALFORMED_INPUT"


# Types we will carry through without remapping. Anything else is unsupported
# unless the caller explicitly lists it in allow_channel_types.
DEFAULT_SUPPORTED_CHANNEL_TYPES = frozenset(
    {"eeg", "eog", "ecg", "emg", "stim", "misc", "seeg", "ecog", "dbs", "unknown"}
)


@dataclass(frozen=True)
class CanonicalInMemorySignalBlock:
    """Canonical in-memory block. Arrays are copied; originals are not mutated."""

    schema_version: str
    status: BlockStatus
    reason_codes: tuple[str, ...]
    channel_names: tuple[str, ...]
    channel_types: tuple[str | None, ...]
    units: tuple[str | None, ...]
    sample_rate_hz: float | None
    time_origin: str | None
    block_start_sample: int | None
    block_end_sample: int | None
    n_channels: int
    n_samples: int
    data_shape: tuple[int, ...]
    bad_channels: tuple[str, ...]
    events: tuple[Mapping[str, Any], ...]
    annotations: tuple[Mapping[str, Any], ...]
    reference: str | None
    montage_name: str | None
    montage_coordinates: tuple[tuple[float, float, float] | None, ...] | None
    preprocessing_history: tuple[str, ...]
    source_id: str | None
    source_sha256: str | None
    checksum_state: str
    scientific_pass: bool
    data: Any | None = None  # optional numeric array copy; never required for metadata JSON
    warnings: tuple[str, ...] = ()
    mne_available: bool = False
    mne_version: str | None = None
    limitation: str = (
        "Successful conversion is engineering conformance only, not scientific validity."
    )

    def metadata_dict(self, *, include_data: bool = False) -> dict[str, Any]:
        payload = asdict(self)
        if not include_data:
            payload["data"] = None
        payload["status"] = self.status.value
        payload["data_shape"] = list(self.data_shape)
        payload["channel_names"] = list(self.channel_names)
        payload["channel_types"] = list(self.channel_types)
        payload["units"] = list(self.units)
        payload["bad_channels"] = list(self.bad_channels)
        payload["events"] = [dict(item) for item in self.events]
        payload["annotations"] = [dict(item) for item in self.annotations]
        payload["preprocessing_history"] = list(self.preprocessing_history)
        payload["reason_codes"] = list(self.reason_codes)
        payload["warnings"] = list(self.warnings)
        if self.montage_coordinates is not None:
            payload["montage_coordinates"] = [
                None if row is None else list(row) for row in self.montage_coordinates
            ]
        payload["scientific_pass"] = False
        return payload


@dataclass(frozen=True)
class ConversionResult:
    block: CanonicalInMemorySignalBlock
    input_fingerprint: str
    mutated_input: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "input_fingerprint": self.input_fingerprint,
            "mutated_input": self.mutated_input,
            "block": self.block.metadata_dict(include_data=False),
            "scientific_pass": False,
        }
