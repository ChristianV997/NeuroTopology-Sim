"""MNE current-source-density (CSD) adapter.

Thin engineering wrapper around
``mne.preprocessing.compute_current_source_density`` with explicit channel
selection, fail-closed montage preconditions, and provenance metadata.

This package does **not** implement anatomical source localization and does
not make scientific, clinical, or consciousness claims.
"""
from __future__ import annotations

from .constants import (
    DEFAULT_COPY,
    DEFAULT_LAMBDA2,
    DEFAULT_N_LEGENDRE_TERMS,
    DEFAULT_SPHERE,
    DEFAULT_STIFFNESS,
    DOCUMENTED_OUTPUT_UNIT,
    MNE_API_DOC_URL,
    MNE_LICENSE,
    SUPPORTED_MNE_MIN_VERSION,
    TRANSFORM_KIND,
)
from .errors import (
    CSDAdapterError,
    InvalidChannelSelectionError,
    MissingCoordinatesError,
    MNEUnavailableError,
    ReferenceMutationError,
)
from .preconditions import (
    extract_channel_inventory,
    reject_reference_mutation,
    validate_channel_selection,
)
from .provenance import CSDProvenance
from .transform import (
    CSDResult,
    apply_csd,
    get_mne_version,
    inspect_preconditions,
    mne_available,
)

__all__ = [
    "DEFAULT_COPY",
    "DEFAULT_LAMBDA2",
    "DEFAULT_N_LEGENDRE_TERMS",
    "DEFAULT_SPHERE",
    "DEFAULT_STIFFNESS",
    "DOCUMENTED_OUTPUT_UNIT",
    "MNE_API_DOC_URL",
    "MNE_LICENSE",
    "SUPPORTED_MNE_MIN_VERSION",
    "TRANSFORM_KIND",
    "CSDAdapterError",
    "InvalidChannelSelectionError",
    "MissingCoordinatesError",
    "MNEUnavailableError",
    "ReferenceMutationError",
    "CSDProvenance",
    "CSDResult",
    "apply_csd",
    "extract_channel_inventory",
    "get_mne_version",
    "inspect_preconditions",
    "mne_available",
    "reject_reference_mutation",
    "validate_channel_selection",
]
