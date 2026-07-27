"""Tests for persistence diagram JSON serialization."""
import json

import numpy as np
import pytest

from core.persistence_export import (
    bottleneck_distance,
    deserialize_diagram,
    dict_to_persistence,
    persistence_json_roundtrip,
    persistence_statistics,
    persistence_to_dict,
    serialize_diagram,
)


def test_serialize_deserialize_empty():
    """Empty diagram round-trip."""
    dgm = np.empty((0, 2), dtype=float)
    serialized = serialize_diagram(dgm)
    assert serialized == []
    deserialized = deserialize_diagram(serialized)
    assert deserialized.shape == (0, 2)


def test_serialize_deserialize_finite():
    """Finite pairs round-trip."""
    dgm = np.array([[0.1, 0.5], [0.2, 0.8], [0.3, 1.0]])
    serialized = serialize_diagram(dgm)
    assert len(serialized) == 3
    assert serialized[0] == [0.1, 0.5]

    deserialized = deserialize_diagram(serialized)
    assert deserialized.shape == (3, 2)
    np.testing.assert_array_almost_equal(deserialized, dgm)


def test_serialize_deserialize_infinite():
    """Infinite death values round-trip through None."""
    dgm = np.array([[0.1, 0.5], [0.2, np.inf], [0.3, 1.0]])
    serialized = serialize_diagram(dgm)
    assert serialized[0] == [0.1, 0.5]
    assert serialized[1] == [0.2, None]
    assert serialized[2] == [0.3, 1.0]

    deserialized = deserialize_diagram(serialized)
    assert deserialized.shape == (3, 2)
    assert np.isfinite(deserialized[0, 1])
    assert np.isinf(deserialized[1, 1])
    assert np.isfinite(deserialized[2, 1])


def test_persistence_statistics_empty():
    """Statistics on empty diagram."""
    dgm = np.empty((0, 2), dtype=float)
    stats = persistence_statistics(dgm)
    assert stats["count"] == 0
    assert stats["finite_pairs"] == 0
    assert stats["max_lifetime"] is None


def test_persistence_statistics_finite():
    """Statistics on finite-only diagram."""
    dgm = np.array([[0.0, 1.0], [0.1, 0.5], [0.2, 2.0]])
    stats = persistence_statistics(dgm)
    assert stats["count"] == 3
    assert stats["finite_pairs"] == 3
    assert stats["max_lifetime"] == 1.8  # 2.0 - 0.2
    assert stats["mean_lifetime"] == pytest.approx((1.0 + 0.4 + 1.8) / 3)
    assert stats["total_persistence"] == pytest.approx(1.0 + 0.4 + 1.8)


def test_persistence_statistics_mixed():
    """Statistics on diagram with infinite pairs."""
    dgm = np.array([[0.0, 1.0], [0.1, np.inf], [0.2, 2.0]])
    stats = persistence_statistics(dgm)
    assert stats["count"] == 3
    assert stats["finite_pairs"] == 2  # only non-inf pairs
    assert stats["max_lifetime"] == 1.8
    assert stats["mean_lifetime"] == pytest.approx((1.0 + 1.8) / 2)


def test_bottleneck_distance_identical():
    """Identical diagrams have distance 0."""
    dgm = np.array([[0.1, 0.5], [0.2, 0.8]])
    dist = bottleneck_distance(dgm, dgm)
    assert dist == 0.0


def test_bottleneck_distance_empty():
    """Empty vs non-empty."""
    dgm1 = np.empty((0, 2), dtype=float)
    dgm2 = np.array([[0.0, 1.0]])
    dist = bottleneck_distance(dgm1, dgm2)
    assert dist == 0.5  # distance to diagonal for (0, 1)


def test_bottleneck_distance_both_empty():
    """Two empty diagrams."""
    dgm1 = np.empty((0, 2), dtype=float)
    dgm2 = np.empty((0, 2), dtype=float)
    dist = bottleneck_distance(dgm1, dgm2)
    assert dist == 0.0


def test_bottleneck_distance_shifted():
    """Slightly shifted diagrams."""
    dgm1 = np.array([[0.0, 1.0]])
    dgm2 = np.array([[0.01, 1.01]])
    dist = bottleneck_distance(dgm1, dgm2)
    assert dist == pytest.approx(0.01, abs=1e-6)


def test_persistence_to_dict():
    """Convert GUDHI output to dict."""
    diagrams = {
        0: np.array([[0.0, 1.0], [0.1, np.inf]]),
        1: np.array([[0.2, 0.8]]),
    }
    betti = [2, 1, 0]
    data = persistence_to_dict(diagrams, betti)

    assert "diagrams" in data
    assert "statistics" in data
    assert "betti_numbers" in data
    assert data["betti_numbers"] == [2, 1, 0]
    assert "0" in data["diagrams"]
    assert "1" in data["diagrams"]
    assert len(data["diagrams"]["0"]) == 2
    assert len(data["diagrams"]["1"]) == 1


def test_persistence_json_roundtrip():
    """Full JSON serialization roundtrip."""
    diagrams = {
        0: np.array([[0.0, 1.0], [0.1, 0.5]]),
        1: np.array([[0.2, 0.8]]),
    }
    betti = [2, 1]
    data = persistence_to_dict(diagrams, betti)

    # Serialize to JSON and back
    json_str = json.dumps(data)
    restored = json.loads(json_str)

    # Verify structure
    assert "diagrams" in restored
    assert "statistics" in restored
    assert len(restored["diagrams"]["0"]) == 2
    assert len(restored["diagrams"]["1"]) == 1

    # Verify numerical precision
    dgm0_restored = deserialize_diagram(restored["diagrams"]["0"])
    np.testing.assert_array_almost_equal(dgm0_restored[:2], diagrams[0][:2])


def test_dict_to_persistence():
    """Reconstruct from JSON dict."""
    diagrams_orig = {
        0: np.array([[0.0, 1.0], [0.1, np.inf]]),
        1: np.array([[0.2, 0.8]]),
    }
    betti_orig = [2, 1]
    data = persistence_to_dict(diagrams_orig, betti_orig)

    diagrams_restored, betti_restored = dict_to_persistence(data)

    assert set(diagrams_restored.keys()) == {0, 1}
    assert betti_restored == betti_orig
    assert diagrams_restored[0].shape == (2, 2)
    assert np.isinf(diagrams_restored[0][1, 1])
    np.testing.assert_array_almost_equal(diagrams_restored[1], diagrams_orig[1])
