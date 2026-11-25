"""Tests for mathematical comparability gates.

Ensures that non-equivalent complexes, filtrations, metrics, coefficient fields,
and thresholds are strictly rejected as NOT_COMPARABLE.
"""
from __future__ import annotations

import pytest

from tools.topology_backend_conformance import (
    CoefficientField,
    ComparabilityStatus,
    ConformanceExecutionConfig,
    FiltrationType,
    MetricConvention,
    NonComparableReason,
    compare_conformance_runs,
    validate_mathematical_comparability,
)


def test_cubical_vs_rips_rejected_as_not_comparable() -> None:
    """Cubical complex (grid sublevel set) vs Vietoris-Rips (distance matrix) are fundamentally non-equivalent."""
    cfg_rips = ConformanceExecutionConfig(
        filtration_type=FiltrationType.VIETORIS_RIPS,
        metric_convention=MetricConvention.PRECOMPUTED_DISTANCE_MATRIX,
        input_identity="fixture_same_name",
    )
    cfg_cubical = ConformanceExecutionConfig(
        filtration_type=FiltrationType.CUBICAL_SUBLEVEL,
        metric_convention=MetricConvention.GRID_SCALAR_SUBLEVEL,
        input_identity="fixture_same_name",
    )

    status, reasons = validate_mathematical_comparability(cfg_rips, cfg_cubical)
    assert status == ComparabilityStatus.NOT_COMPARABLE
    assert any(NonComparableReason.FILTRATION_MISMATCH.value in r for r in reasons)
    assert any(NonComparableReason.METRIC_MISMATCH.value in r for r in reasons)


def test_metric_convention_mismatch_rejected() -> None:
    """Euclidean point cloud vs 1-PLV dissimilarity are different metric spaces."""
    cfg_euclid = ConformanceExecutionConfig(
        filtration_type=FiltrationType.VIETORIS_RIPS,
        metric_convention=MetricConvention.EUCLIDEAN_POINT_CLOUD,
        input_identity="dataset_x",
    )
    cfg_plv = ConformanceExecutionConfig(
        filtration_type=FiltrationType.VIETORIS_RIPS,
        metric_convention=MetricConvention.DISSIMILARITY_ONE_MINUS_PLV,
        input_identity="dataset_x",
    )

    status, reasons = validate_mathematical_comparability(cfg_euclid, cfg_plv)
    assert status == ComparabilityStatus.NOT_COMPARABLE
    assert any(NonComparableReason.METRIC_MISMATCH.value in r for r in reasons)


def test_coefficient_field_mismatch_rejected() -> None:
    """Z_2 homology vs Z_3 homology are distinct algebraic structures."""
    cfg_z2 = ConformanceExecutionConfig(
        filtration_type=FiltrationType.VIETORIS_RIPS,
        metric_convention=MetricConvention.PRECOMPUTED_DISTANCE_MATRIX,
        coefficient_field=CoefficientField.Z2,
        input_identity="fixture_a",
    )
    cfg_z3 = ConformanceExecutionConfig(
        filtration_type=FiltrationType.VIETORIS_RIPS,
        metric_convention=MetricConvention.PRECOMPUTED_DISTANCE_MATRIX,
        coefficient_field=CoefficientField.Z3,
        input_identity="fixture_a",
    )

    status, reasons = validate_mathematical_comparability(cfg_z2, cfg_z3)
    assert status == ComparabilityStatus.NOT_COMPARABLE
    assert any(NonComparableReason.COEFFICIENT_FIELD_MISMATCH.value in r for r in reasons)


def test_threshold_truncation_mismatch_rejected() -> None:
    """Unbounded filtration vs threshold-truncated filtration cannot be directly compared."""
    cfg_unbounded = ConformanceExecutionConfig(
        filtration_type=FiltrationType.VIETORIS_RIPS,
        metric_convention=MetricConvention.PRECOMPUTED_DISTANCE_MATRIX,
        threshold=None,
        input_identity="square_fixture",
    )
    cfg_bounded = ConformanceExecutionConfig(
        filtration_type=FiltrationType.VIETORIS_RIPS,
        metric_convention=MetricConvention.PRECOMPUTED_DISTANCE_MATRIX,
        threshold=1.2,
        input_identity="square_fixture",
    )

    status, reasons = validate_mathematical_comparability(cfg_unbounded, cfg_bounded)
    assert status == ComparabilityStatus.NOT_COMPARABLE
    assert any(NonComparableReason.THRESHOLD_TRUNCATION_MISMATCH.value in r for r in reasons)


def test_input_identity_mismatch_rejected() -> None:
    """Different inputs cannot be asserted as conforming."""
    cfg_1 = ConformanceExecutionConfig(
        filtration_type=FiltrationType.VIETORIS_RIPS,
        metric_convention=MetricConvention.PRECOMPUTED_DISTANCE_MATRIX,
        input_identity="triangle_equilateral",
    )
    cfg_2 = ConformanceExecutionConfig(
        filtration_type=FiltrationType.VIETORIS_RIPS,
        metric_convention=MetricConvention.PRECOMPUTED_DISTANCE_MATRIX,
        input_identity="square_unit",
    )

    status, reasons = validate_mathematical_comparability(cfg_1, cfg_2)
    assert status == ComparabilityStatus.NOT_COMPARABLE
    assert any(NonComparableReason.INPUT_IDENTITY_MISMATCH.value in r for r in reasons)


def test_identical_configurations_accepted_as_comparable() -> None:
    """Identical configurations pass comparability verification."""
    cfg_a = ConformanceExecutionConfig(
        filtration_type=FiltrationType.VIETORIS_RIPS,
        metric_convention=MetricConvention.PRECOMPUTED_DISTANCE_MATRIX,
        coefficient_field=CoefficientField.Z2,
        threshold=2.0,
        input_identity="same_input",
    )
    cfg_b = ConformanceExecutionConfig(
        filtration_type=FiltrationType.VIETORIS_RIPS,
        metric_convention=MetricConvention.PRECOMPUTED_DISTANCE_MATRIX,
        coefficient_field=CoefficientField.Z2,
        threshold=2.0,
        input_identity="same_input",
    )

    status, reasons = validate_mathematical_comparability(cfg_a, cfg_b)
    assert status == ComparabilityStatus.COMPARABLE
    assert len(reasons) == 0
