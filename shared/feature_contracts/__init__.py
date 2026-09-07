"""Canonical provenance-rich feature contracts package for NeuroTopology-Sim."""
from __future__ import annotations

from .models import (
    CanonicalFeatureBundle,
    CanonicalFeatureRecord,
    CoordinateStatus,
    EvidenceClass,
    FeatureFamily,
    FrequencyBand,
    TimeWindow,
)
from .serialization import (
    bundle_from_dict,
    bundle_from_json,
    bundle_to_json,
    canonical_sort_key,
    canonical_sort_records,
    compute_bundle_checksum,
    compute_record_checksum,
    record_from_dict,
    record_from_json,
    record_to_json,
)
from .validators import (
    VALID_UNITS,
    FeatureContractValidationError,
    check_feature_compatibility,
    validate_feature_bundle,
    validate_feature_record,
)

__all__ = [
    "CanonicalFeatureRecord",
    "CanonicalFeatureBundle",
    "FeatureFamily",
    "CoordinateStatus",
    "EvidenceClass",
    "FrequencyBand",
    "TimeWindow",
    "VALID_UNITS",
    "FeatureContractValidationError",
    "validate_feature_record",
    "validate_feature_bundle",
    "check_feature_compatibility",
    "canonical_sort_key",
    "canonical_sort_records",
    "compute_record_checksum",
    "compute_bundle_checksum",
    "record_to_json",
    "bundle_to_json",
    "record_from_dict",
    "bundle_from_dict",
    "record_from_json",
    "bundle_from_json",
]
