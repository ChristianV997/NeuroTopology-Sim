"""Unit tests for TDA pairwise equivalence and disagreement detection."""
from __future__ import annotations

import pytest

from tools.tda_reproducibility.equivalence import (
    compare_backend_diagrams,
    compute_bottleneck_distance,
)
from tools.tda_reproducibility.types import PersistenceInterval


def test_equivalence_identical_diagrams():
    ivs_a = [
        PersistenceInterval(dimension=1, birth=0.5, death=1.5),
        PersistenceInterval(dimension=1, birth=0.8, death=2.0),
    ]
    ivs_b = [
        PersistenceInterval(dimension=1, birth=0.5, death=1.5),
        PersistenceInterval(dimension=1, birth=0.8, death=2.0),
    ]
    comp = compare_backend_diagrams("backend_a", "backend_b", ivs_a, ivs_b, dimension=1)
    assert comp.equivalent is True
    assert comp.bottleneck_distance == 0.0
    assert comp.max_interval_diff == 0.0
    assert comp.disagreement_reason is None


def test_equivalence_within_tolerance():
    ivs_a = [PersistenceInterval(dimension=1, birth=0.5, death=1.5)]
    ivs_b = [PersistenceInterval(dimension=1, birth=0.50001, death=1.50001)]
    comp = compare_backend_diagrams(
        "backend_a", "backend_b", ivs_a, ivs_b, dimension=1, tolerance=1e-4
    )
    assert comp.equivalent is True
    assert comp.bottleneck_distance is not None
    assert comp.bottleneck_distance <= 1e-4


def test_equivalence_count_mismatch():
    ivs_a = [
        PersistenceInterval(dimension=1, birth=0.5, death=1.5),
    ]
    ivs_b = [
        PersistenceInterval(dimension=1, birth=0.5, death=1.5),
        PersistenceInterval(dimension=1, birth=1.0, death=2.0),
    ]
    comp = compare_backend_diagrams("backend_a", "backend_b", ivs_a, ivs_b, dimension=1)
    assert comp.equivalent is False
    assert comp.disagreement_reason is not None
    assert "Interval count mismatch" in comp.disagreement_reason


def test_equivalence_infinity_mismatch():
    ivs_a = [PersistenceInterval(dimension=0, birth=0.0, death=None)]
    ivs_b = [PersistenceInterval(dimension=0, birth=0.0, death=10.0)]
    comp = compare_backend_diagrams("backend_a", "backend_b", ivs_a, ivs_b, dimension=0)
    assert comp.equivalent is False
    assert "Infinity mismatch" in comp.disagreement_reason


def test_equivalence_value_disagreement_exceeds_tolerance():
    ivs_a = [PersistenceInterval(dimension=1, birth=0.5, death=1.5)]
    ivs_b = [PersistenceInterval(dimension=1, birth=0.5, death=2.5)]
    comp = compare_backend_diagrams(
        "backend_a", "backend_b", ivs_a, ivs_b, dimension=1, tolerance=1e-4
    )
    assert comp.equivalent is False
    assert comp.disagreement_reason is not None
    assert "exceeds tolerance" in comp.disagreement_reason
