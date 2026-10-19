"""Geometry helpers for synthetic planar mesh construction and validation."""

from neurotopology_sim.experimental.geometry.planar_triangulation import (
    DegeneracyPolicy,
    PlanarTriangulationResult,
    triangulate_2d,
    validate_planar_mesh,
)

__all__ = [
    "DegeneracyPolicy",
    "PlanarTriangulationResult",
    "triangulate_2d",
    "validate_planar_mesh",
]
