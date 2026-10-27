"""Minimal cellular-sheaf → scalar-edge readout benchmark.

This package is a mathematical testbed only. It does **not** model neural
dynamics, physiological EMF, or thermodynamic coupling. Exactness of sheaf
cochains, scalar CTMC cycle affinities, and physical work/EMF remain distinct.
"""

from .sheaf import (
    CellularSheaf,
    Edge,
    LinearReadout,
    is_endpoint_compatible,
    sheaf_coboundary,
    scalarize_edge_cochain,
)
from .triangle_example import run_canonical_triangle

__all__ = [
    "CellularSheaf",
    "Edge",
    "LinearReadout",
    "is_endpoint_compatible",
    "sheaf_coboundary",
    "scalarize_edge_cochain",
    "run_canonical_triangle",
]
