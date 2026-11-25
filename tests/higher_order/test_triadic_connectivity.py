"""Engineering and contract tests for bounded triadic connectivity."""

from __future__ import annotations

import json
import socket
import sys

import numpy as np
import pytest

from topo_monitor.higher_order.triadic import (
    SCHEMA_VERSION,
    SignalWindow,
    estimate_triadic_connectivity,
)


def _nonlinear(seed: int = 7, samples: int = 800) -> np.ndarray:
    rng = np.random.default_rng(seed)
    x = rng.normal(size=samples)
    y = rng.normal(size=samples)
    return np.vstack([x, y, x * y])


def _independent(seed: int = 8, channels: int = 3, samples: int = 800) -> np.ndarray:
    return np.random.default_rng(seed).normal(size=(channels, samples))


def _common_driver(seed: int = 9, samples: int = 800) -> np.ndarray:
    rng = np.random.default_rng(seed)
    driver = rng.normal(size=samples)
    return np.vstack([driver + 0.5 * rng.normal(size=samples) for _ in range(3)])


def _top(result):
    assert result.top_triads
    return result.top_triads[0]


def test_known_three_way_interaction_has_nonlinear_score_and_surrogate_controls() -> None:
    result = estimate_triadic_connectivity(
        _nonlinear(),
        channel_labels=("x", "y", "z"),
        source_id="synthetic-three-way",
        synthetic_demo=True,
        top_k=1,
        surrogate_methods=("amplitude_shuffle", "phase_shuffle", "circular_shift", "block_shift"),
        n_surrogates=8,
        seed=101,
    )
    assert _top(result).nonlinear_interaction_score is not None
    assert _top(result).nonlinear_interaction_score > 0.1
    assert len(result.surrogate_comparisons) == 4
    assert all(item.status == "COMPUTED" for item in result.surrogate_comparisons)
    assert result.provenance.synthetic_demo is True
    assert result.schema_version == SCHEMA_VERSION


def test_independent_gaussian_null_is_low_for_nonlinear_estimator() -> None:
    result = estimate_triadic_connectivity(_independent(), top_k=1)
    assert (_top(result).nonlinear_interaction_score or 0.0) < 0.1
    assert result.psd_control["is_psd_with_tolerance"] is True
    assert result.pairwise_control["finite_value_status"] == "FINITE"


def test_common_driver_is_distinct_from_three_way_nonlinearity() -> None:
    interaction = _top(estimate_triadic_connectivity(_nonlinear(), top_k=1))
    common = _top(estimate_triadic_connectivity(_common_driver(), top_k=1))
    assert (common.matrix_entropy_score or 0.0) > 0.2
    assert (common.nonlinear_interaction_score or 0.0) < (interaction.nonlinear_interaction_score or 0.0)


def test_channel_permutation_invariance_with_stable_labels() -> None:
    data = _nonlinear()
    labels = ("x", "y", "z")
    first = estimate_triadic_connectivity(data, channel_labels=labels, top_k=1)
    permutation = np.array([2, 0, 1])
    second = estimate_triadic_connectivity(data[permutation], channel_labels=np.asarray(labels)[permutation], top_k=1)
    assert _top(first).channel_labels == _top(second).channel_labels
    assert _top(first).combined_score == pytest.approx(_top(second).combined_score)


def test_repeated_execution_and_canonical_serialization_are_deterministic() -> None:
    kwargs = dict(
        channel_labels=("a", "b", "c"),
        top_k=1,
        surrogate_methods=("phase_shuffle", "block_shift"),
        n_surrogates=5,
        seed=22,
        synthetic_demo=True,
    )
    first = estimate_triadic_connectivity(_nonlinear(), **kwargs)
    second = estimate_triadic_connectivity(_nonlinear(), **kwargs)
    assert first.to_json() == second.to_json()
    assert first.provenance_checksum == second.provenance_checksum
    parsed = json.loads(first.to_json())
    assert parsed["provenance"]["synthetic_demo"] is True
    assert "graph_beta1" not in parsed
    assert "spatial_winding" not in parsed
    assert "scalar_chirality" not in parsed


def test_feature_matrix_input_and_condition_labels() -> None:
    data = _nonlinear()
    result = estimate_triadic_connectivity(
        feature_matrix=data,
        channel_labels=("f0", "f1", "f2"),
        condition_labels=("rest",) * data.shape[1],
        input_kind="feature_matrix",
    )
    assert result.provenance.input_kind == "feature_matrix"
    assert result.effective_channel_count == 3
    assert result.condition_summary == {"rest": data.shape[1]}
    assert result.optional_dependency_status["scipy"] == "not_required"


def test_bounded_triad_count_and_complexity_telemetry() -> None:
    data = _independent(channels=80, samples=80)
    result = estimate_triadic_connectivity(data, max_channels=80, max_triads=17, top_k=5)
    telemetry = result.complexity_telemetry
    assert len(result.interactions) <= 17
    assert telemetry["candidate_triads"] <= 17
    assert telemetry["triad_generation"] == "sparse_bounded"
    assert telemetry["bounded"] is True
    assert telemetry["theoretical_all_triads_for_selected_channels"] > 17


def test_memory_bound_rejects_oversized_input() -> None:
    with pytest.raises(MemoryError):
        estimate_triadic_connectivity(_independent(samples=100), max_memory_mb=0.0001)


def test_missing_optional_scipy_does_not_change_numpy_estimator(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "scipy", None)
    result = estimate_triadic_connectivity(_independent(), top_k=1)
    assert result.finite_value_status == "FINITE"


def test_malformed_shapes_nonfinite_values_and_duplicate_labels_are_rejected() -> None:
    with pytest.raises(ValueError, match="shape"):
        estimate_triadic_connectivity(np.ones((2, 10)))
    with pytest.raises(ValueError, match="shape"):
        estimate_triadic_connectivity(np.ones((3, 10, 1)))
    bad = _independent().copy()
    bad[0, 0] = np.nan
    with pytest.raises(ValueError, match="NaN"):
        estimate_triadic_connectivity(bad)
    with pytest.raises(ValueError, match="unique"):
        SignalWindow(_independent(), channel_labels=("x", "x", "z"))


def test_signal_window_timestamp_and_condition_validation() -> None:
    data = _independent(samples=20)
    with pytest.raises(ValueError, match="strictly increasing"):
        SignalWindow(data, timestamps=tuple(range(19)) + (18,))
    with pytest.raises(ValueError, match="condition_labels"):
        SignalWindow(data, condition_labels=("rest",))


def test_json_is_finite_and_no_network_is_used(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked_socket(*args, **kwargs):
        raise AssertionError("network access is forbidden in triadic estimation")

    monkeypatch.setattr(socket, "socket", blocked_socket)
    result = estimate_triadic_connectivity(_independent(), top_k=1)
    encoded = result.to_json()
    assert "NaN" not in encoded
    assert "Infinity" not in encoded
    json.loads(encoded)


def test_invalid_surrogate_and_parameter_bounds_are_rejected() -> None:
    with pytest.raises(ValueError, match="unsupported surrogate"):
        estimate_triadic_connectivity(_independent(), surrogate_methods=("unknown",), n_surrogates=1)
    with pytest.raises(ValueError, match="n_surrogates"):
        estimate_triadic_connectivity(_independent(), surrogate_methods=("phase_shuffle",), n_surrogates=0)
    with pytest.raises(ValueError, match="max_channels"):
        estimate_triadic_connectivity(_independent(), max_channels=2)
