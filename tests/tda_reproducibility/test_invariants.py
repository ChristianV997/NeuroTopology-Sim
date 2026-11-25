"""Unit tests for TDA mathematical and operational invariants."""
from __future__ import annotations

import numpy as np
import pytest

from tools.tda_reproducibility.fixtures import make_circle_fixture
from tools.tda_reproducibility.invariants import (
    verify_bounded_point_capacity,
    verify_deterministic_repeated_checksum,
    verify_distance_matrix_symmetry,
    verify_finite_intervals,
    verify_node_reordering_invariance,
    verify_spatial_charge_isolation,
    verify_zero_diagonal,
)
from tools.tda_reproducibility.runners import RipserRunner
from tools.tda_reproducibility.types import PersistenceInterval


def test_verify_distance_matrix_symmetry_valid():
    D = np.array([
        [0.0, 1.2, 2.5],
        [1.2, 0.0, 1.8],
        [2.5, 1.8, 0.0],
    ])
    res = verify_distance_matrix_symmetry(D)
    assert res.passed is True
    assert res.metrics["max_asymmetry"] <= 1e-8


def test_verify_distance_matrix_symmetry_invalid_asymmetric():
    D = np.array([
        [0.0, 1.0],
        [2.0, 0.0],
    ])
    res = verify_distance_matrix_symmetry(D)
    assert res.passed is False
    assert "asymmetry" in res.details.lower()


def test_verify_distance_matrix_symmetry_invalid_shape_or_nan():
    D_rect = np.zeros((3, 4))
    res = verify_distance_matrix_symmetry(D_rect)
    assert res.passed is False

    D_nan = np.zeros((3, 3))
    D_nan[0, 1] = np.nan
    res_nan = verify_distance_matrix_symmetry(D_nan)
    assert res_nan.passed is False


def test_verify_distance_matrix_symmetry_negative():
    D_neg = np.array([
        [0.0, -1.0],
        [-1.0, 0.0],
    ])
    res = verify_distance_matrix_symmetry(D_neg)
    assert res.passed is False


def test_verify_zero_diagonal():
    D_ok = np.zeros((3, 3))
    assert verify_zero_diagonal(D_ok).passed is True

    D_bad = np.eye(3)
    res = verify_zero_diagonal(D_bad)
    assert res.passed is False
    assert res.metrics["max_diagonal"] == 1.0


def test_verify_finite_intervals():
    valid = [
        PersistenceInterval(dimension=0, birth=0.0, death=1.5),
        PersistenceInterval(dimension=0, birth=0.0, death=None),
        PersistenceInterval(dimension=1, birth=0.5, death=2.0),
    ]
    assert verify_finite_intervals(valid).passed is True

    invalid_birth = [
        PersistenceInterval(dimension=0, birth=-0.5, death=1.0)
    ]
    assert verify_finite_intervals(invalid_birth).passed is False

    death_before_birth = [
        PersistenceInterval(dimension=1, birth=2.0, death=1.0)
    ]
    assert verify_finite_intervals(death_before_birth).passed is False


def test_verify_node_reordering_invariance():
    fix = make_circle_fixture(n_points=8)
    runner = RipserRunner()
    res = verify_node_reordering_invariance(runner.run, fix.distance_matrix, seed=123)
    assert res.passed is True
    assert res.metrics["checksum_match"] is True


def test_verify_bounded_point_capacity():
    assert verify_bounded_point_capacity(50, max_points_bound=100).passed is True
    assert verify_bounded_point_capacity(150, max_points_bound=100).passed is False


def test_verify_spatial_charge_isolation():
    clean_payload = {
        "beta_1": 2,
        "spatial_charge": 1.0,
        "metadata": {"provenance": "synthetic"},
    }
    assert verify_spatial_charge_isolation(clean_payload).passed is True

    # Test forbidden conflation keys
    forbidden_keys = [
        {"beta_1_charge": 1},
        {"spatial_beta_1": 1},
        {"graph_vortex_charge": 1},
        {"q_from_beta_1": 1},
    ]
    for bad_payload in forbidden_keys:
        res = verify_spatial_charge_isolation(bad_payload)
        assert res.passed is False, f"Expected failure on {bad_payload}"

    # Test exact same reference object
    shared_obj = [1]
    aliased_payload = {
        "beta_1": shared_obj,
        "spatial_charge": shared_obj,
    }
    assert verify_spatial_charge_isolation(aliased_payload).passed is False


def test_verify_deterministic_repeated_checksum():
    fix = make_circle_fixture(n_points=6)
    runner = RipserRunner()
    res = verify_deterministic_repeated_checksum(runner.run, fix.distance_matrix, repetitions=3)
    assert res.passed is True
    assert res.metrics["unique_checksums"] == 1
