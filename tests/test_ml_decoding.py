"""Synthetic ground-truth tests for analysis/ml_decoding.py -- cross-
validated logistic-regression decoding with a real permutation-test null,
proving the instrument catches genuine class-separating structure and does
NOT falsely flag pure noise as significant.
"""
from __future__ import annotations

import numpy as np
import pytest

from analysis.ml_decoding import build_decoding_report, build_feature_matrix, evaluate_decoding


# ---------------------------------------------------------------------------
# build_feature_matrix
# ---------------------------------------------------------------------------

def test_build_feature_matrix_auto_selects_shared_numeric_keys():
    rows = [
        {"a": 1.0, "b": 2.0, "label": "x"},
        {"a": 3.0, "b": 4.0, "label": "y"},
    ]
    X, names, kept = build_feature_matrix(rows)
    assert names == ["a", "b"]
    assert X.shape == (2, 2)
    assert kept == [0, 1]


def test_build_feature_matrix_drops_rows_with_missing_or_nonfinite_values():
    rows = [
        {"a": 1.0, "b": 2.0},
        {"a": float("nan"), "b": 4.0},
        {"a": 5.0, "b": 6.0},
    ]
    X, names, kept = build_feature_matrix(rows, feature_keys=["a", "b"])
    assert kept == [0, 2]
    assert X.shape == (2, 2)


def test_build_feature_matrix_empty_input():
    X, names, kept = build_feature_matrix([])
    assert X.shape == (0, 0)
    assert names == []
    assert kept == []


# ---------------------------------------------------------------------------
# evaluate_decoding -- the ground-truth ability-to-detect-signal tests
# ---------------------------------------------------------------------------

def test_decoding_detects_genuine_class_separation():
    """Two clearly separated Gaussian blobs must decode well above chance
    with a significant permutation p-value -- the textbook case this
    instrument exists to catch."""
    rng = np.random.default_rng(0)
    n_per_class = 30
    X = np.vstack([rng.normal(0, 1, size=(n_per_class, 2)), rng.normal(3, 1, size=(n_per_class, 2))])
    y = np.array([0] * n_per_class + [1] * n_per_class)

    result = evaluate_decoding(X, y, seed=0, n_permutations=200, cv_folds=5)
    assert result["status"] == "computed"
    assert result["accuracy"] > 0.8
    assert result["p_value"] < 0.05


def test_decoding_does_not_falsely_flag_pure_noise():
    """Identically-distributed features for both classes must NOT decode
    above chance with a significant p-value -- the null case, proving this
    instrument doesn't manufacture false positives on its own."""
    rng = np.random.default_rng(1)
    n_per_class = 30
    X = rng.normal(0, 1, size=(n_per_class * 2, 2))
    y = np.array([0] * n_per_class + [1] * n_per_class)

    result = evaluate_decoding(X, y, seed=0, n_permutations=200, cv_folds=5)
    assert result["status"] == "computed"
    assert result["p_value"] > 0.05


def test_decoding_reports_insufficient_data_for_small_classes():
    X = np.random.default_rng(2).standard_normal((6, 2))
    y = np.array([0, 0, 0, 1, 1, 1])
    result = evaluate_decoding(X, y, cv_folds=5)
    assert result["status"] == "insufficient_data"


def test_decoding_not_applicable_for_more_than_two_classes():
    X = np.random.default_rng(3).standard_normal((30, 2))
    y = np.array([0, 1, 2] * 10)
    result = evaluate_decoding(X, y, cv_folds=5)
    assert result["status"] == "not_applicable"


def test_decoding_chance_level_matches_majority_class_fraction():
    rng = np.random.default_rng(4)
    X = rng.standard_normal((50, 2))
    y = np.array([0] * 35 + [1] * 15)
    result = evaluate_decoding(X, y, seed=0, n_permutations=50, cv_folds=5)
    assert result["chance_level"] == pytest.approx(35 / 50)


# ---------------------------------------------------------------------------
# build_decoding_report (integration)
# ---------------------------------------------------------------------------

def test_build_decoding_report_end_to_end_with_signal():
    rng = np.random.default_rng(5)
    n_per_class = 25
    class0 = [{"feat_a": float(v), "feat_b": float(v * 2)} for v in rng.normal(0, 1, n_per_class)]
    class1 = [{"feat_a": float(v), "feat_b": float(v * 2)} for v in rng.normal(4, 1, n_per_class)]
    feature_dicts = class0 + class1
    labels = ["state_a"] * n_per_class + ["state_b"] * n_per_class

    report = build_decoding_report(feature_dicts, labels, seed=0, n_permutations=200, cv_folds=5)
    assert report["status"] == "computed"
    assert report["feature_names"] == ["feat_a", "feat_b"]
    assert report["accuracy"] > 0.7
    assert report["n_rows_dropped"] == 0
