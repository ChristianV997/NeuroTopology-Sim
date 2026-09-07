"""Deterministic null-calibration framework.

Synthetic and control calibrations never emit a scientific PASS and never
modify Bayes-factor or falsification verdicts.
"""

from .calibrate import calibrate, calibrate_payload
from .models import NULL_MODELS
from .schema import CALIBRATION_STATUS, METRIC_FAMILIES

__all__ = [
    "NULL_MODELS",
    "METRIC_FAMILIES",
    "CALIBRATION_STATUS",
    "calibrate",
    "calibrate_payload",
]
