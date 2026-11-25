"""Explicit engineering warning helpers for adversarial validation."""
from __future__ import annotations

from typing import List


WARN_TRIADIC_GAIN_GONE_AFTER_CONFOUND = (
    "WARNING: triadic gain disappears after common-driver / confound control"
)
WARN_TRISPECTRAL_GAIN_GONE_UNDER_SURROGATES = (
    "WARNING: trispectral/higher-order spectral gain disappears under surrogates"
)
WARN_TOPOLOGY_NO_INFO_BEYOND_SPECTRA = (
    "WARNING: topology adds no information beyond spectra under these synthetic controls"
)
WARN_GAIN_TRAINING_ONLY = (
    "WARNING: apparent gain is training-only; held-out subject shows no transfer"
)
WARN_SAMPLE_SIZE_INADEQUATE = (
    "WARNING: sample size is inadequate for stable higher-order estimates"
)
WARN_MULTIPLE_COMPARISONS_UNRESOLVED = (
    "WARNING: multiple comparisons are unresolved; do not treat probe hits as discoveries"
)


def default_suite_warnings() -> List[str]:
    return [WARN_MULTIPLE_COMPARISONS_UNRESOLVED]
