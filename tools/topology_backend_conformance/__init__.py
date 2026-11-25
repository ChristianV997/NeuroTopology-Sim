"""TDA backend semantic conformance harness for NeuroTopology-Sim.

Provides:
- Mathematical comparability checks preventing false equivalences.
- Strict NOT_COMPARABLE status for non-equivalent complexes/filtrations.
- Deterministic synthetic fixtures with analytical ground-truth expectations.
- Adapters for ReferenceSimplicialEngine, Ripser, GUDHI, and repository modules.
- Complete offline capability and graceful fallback when optional packages are absent.
"""
from __future__ import annotations

from .models import (
    BackendExecutionResult,
    BackendMetadata,
    CoefficientField,
    ComparabilityStatus,
    ConformanceComparisonResult,
    ConformanceExecutionConfig,
    FiltrationType,
    MetricConvention,
    NonComparableReason,
    PersistenceBar,
)
from .reference_engine import (
    compute_euclidean_distance_matrix,
    compute_vietoris_rips_reference,
)
from .fixtures import (
    ConformanceFixture,
    get_all_conformance_fixtures,
    make_cubical_annulus_loop_fixture,
    make_cubical_flat_grid_fixture,
    make_disconnected_components_fixture,
    make_duplicate_points_fixture,
    make_empty_fixture,
    make_filled_triangle_fixture,
    make_known_loop_fixture,
    make_reordered_fixture,
    make_single_point_fixture,
    make_threshold_boundary_fixture,
)
from .adapters import (
    BaseTDAAdapter,
    GudhiCubicalAdapter,
    GudhiRipsAdapter,
    ReferenceSimplicialAdapter,
    RipserAdapter,
    get_all_adapters,
    is_module_installed,
)
from .comparator import (
    compute_bottleneck_distance_exact,
    compare_conformance_runs,
    validate_mathematical_comparability,
)

__all__ = [
    "BackendExecutionResult",
    "BackendMetadata",
    "BaseTDAAdapter",
    "CoefficientField",
    "ComparabilityStatus",
    "ConformanceComparisonResult",
    "ConformanceExecutionConfig",
    "ConformanceFixture",
    "FiltrationType",
    "GudhiCubicalAdapter",
    "GudhiRipsAdapter",
    "MetricConvention",
    "NonComparableReason",
    "PersistenceBar",
    "ReferenceSimplicialAdapter",
    "RipserAdapter",
    "compare_conformance_runs",
    "compute_bottleneck_distance_exact",
    "compute_euclidean_distance_matrix",
    "compute_vietoris_rips_reference",
    "get_all_adapters",
    "get_all_conformance_fixtures",
    "is_module_installed",
    "make_cubical_annulus_loop_fixture",
    "make_cubical_flat_grid_fixture",
    "make_disconnected_components_fixture",
    "make_duplicate_points_fixture",
    "make_empty_fixture",
    "make_filled_triangle_fixture",
    "make_known_loop_fixture",
    "make_reordered_fixture",
    "make_single_point_fixture",
    "make_threshold_boundary_fixture",
    "validate_mathematical_comparability",
]
