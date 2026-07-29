import numpy as np
import pytest

from research_runtime.transitions import (
    fit_feature_state_model,
    jensen_shannon_distance,
    operator_metrics,
    transition_operator,
)


def test_frozen_state_model_is_deterministic_and_reusable():
    features = np.array([[0.0], [0.1], [4.9], [5.0], [0.2], [5.1]])
    first = fit_feature_state_model(features, n_states=2, seed=11)
    second = fit_feature_state_model(features, n_states=2, seed=11)
    assert first.to_dict() == second.to_dict()
    assert np.array_equal(first.transform(features), second.transform(features))


def test_transition_operator_never_crosses_sequence_boundaries():
    result = transition_operator([0, 1, 1, 0, 1], ["a", "a", "a", "b", "b"])
    assert result["transition_counts"] == {"a": 2, "b": 1}
    assert np.asarray(result["operators"]["a"]).shape == (2, 2)


def test_operator_metrics_and_distance_are_finite():
    first = [[0.8, 0.2], [0.1, 0.9]]
    second = [[0.5, 0.5], [0.5, 0.5]]
    metrics = operator_metrics(first)
    assert 0.0 <= metrics["transition_entropy"] <= 1.0
    assert jensen_shannon_distance(first, second) > 0.0


def test_transition_inputs_fail_closed():
    with pytest.raises(ValueError):
        transition_operator([0, 1], ["only-one-sequence-label"])
    with pytest.raises(ValueError):
        fit_feature_state_model([[0.0], [float("nan")]], n_states=2)
