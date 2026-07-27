import json
import os

import numpy as np

from sim.pitnn.state_exporter import PITNNStateExporter
from sim.pitnn.visualization import PITNNVisualizer


def test_state_exporter_npz_roundtrip(tmp_path):
    exporter = PITNNStateExporter(tmp_path / "artifacts")
    rng = np.random.default_rng(42)
    spins = rng.normal(size=(20, 8, 3)); spins /= np.linalg.norm(spins, axis=2, keepdims=True)
    timestamps = np.linspace(0, 1e-12, len(spins))
    path = exporter.export_npz("test_spins.npz", spins, timestamps, {"test_run": True, "num_spins": 8})
    loaded = exporter.load_npz(path)
    np.testing.assert_allclose(loaded["spins_history"], spins, rtol=1e-12)
    np.testing.assert_allclose(loaded["time_stamps"], timestamps, rtol=1e-12)
    assert loaded["metadata"]["test_run"] is True


def test_state_exporter_json(tmp_path):
    path = PITNNStateExporter(tmp_path).export_json("summary", {"verdict": "NOT_SUPPORTED"})
    assert os.path.exists(path)
    assert json.loads(open(path, encoding="utf-8").read())["verdict"] == "NOT_SUPPORTED"


def test_generic_array_bundle_supports_complex_density(tmp_path):
    exporter = PITNNStateExporter(tmp_path)
    rho = np.eye(3, dtype=complex)[None, :, :]
    path = exporter.export_array_bundle("rho", {"rho_history": rho}, {"units": "dimensionless"})
    loaded = exporter.load_array_bundle(path)
    np.testing.assert_array_equal(loaded["rho_history"], rho)
    assert loaded["metadata"]["units"] == "dimensionless"


def test_visualizer_renders_headless_files(tmp_path):
    viz = PITNNVisualizer(tmp_path / "plots")
    rng = np.random.default_rng(42)
    spins = rng.normal(size=(10, 8, 3)); spins /= np.linalg.norm(spins, axis=2, keepdims=True)
    times = np.linspace(0, 1e-12, len(spins))
    trace = [{"winding_number": 1.0, "topological_charge": 0.05, "beta1_loops": 2} for _ in times]
    paths = [viz.plot_topological_trace(times, trace, "trace.png"),
             viz.plot_spinor_field_heatmap(spins, "heatmap.png"),
             viz.plot_s2_phase_space(spins[-1], "s2.png")]
    assert all(os.path.exists(path) and os.path.getsize(path) > 1000 for path in paths)
