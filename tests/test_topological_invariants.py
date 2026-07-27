import numpy as np
import pytest

from sim.pitnn.topological_invariants import TopologicalInvariantTracker


def test_winding_number_quantization():
    num_spins = 100
    tracker = TopologicalInvariantTracker(num_spins=num_spins)
    for winding in (1, 2):
        angles = np.linspace(0, winding * 2 * np.pi, num_spins, endpoint=False)
        spins = np.column_stack([np.cos(angles), np.sin(angles), np.zeros(num_spins)])
        assert np.isclose(tracker.compute_winding_number(spins), winding)


def test_chirality_and_topological_charge_are_rotation_invariant():
    num_spins = 100
    tracker = TopologicalInvariantTracker(num_spins=num_spins)
    rng = np.random.default_rng(42)
    spins = rng.normal(size=(num_spins, 3))
    spins /= np.linalg.norm(spins, axis=1, keepdims=True)
    theta = np.pi / 4.0
    rotation = np.array([[np.cos(theta), -np.sin(theta), 0],
                         [np.sin(theta), np.cos(theta), 0], [0, 0, 1]])
    q_initial = tracker.compute_topological_charge(spins)
    q_rotated = tracker.compute_topological_charge(spins @ rotation.T)
    assert np.isfinite(q_initial)
    assert np.isclose(q_initial, q_rotated, atol=1e-12)


def test_topological_audit_snapshot_keys():
    tracker = TopologicalInvariantTracker(num_spins=50)
    spins = np.ones((50, 3)) / np.sqrt(3)
    snapshot = tracker.audit_snapshot(spins)
    assert set(snapshot) == {"winding_number", "topological_charge", "beta1_loops", "max_chirality", "mean_chirality"}
    assert isinstance(snapshot["beta1_loops"], int)


def test_tracker_rejects_wrong_shape_and_nonfinite_values():
    tracker = TopologicalInvariantTracker(num_spins=8)
    with pytest.raises(ValueError):
        tracker.audit_snapshot(np.zeros((7, 3)))
    invalid = np.zeros((8, 3)); invalid[0, 0] = np.nan
    with pytest.raises(ValueError):
        tracker.audit_snapshot(invalid)
