"""Parametric GNEB-like energy landscape and thermodynamic drag."""
from dataclasses import dataclass
import numpy as np

from .pitnn_constants import PITNNConstants


@dataclass(frozen=True)
class GNEBConfig:
    n_images: int = 32
    defect_charge: int = 1
    curvature: float = 1.0
    meditative_flattening: float = 0.0
    metabolic_scale_W: float = 1e-12


def calculate_gneb_well(cfg: GNEBConfig = GNEBConfig(), constants: PITNNConstants | None = None) -> dict:
    """Calculate a reproducible 1-D energy path and its barrier.

    This is a local surrogate, not an invocation of the Spirit executable.
    ``meditative_flattening`` is clipped to [0, 1] and reduces curvature.
    """
    constants = constants or PITNNConstants()
    if cfg.n_images < 3 or cfg.defect_charge < 0 or cfg.metabolic_scale_W < 0:
        raise ValueError("invalid GNEB parameters")
    flattening = float(np.clip(cfg.meditative_flattening, 0.0, 1.0))
    x = np.linspace(-1.0, 1.0, cfg.n_images)
    curvature = cfg.curvature * (1.0 - flattening)
    barrier = constants.topological_barrier_J * max(cfg.defect_charge, 1)
    energy = barrier * (1.0 - x * x) + 0.5 * curvature * constants.thermal_energy_J * x * x
    hessian_eigenvalue = curvature * constants.thermal_energy_J
    drag_W = cfg.metabolic_scale_W * abs(cfg.defect_charge) * (1.0 + curvature)
    return {
        "topological_barrier_J": float(barrier),
        "topological_barrier_eV": float(barrier / constants.eV),
        "dot_Sigma_W": float(drag_W),
        "hessian_min_eigenvalue": float(hessian_eigenvalue),
        "exceptional_point_proxy": bool(abs(hessian_eigenvalue) < 1e-30),
        "energy_path_J": energy.tolist(),
        "external_solver": "not_run",
    }
