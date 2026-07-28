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


def test_serialize_deserialize_roundtrip_with_infinity():
    diagram = np.array([[0.1, 0.5], [0.2, np.inf]], dtype=float)
    encoded = serialize_diagram(diagram)
    assert encoded == [[0.1, 0.5], [0.2, None]]
    decoded = deserialize_diagram(encoded)
    assert decoded.shape == (2, 2)
    assert np.isinf(decoded[1, 1])


def test_bottleneck_distance_delegates_to_topology_impl():
    a = np.array([[0.0, 1.0]], dtype=float)
    b = np.array([[0.01, 1.01]], dtype=float)
    with pytest.raises(ImportError):
        bottleneck_distance(a, b)


def test_persistence_json_roundtrip_preserves_structure():
    diagrams = {0: np.array([[0.0, 1.0]], dtype=float)}
    payload = persistence_to_dict(diagrams, [1])
    restored = persistence_json_roundtrip(payload)
    rebuilt, betti = dict_to_persistence(restored)
    assert betti == [1]
    np.testing.assert_array_almost_equal(rebuilt[0], diagrams[0])


def test_persistence_statistics_handles_empty():
    stats = persistence_statistics(np.empty((0, 2), dtype=float))
    assert stats["count"] == 0
    assert stats["finite_pairs"] == 0
    assert stats["total_persistence"] == 0.0
