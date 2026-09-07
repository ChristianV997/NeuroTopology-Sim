from __future__ import annotations

import ast
import json
from pathlib import Path

import numpy as np
import pytest

from analysis.transition_forecasting import BenchmarkDataset, ForecastStatus, locked_split, run_benchmark, validate_split
from analysis.transition_forecasting.benchmark import LeakageDetected


def make_dataset(kind: str = "triadic", *, synthetic: bool = True, missing_respiration: bool = False) -> BenchmarkDataset:
    rng = np.random.default_rng(42)
    n = 72
    psd = rng.normal(size=(n, 3))
    pairwise = rng.normal(size=(n, 3))
    triadic = rng.normal(size=(n, 3))
    hyper = rng.normal(size=(n, 3))
    if kind == "triadic":
        target = (triadic[:, 0] - triadic[:, 1] > 0).astype(int)
    elif kind == "pairwise":
        target = (pairwise[:, 0] + 0.25 * pairwise[:, 1] > 0).astype(int)
    else:
        target = (rng.normal(size=n) > 0).astype(int)
    controls = {
        "arousal": rng.normal(size=n), "cardiac": rng.normal(size=n),
        "sampling_rate": np.full(n, 100.0), "window_length": np.full(n, 2.0),
    }
    if not missing_respiration:
        controls["respiration"] = rng.normal(size=n)
    return BenchmarkDataset(
        features={"psd": psd, "pairwise_fc": pairwise, "triadic_fc": triadic, "directed_hypergraph": hyper},
        target=target, subjects=np.repeat(np.arange(6), 12), sessions=np.tile(np.arange(12), 6),
        timestamps=np.arange(n, dtype=float), prediction_horizon=2.0,
        target_definition="transition at t+Delta_t", provenance={"dataset_id": "fixture", "complete": True},
        controls=controls, synthetic=synthetic,
    )


def test_known_triadic_synthetic_transition_has_incremental_predictive_gain():
    report = run_benchmark(make_dataset("triadic"), seed=7)
    triadic = report.results[2]
    assert triadic.incremental_gain is not None and triadic.incremental_gain > 0
    assert triadic.status == ForecastStatus.SYNTHETIC_DEMO_ONLY.value
    assert report.formal_bayes_factor is None and report.scientific_pass is False


def test_pairwise_only_synthetic_transition_beats_psd_without_causal_language():
    report = run_benchmark(make_dataset("pairwise"), seed=7)
    pairwise = report.results[1]
    assert pairwise.incremental_gain is not None and pairwise.incremental_gain > 0
    assert report.evidence_class == "forecast_benchmark"
    assert "caus" not in report.to_json().lower()


def test_no_signal_reports_no_incremental_gain():
    dataset = make_dataset("null")
    dataset.features = {key: np.zeros_like(value) for key, value in dataset.features.items()}
    report = run_benchmark(dataset, seed=3)
    assert report.results[0].status == ForecastStatus.SYNTHETIC_DEMO_ONLY.value
    assert all(result.status == ForecastStatus.NO_INCREMENTAL_GAIN.value for result in report.results[1:])
    assert all(result.incremental_gain is None or abs(result.incremental_gain) < 1e-12 for result in report.results)


def test_subject_leakage_is_rejected_by_locked_validator():
    split = locked_split(np.array(["a", "a", "b", "b"]), np.arange(4), np.arange(4), "subject-held-out", validation_fraction=0)
    bad = type(split)(split.strategy, split.train, split.validation, split.test + (0,))
    with pytest.raises(ValueError, match="overlapping|subject leakage"):
        validate_split(bad, np.array(["a", "a", "b", "b"]), np.arange(4), np.arange(4))


def test_temporal_leakage_is_rejected_and_classified():
    dataset = make_dataset()
    dataset.feature_times = {"triadic_fc": dataset.timestamps + 1}
    report = run_benchmark(dataset)
    assert report.status == ForecastStatus.LEAKAGE_DETECTED.value


def test_locked_split_strategies_are_group_disjoint_and_forward_time_ordered():
    dataset = make_dataset()
    subject = locked_split(dataset.subjects, dataset.sessions, dataset.timestamps, "subject-held-out")
    validate_split(subject, dataset.subjects, dataset.sessions, dataset.timestamps)
    assert not set(dataset.subjects[list(subject.train)]) & set(dataset.subjects[list(subject.test)])
    session = locked_split(dataset.subjects, dataset.sessions, dataset.timestamps, "session-held-out")
    validate_split(session, dataset.subjects, dataset.sessions, dataset.timestamps)
    forward = locked_split(dataset.subjects, dataset.sessions, dataset.timestamps, "forward-time", cutoff=48)
    validate_split(forward, dataset.subjects, dataset.sessions, dataset.timestamps)
    assert max(dataset.timestamps[list(forward.train)]) < min(dataset.timestamps[list(forward.test)])


def test_calibration_and_proper_scores_are_finite():
    report = run_benchmark(make_dataset(), seed=1)
    for result in report.results:
        assert result.log_loss is not None and result.log_loss >= 0
        assert result.brier_score is not None and result.brier_score >= 0
        assert result.calibration_error is not None and result.calibration_error >= 0


def test_deterministic_repeat_and_finite_json():
    first = run_benchmark(make_dataset(), seed=11).to_json()
    second = run_benchmark(make_dataset(), seed=11).to_json()
    assert first == second
    payload = json.loads(first)
    assert payload["formal_bayes_factor"] is None
    assert payload["scientific_pass"] is False
    assert payload["evidence_class"] == "forecast_benchmark"
    json.dumps(payload, allow_nan=False)


def test_missing_respiration_is_reported_not_imputed_as_validation_success():
    report = run_benchmark(make_dataset(missing_respiration=True))
    assert "respiration" in report.missingness["PSD"] ["missing_controls"]
    assert "respiration" in report.results[0].missingness["missing_controls"]


def test_missing_optional_dependency_does_not_trigger_network_or_false_pass():
    report = run_benchmark(make_dataset("triadic", missing_respiration=True))
    assert report.status == ForecastStatus.SYNTHETIC_DEMO_ONLY.value
    source = Path(__file__).resolve().parents[2] / "analysis" / "transition_forecasting" / "benchmark.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    imports = [node.names[0].name for node in ast.walk(tree) if isinstance(node, ast.Import) and node.names]
    assert not any(name in {"socket", "requests", "urllib", "httpx"} for name in imports)


def test_target_derived_preprocessing_cannot_use_test_rows():
    dataset = make_dataset()
    report = run_benchmark(dataset, preprocessing_fit_indices=list(range(60, 72)))
    assert report.status == ForecastStatus.LEAKAGE_DETECTED.value
