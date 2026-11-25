"""FHN integration with a fixed voltage calibration (no per-trajectory rescaling).

Dimensionless FHN:

    dv/dt = v - v³/3 - w + I₀ + I_offset(t)
    dw/dt = 0.08 (v + 0.7 - 0.8 w)

Fixed affine map (shared by all arms):

    V(t) [V] = V_rest + S · v(t)

where V_rest and S are constant calibration parameters. This deliberately
avoids ``simulate_fhn``'s per-run min–max normalisation, which would erase
cross-condition amplitude differences.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Optional

import numpy as np


@dataclass(frozen=True)
class FixedFHNCalibration:
    """Fixed time/amplitude calibration applied identically to every arm."""

    duration_s: float = 0.02
    dt_s: float = 1.0e-5
    input_current: float = 1.2
    resting_potential_V: float = -0.070
    volts_per_dimensionless_v: float = 0.030
    threshold_V: float = -0.020
    max_steps: int = 200_000

    def __post_init__(self) -> None:
        if self.duration_s <= 0 or self.dt_s <= 0:
            raise ValueError("duration_s and dt_s must be positive")
        n = int(np.floor(self.duration_s / self.dt_s)) + 1
        if n > self.max_steps:
            raise ValueError(f"FHN step count {n} exceeds max_steps={self.max_steps}")
        if not np.isfinite(self.volts_per_dimensionless_v) or self.volts_per_dimensionless_v == 0:
            raise ValueError("volts_per_dimensionless_v must be finite and nonzero")


def integrate_fhn_fixed_calibration(
    calibration: FixedFHNCalibration | None = None,
    current_offset: Optional[np.ndarray] = None,
) -> Dict[str, Any]:
    """Integrate FHN with optional dimensionless current offset of shape (n_times,)."""
    cal = calibration or FixedFHNCalibration()
    times = np.arange(0.0, cal.duration_s + cal.dt_s / 2.0, cal.dt_s)
    n = times.size
    if current_offset is None:
        offset = np.zeros(n, dtype=float)
    else:
        offset = np.asarray(current_offset, dtype=float).reshape(-1)
        if offset.shape != (n,) or not np.all(np.isfinite(offset)):
            raise ValueError("current_offset must be finite with one value per FHN time sample")

    state = np.array([-1.0, -0.6], dtype=float)
    traj = np.empty((n, 2), dtype=float)

    def rhs(value: np.ndarray, i_off: float) -> np.ndarray:
        v, w = value
        return np.array(
            [
                v - v**3 / 3.0 - w + cal.input_current + i_off,
                0.08 * (v + 0.7 - 0.8 * w),
            ]
        )

    for i in range(n):
        traj[i] = state
        k1 = rhs(state, offset[i])
        k2 = rhs(state + 0.5 * cal.dt_s * k1, offset[i])
        k3 = rhs(state + 0.5 * cal.dt_s * k2, offset[i])
        k4 = rhs(state + cal.dt_s * k3, offset[i])
        state = state + (cal.dt_s / 6.0) * (k1 + 2 * k2 + 2 * k3 + k4)

    v = traj[:, 0]
    voltage = cal.resting_potential_V + cal.volts_per_dimensionless_v * v
    crossing = float(np.mean(voltage >= cal.threshold_V))
    return {
        "times_s": times,
        "v_dimensionless": v,
        "w_dimensionless": traj[:, 1],
        "voltage_V": voltage,
        "current_offset_dimensionless": offset,
        "threshold_crossing_fraction": crossing,
        "calibration": {
            "duration_s": cal.duration_s,
            "dt_s": cal.dt_s,
            "input_current": cal.input_current,
            "resting_potential_V": cal.resting_potential_V,
            "volts_per_dimensionless_v": cal.volts_per_dimensionless_v,
            "threshold_V": cal.threshold_V,
            "note": "fixed_affine_shared_across_arms",
        },
        "finite": bool(np.all(np.isfinite(voltage))),
    }
