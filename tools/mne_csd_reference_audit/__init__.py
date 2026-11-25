"""Independent NumPy reference for the MNE-convention average-referenced CSD operator.

Pure NumPy. Never imports MNE. Synthetic montages only. Status: HOLD / SYNTHETIC_ONLY.
"""
from .kkt import csd_operator, apply_csd
from .legendre import g_function, h_function, PROPOSAL_CONSTANTS
from .report import build_report, to_json

__all__ = ["csd_operator", "apply_csd", "g_function", "h_function", "PROPOSAL_CONSTANTS", "build_report", "to_json"]
