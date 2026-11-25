"""Simplicial phase cochain and weighted Hodge decomposition reference implementation.

This package provides an experimental, standalone reference implementation
for discrete differential forms, phase cochains, exact integer topological
charges, and weighted Hodge-Helmholtz decompositions on simplicial complexes.
"""

from .complex import SimplicialComplex
from .cochain import (
    ChargeMomentSummary,
    Wrapped1Cochain,
    compute_charge_moments,
    compute_confidence_weighted_scores,
    compute_topological_charges,
    compute_triangle_loop_winding,
    compute_wrapped_1_cochain,
    wrap_to_pi,
)
from .fixtures import (
    build_annulus_fixture,
    build_dipole_complex_fixture,
    build_single_triangle_fixture,
    build_vortex_quad_fixture,
)
from .hodge import HodgeDecomposition, compute_weighted_hodge_decomposition

__all__ = [
    "ChargeMomentSummary",
    "HodgeDecomposition",
    "SimplicialComplex",
    "Wrapped1Cochain",
    "build_annulus_fixture",
    "build_dipole_complex_fixture",
    "build_single_triangle_fixture",
    "build_vortex_quad_fixture",
    "compute_charge_moments",
    "compute_confidence_weighted_scores",
    "compute_topological_charges",
    "compute_triangle_loop_winding",
    "compute_weighted_hodge_decomposition",
    "compute_wrapped_1_cochain",
    "wrap_to_pi",
]
