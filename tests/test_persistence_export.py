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


def test_serialize_deserialize_roundtrip_with_infinity():
    diagram = np.array([[0.1, 0.5], [0.2, np.inf]], dtype=float)
    encoded = serialize_diagram(diagram)
    assert encoded == [[0.1, 0.5], [0.2, None]]
    decoded = deserialize_diagram(encoded)
    np.testing.assert_array_equal(decoded[0], diagram[0])
    assert np.isinf(decoded[1, 1])


def test_serialization_rejects_non_pair_shape():
    with pytest.raises(ValueError, match=r"shape \(n, 2\)"):
        serialize_diagram(np.zeros(3))


def test_bottleneck_distance_uses_canonical_topology_impl():
    gudhi = pytest.importorskip("gudhi")
    a = np.array([[0.0, 1.0]], dtype=float)
    b = np.array([[0.01, 1.01]], dtype=float)
    assert bottleneck_distance(a, b) == pytest.approx(gudhi.bottleneck_distance(a, b))


def test_bottleneck_distance_requires_optional_gudhi():
    pytest.importorskip("gudhi")


def test_empty_diagram_statistics_and_distance():
    empty = np.empty((0, 2), dtype=float)
    assert persistence_statistics(empty)["total_persistence"] == 0.0
    gudhi = pytest.importorskip("gudhi")
    assert bottleneck_distance(empty, empty) == 0.0


def test_persistence_statistics_excludes_infinite_pairs():
    stats = persistence_statistics(np.array([[0.0, 1.0], [0.1, np.inf], [0.2, 2.0]]))
    assert stats["count"] == 3
    assert stats["finite_pairs"] == 2
    assert stats["max_lifetime"] == pytest.approx(1.8)
    assert stats["total_persistence"] == pytest.approx(2.8)


def test_persistence_mapping_roundtrip():
    diagrams = {0: np.array([[0.0, 1.0], [0.1, np.inf]]), 1: np.array([[0.2, 0.8]])}
    payload = persistence_to_dict(diagrams, [2, 1])
    assert json.loads(json.dumps(payload))["betti_numbers"] == [2, 1]
    restored = persistence_json_roundtrip(payload)
    rebuilt, betti = dict_to_persistence(restored)
    assert betti == [2, 1]
    np.testing.assert_array_equal(rebuilt[0][0], diagrams[0][0])
    assert np.isinf(rebuilt[0][1, 1])
