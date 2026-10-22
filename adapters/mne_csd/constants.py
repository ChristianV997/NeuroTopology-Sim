"""Documented MNE CSD API defaults and provenance labels.

Defaults match ``mne.preprocessing.compute_current_source_density`` as
documented for MNE-Python ≥ 1.4 (project EEG profile) / verified against
stable docs for MNE 1.13.2:

https://mne.tools/stable/generated/mne.preprocessing.compute_current_source_density.html

These are API defaults from upstream documentation, not independently
derived scientific constants and not Round-4/5 proposal pins.
"""
from __future__ import annotations

from typing import Final, Tuple

# Upstream API defaults (MNE docs / mne/preprocessing/_csd.py).
DEFAULT_LAMBDA2: Final[float] = 1e-5
DEFAULT_STIFFNESS: Final[float] = 4.0
DEFAULT_N_LEGENDRE_TERMS: Final[int] = 50
DEFAULT_SPHERE: Final[str] = "auto"
DEFAULT_COPY: Final[bool] = True

# Supported project dependency floor from requirements-eeg.txt.
SUPPORTED_MNE_MIN_VERSION: Final[str] = "1.4.0"

# Upstream project license (BSD-3-Clause).
MNE_LICENSE: Final[str] = "BSD-3-Clause"
MNE_LICENSE_URL: Final[str] = "https://github.com/mne-tools/mne-python/blob/main/LICENSE.txt"
MNE_API_DOC_URL: Final[str] = (
    "https://mne.tools/stable/generated/mne.preprocessing.compute_current_source_density.html"
)
MNE_SOURCE_URL: Final[str] = "https://github.com/mne-tools/mne-python/blob/main/mne/preprocessing/_csd.py"

# MNE sets CSD channel unit to V/m² (FIFF_UNIT_V_M2) in _csd.py after transform.
DOCUMENTED_OUTPUT_UNIT: Final[str] = "V/m^2"
DOCUMENTED_OUTPUT_UNIT_SOURCE: Final[str] = (
    "mne.preprocessing._csd.compute_current_source_density assigns "
    "FIFF.FIFF_UNIT_V_M2 to transformed EEG channels"
)

TRANSFORM_KIND: Final[str] = "sensor_space_surface_laplacian_csd"
NOT_SOURCE_LOCALIZATION: Final[str] = (
    "This transform is a sensor-space spherical-spline surface Laplacian "
    "(current source density). It is not anatomical source localization "
    "(e.g. MNE/dSPM/eLORETA/beamformer) and must not be described as such."
)

REQUIRED_API_PARAMS: Final[Tuple[str, ...]] = (
    "sphere",
    "lambda2",
    "stiffness",
    "n_legendre_terms",
    "copy",
)
