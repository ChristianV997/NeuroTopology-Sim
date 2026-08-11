"""Tests for the phase-space axis registry."""
from __future__ import annotations

import pytest

from phase_space.axes import (
    AXES,
    AXIS_NAMES,
    PLACEHOLDER_AXES,
    AxisError,
    axis_feature_map,
    get_axis,
    validate_axis_name,
)
from phase_space.uncertainty import CONFIDENCE_ORDER
from transitions.features import ALLOWED_NAMESPACES

_EXPECTED_AXES = {
    "integration",
    "differentiation",
    "metastability",
    "accessibility_proxy",
    "precision_stability_proxy",
    "topological_organization",
    "temporal_continuity",
    "generative_depth_proxy",
    "self_model_proxy",
}


def test_all_initial_axes_registered():
    assert set(AXIS_NAMES) == _EXPECTED_AXES


def test_every_axis_declares_at_least_one_feature():
    for name, axis in AXES.items():
        assert axis.features, f"axis '{name}' declares no source features"


def test_axis_feature_map_is_explicit_and_complete():
    mapping = axis_feature_map()
    assert set(mapping) == _EXPECTED_AXES
    for name, features in mapping.items():
        assert isinstance(features, list) and features


def test_all_mapped_features_use_allowed_namespaces():
    for name, axis in AXES.items():
        for feature in axis.features:
            namespace = feature.split(".", 1)[0]
            assert namespace in ALLOWED_NAMESPACES, (
                f"axis '{name}' maps feature '{feature}' with unknown namespace"
            )


def test_every_axis_has_a_description_and_direction_note():
    for name, axis in AXES.items():
        assert axis.description.strip(), f"axis '{name}' has no description"
        assert axis.direction_note.strip(), f"axis '{name}' has no direction note"


def test_every_axis_max_confidence_is_a_known_level():
    for axis in AXES.values():
        assert axis.max_confidence in CONFIDENCE_ORDER


def test_no_axis_permits_high_confidence():
    for name, axis in AXES.items():
        assert axis.max_confidence != "high", (
            f"axis '{name}' declares a 'high' ceiling; v1 policy forbids it"
        )


# ── Name-safety firewall ─────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "bad",
    [
        "clinical_severity",
        "diagnostic_index",
        "consciousness_detection",
        "jhana_depth",
        "jhāna_depth",
        "cessation_index",
        "enlightenment_level",
        "spiritual_attainment_score",
        "treatment_response",
        "psychiatric_state",
        "validated_biomarker",
    ],
)
def test_forbidden_axis_names_fail(bad):
    with pytest.raises(AxisError):
        validate_axis_name(bad)


def test_unknown_axis_name_fails():
    with pytest.raises(AxisError, match="unknown axis"):
        validate_axis_name("not_a_registered_axis")


def test_empty_axis_name_fails():
    with pytest.raises(AxisError):
        validate_axis_name("")


def test_registered_axes_all_pass_validation():
    for name in AXIS_NAMES:
        validate_axis_name(name)


def test_get_axis_returns_the_registered_object():
    axis = get_axis("topological_organization")
    assert axis.name == "topological_organization"
    assert "topology.q_abs" in axis.features


def test_get_axis_rejects_unknown_name():
    with pytest.raises(AxisError):
        get_axis("nope")


# ── Proxy-axis conservatism ─────────────────────────────────────────────────

def test_placeholder_axes_are_declared():
    assert PLACEHOLDER_AXES == {"generative_depth_proxy", "self_model_proxy"}


def test_placeholder_axes_only_map_phenomenology_features():
    for name in PLACEHOLDER_AXES:
        for feature in AXES[name].features:
            assert feature.startswith("phenomenology."), (
                f"placeholder axis '{name}' maps non-phenomenology feature "
                f"'{feature}', which would make it accidentally estimable"
            )


@pytest.mark.parametrize("name", ["accessibility_proxy", "precision_stability_proxy"])
def test_indirect_proxy_axes_are_capped_at_low_confidence(name):
    assert AXES[name].max_confidence == "low"


@pytest.mark.parametrize("name", sorted(PLACEHOLDER_AXES))
def test_placeholder_axes_are_capped_at_low_confidence(name):
    assert AXES[name].max_confidence == "low"


def test_no_axis_name_claims_to_measure_consciousness():
    for name in AXIS_NAMES:
        assert "consciousness" not in name.lower()
        assert "awareness" not in name.lower()
