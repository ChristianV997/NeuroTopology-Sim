import json

import numpy as np

from sim.pitnn.empirical_pipeline import (
    analytic_phase,
    bandpass_filter,
    generate_mock_conditions,
    phase_coherence_matrix,
    standardize_condition,
)
from scripts.run_empirical_falsification import run_empirical_falsification


def test_filter_and_hilbert_phase_are_finite():
    rate = 250.0
    t = np.arange(512) / rate
    data = np.column_stack([np.sin(2 * np.pi * 40 * t), np.cos(2 * np.pi * 40 * t), np.sin(2 * np.pi * 40 * t + .3)])
    filtered = bandpass_filter(data, rate, "gamma")
    analytic, phase = analytic_phase(filtered)
    assert filtered.shape == data.shape
    assert analytic.shape == data.shape
    assert phase.shape == data.shape
    assert np.all(np.isfinite(phase))
    coherence = phase_coherence_matrix(phase)
    assert coherence.shape == (512, 3, 3)
    np.testing.assert_allclose(np.diagonal(coherence, axis1=1, axis2=2), 1.0)


def test_mock_conditions_have_distinct_finite_topology():
    conditions = generate_mock_conditions(seed=11)
    assert set(conditions) == {"awake", "sedated"}
    assert all(np.all(np.isfinite(condition.charge)) for condition in conditions.values())
    assert all(condition.coherence.shape[1:] == (6, 6) for condition in conditions.values())


def test_synthetic_report_stays_not_supported(tmp_path):
    report = run_empirical_falsification(output_dir=tmp_path, fast_tda=True, seed=7)
    assert report["source_kind"] == "synthetic_demo"
    assert report["verdict"] == "NOT_SUPPORTED"
    assert report["bayes_factor"] <= 100.0
    payload = json.loads((tmp_path / "empirical_falsification_report.json").read_text(encoding="utf-8"))
    assert payload["schema"] == "PITNN.EmpiricalFalsificationReport.v1"
    assert set(payload["conditions"]) == {"awake", "sedated"}


def test_local_npz_conditions_are_ingested(tmp_path):
    rng = np.random.default_rng(4)
    first = rng.normal(size=(256, 4))
    second = rng.normal(size=(256, 4))
    source = tmp_path / "conditions.npz"
    np.savez(source, state_a=first, state_b=second)
    report = run_empirical_falsification(source, output_dir=tmp_path / "out", sample_rate_hz=250.0)
    assert report["source_kind"] == "empirical_local"
    assert report["verdict"] in {"PASS", "NOT_SUPPORTED"}
    assert np.isfinite(report["bayes_factor"])
