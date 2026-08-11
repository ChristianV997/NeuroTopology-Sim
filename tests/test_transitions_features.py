"""Tests for transitions.features — the canonical feature namespace validator."""
from __future__ import annotations

import pytest

from transitions.features import (
    CANONICAL_FEATURES,
    FeatureNameError,
    is_restricted_feature,
    validate_feature_name,
    validate_feature_names,
    validate_feature_names_or_raise,
)


@pytest.mark.parametrize("name", sorted(CANONICAL_FEATURES))
def test_all_canonical_features_pass(name):
    validate_feature_name(name)  # must not raise


def test_unknown_namespace_fails():
    with pytest.raises(FeatureNameError, match="unknown namespace"):
        validate_feature_name("nonexistent_namespace.something")


def test_non_namespaced_feature_fails():
    with pytest.raises(FeatureNameError):
        validate_feature_name("delta_power")


def test_new_name_under_known_namespace_passes():
    validate_feature_name("topology.some_new_invariant")


def test_experimental_namespace_structurally_passes():
    validate_feature_name("experimental.novel_metric")


def test_experimental_namespace_is_flagged_restricted():
    assert is_restricted_feature("experimental.novel_metric") is True
    assert is_restricted_feature("topology.q_net") is False


@pytest.mark.parametrize(
    "name",
    [
        "clinical.diagnosis_score",
        "topology.jhana_index",
        "experimental.jhāna_marker",
        "spectral.cessation_power",
        "dynamics.enlightenment_state",
        "connectivity.spiritual_attainment_score",
        "qc.clinical_biomarker",
        "experimental.treatment_response",
        "topology.psychiatric_marker",
        "dynamics.meditation_stage_detect_probability",
    ],
)
def test_forbidden_claim_like_names_fail(name):
    with pytest.raises(FeatureNameError):
        validate_feature_name(name)


def test_empty_name_fails():
    with pytest.raises(FeatureNameError):
        validate_feature_name("")


def test_validate_feature_names_returns_errors_list_not_raise():
    errors = validate_feature_names(["topology.q_net", "not_namespaced", "bad.jhana_score"])
    assert len(errors) == 2
    assert all(isinstance(e, str) for e in errors)


def test_validate_feature_names_empty_list_fails():
    errors = validate_feature_names([])
    assert errors


def test_validate_feature_names_or_raise_raises():
    with pytest.raises(FeatureNameError):
        validate_feature_names_or_raise(["not_namespaced"])


def test_validate_feature_names_or_raise_passes_for_valid_set():
    validate_feature_names_or_raise(["topology.q_net", "connectivity.mean_plv"])


def test_error_message_is_clear_and_mentions_the_bad_name():
    with pytest.raises(FeatureNameError, match="delta_power"):
        validate_feature_name("delta_power")
