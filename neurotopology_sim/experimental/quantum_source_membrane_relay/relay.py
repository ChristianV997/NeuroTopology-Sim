"""Fixed gain from event flux (1/s) to dimensionless FHN current offset.

Mapping (identical for quantum and classical arms):

    I_offset(t) = g · φ(t)

where
    φ(t)  : event flux [s⁻¹]
    g     : gain [s]  (so I_offset is dimensionless, matching FHN current units)
    ∫ φ dt = Y  (dimensionless yield)

Classical matched relay: a piecewise-constant flux with the **same** integrated
yield Y and the **same** support duration as the quantum flux window, placed at
the start of the FHN interval (rate = Y / T_support).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class RelayConfig:
    """Unit-explicit flux → current map; ``gain_s`` has units of seconds."""

    gain_s: float = 2.0e-12
    max_abs_offset: float = 5.0

    def __post_init__(self) -> None:
        if not np.isfinite(self.gain_s) or self.gain_s < 0:
            raise ValueError("gain_s must be finite and >= 0")
        if self.max_abs_offset <= 0 or not np.isfinite(self.max_abs_offset):
            raise ValueError("max_abs_offset must be finite and positive")


def event_rate_to_current_offset(
    times_s: np.ndarray,
    event_flux_s: np.ndarray,
    fhn_times_s: np.ndarray,
    config: RelayConfig | None = None,
) -> np.ndarray:
    """Interpolate φ(t) onto FHN times and apply fixed gain g.

    Flux outside the source window is zero. Values are clipped to
    ±max_abs_offset for finite-resource safety (declared clip, not silent).
    """
    cfg = config or RelayConfig()
    t = np.asarray(times_s, dtype=float)
    phi = np.asarray(event_flux_s, dtype=float)
    ft = np.asarray(fhn_times_s, dtype=float)
    if t.ndim != 1 or phi.shape != t.shape or ft.ndim != 1:
        raise ValueError("times/flux must be 1-D and aligned; fhn_times 1-D")
    if not np.all(np.isfinite(t)) or not np.all(np.isfinite(phi)) or not np.all(np.isfinite(ft)):
        raise ValueError("non-finite times or flux")
    if t.size < 2:
        raise ValueError("need at least two source samples")

    # zero outside source support
    phi_on_fhn = np.interp(ft, t, phi, left=0.0, right=0.0)
    offset = cfg.gain_s * phi_on_fhn
    clipped = np.clip(offset, -cfg.max_abs_offset, cfg.max_abs_offset)
    return clipped


def classical_matched_flux(
    yield_dimensionless: float,
    support_duration_s: float,
    fhn_times_s: np.ndarray,
) -> np.ndarray:
    """Constant flux on [0, T_support] with ∫φ dt = Y (matched yield + timing window)."""
    if yield_dimensionless < 0 or not np.isfinite(yield_dimensionless):
        raise ValueError("yield must be finite and >= 0")
    if support_duration_s <= 0 or not np.isfinite(support_duration_s):
        raise ValueError("support_duration_s must be positive")
    ft = np.asarray(fhn_times_s, dtype=float)
    rate = float(yield_dimensionless) / float(support_duration_s)
    return np.where(ft <= support_duration_s, rate, 0.0)
