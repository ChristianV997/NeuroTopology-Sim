"""Oriented-complex topology helpers (experimental, synthetic-only)."""

from .hodge_2d import (
    BoundaryCondition,
    BoundaryConditionError,
    CochainComplexError,
    GaugePolicy,
    HodgeError,
    HodgeResult,
    IllConditionedMetricError,
    MetricError,
    MetricType,
    detect_boundary_elements,
    effective_condition_number,
    hodge_decompose,
    validate_cochain_complex,
    validate_edge_metric,
    weighted_inner_product,
    weighted_norm_sq,
)

try:
    from .winding import (
        DEFAULT_TIE_TOL,
        SUPPORTED_WRAP_INTERVALS,
        TWO_PI,
        ChargeMomentResult,
        WindingError,
        WindingResult,
        branch_index_floor,
        charge_moments,
        origin_shifted_moment,
        phase_winding,
        signed_first_moment,
    )
except ImportError:
    pass

__all__ = [
    "BoundaryCondition",
    "BoundaryConditionError",
    "CochainComplexError",
    "GaugePolicy",
    "HodgeError",
    "HodgeResult",
    "IllConditionedMetricError",
    "MetricError",
    "MetricType",
    "detect_boundary_elements",
    "effective_condition_number",
    "hodge_decompose",
    "validate_cochain_complex",
    "validate_edge_metric",
    "weighted_inner_product",
    "weighted_norm_sq",
]
