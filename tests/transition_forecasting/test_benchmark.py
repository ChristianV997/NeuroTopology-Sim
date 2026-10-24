from __future__ import annotations

import ast
import hashlib
import itertools
import json
import sys
from pathlib import Path

import numpy as np
import pytest

from analysis.transition_forecasting import BenchmarkDataset, ForecastStatus, locked_split, run_benchmark, validate_split
from analysis.transition_forecasting.benchmark import LeakageDetected, _auprc, _auroc, _metadata_is_missing
from scripts.run_transition_benchmark import main as transition_benchmark_main


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
    features = {"psd": psd, "pairwise_fc": pairwise, "triadic_fc": triadic, "directed_hypergraph": hyper}
    timestamps = np.arange(n, dtype=float)
    return BenchmarkDataset(
        features=features,
        target=target, subjects=np.repeat(np.arange(6), 12), sessions=np.tile(np.arange(12), 6),
        timestamps=timestamps, prediction_horizon=2.0,
        target_definition="transition at t+Delta_t", provenance={"dataset_id": "fixture", "complete": True},
        controls=controls,
        feature_times={name: timestamps.copy() for name in features},
        synthetic=synthetic,
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


def test_auroc_averages_ranks_for_tied_scores():
    assert _auroc(
        np.array([0, 0, 1, 1]),
        np.array([0.1, 0.4, 0.4, 0.8]),
    ) == pytest.approx(0.875)


def test_subject_leakage_is_rejected_by_locked_validator():
    split = locked_split(np.array(["a", "a", "b", "b"]), np.arange(4), np.arange(4), "subject-held-out", validation_fraction=0)
    bad = type(split)(split.strategy, split.train, split.validation, split.test + (0,))
    with pytest.raises(ValueError, match="overlapping|subject leakage"):
        validate_split(bad, np.array(["a", "a", "b", "b"]), np.arange(4), np.arange(4))


def test_temporal_leakage_is_rejected_and_classified():
    dataset = make_dataset()
    dataset.feature_times = {
        name: dataset.timestamps.copy() for name in dataset.features
    }
    dataset.feature_times["triadic_fc"] = dataset.timestamps + 1
    report = run_benchmark(dataset)
    assert report.status == ForecastStatus.LEAKAGE_DETECTED.value


def test_missing_feature_time_lineage_is_rejected_before_model_fitting():
    dataset = make_dataset()
    del dataset.feature_times["triadic_fc"]
    report = run_benchmark(dataset)
    assert report.status == ForecastStatus.INVALID_INPUT.value
    assert "immutable feature-time lineage" in report.dataset_provenance["message"]


def test_mismatched_feature_time_vector_is_rejected_before_model_fitting():
    dataset = make_dataset()
    dataset.feature_times["psd"] = dataset.timestamps[:-1]
    report = run_benchmark(dataset)
    assert report.status == ForecastStatus.INVALID_INPUT.value
    assert "row-aligned" in report.dataset_provenance["message"]


def test_non_finite_and_non_monotonic_feature_time_lineage_are_rejected():
    non_finite = make_dataset()
    non_finite.feature_times["pairwise_fc"][3] = np.nan
    assert run_benchmark(non_finite).status == ForecastStatus.INVALID_INPUT.value

    non_monotonic = make_dataset()
    non_monotonic.feature_times["pairwise_fc"][4] = non_monotonic.feature_times["pairwise_fc"][3] - 1
    assert run_benchmark(non_monotonic).status == ForecastStatus.INVALID_INPUT.value


def test_feature_time_lineage_is_bound_into_dataset_identity():
    dataset = make_dataset()
    baseline = dataset.checksum()
    dataset.feature_times["triadic_fc"] = dataset.feature_times["triadic_fc"].copy()
    dataset.feature_times["triadic_fc"][0] = -0.25
    assert dataset.checksum() != baseline


def test_dataset_identity_binds_report_affecting_metadata_and_controls():
    baseline = make_dataset().checksum()

    changed_horizon = make_dataset()
    changed_horizon.prediction_horizon = 3.0
    assert changed_horizon.checksum() != baseline

    changed_target = make_dataset()
    changed_target.target_definition = "different declared target"
    assert changed_target.checksum() != baseline

    changed_provenance = make_dataset()
    changed_provenance.provenance = {**changed_provenance.provenance, "revision": "r2"}
    assert changed_provenance.checksum() != baseline

    changed_control = make_dataset()
    changed_control.controls = {
        **changed_control.controls,
        "arousal": changed_control.controls["arousal"] + 1,
    }
    assert changed_control.checksum() != baseline

    changed_adjudication = make_dataset()
    changed_adjudication.adjudication_metadata = {"multiplicity": {"method": "holm"}}
    assert changed_adjudication.checksum() != baseline

    changed_source_mode = make_dataset()
    changed_source_mode.synthetic = False
    assert changed_source_mode.checksum() != baseline

    nested_array = make_dataset()
    nested_array.provenance = {"source_vector": np.arange(2048)}
    nested_baseline = nested_array.checksum()
    source_vector = np.asarray(nested_array.provenance["source_vector"]).copy()
    source_vector[1024] += 1
    nested_array.provenance = {"source_vector": source_vector}
    assert nested_array.checksum() != nested_baseline


def test_report_checksum_binds_the_complete_serialized_report():
    report = run_benchmark(make_dataset(), seed=11)
    payload = report.to_dict()
    declared_checksum = payload.pop("checksum")
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False)

    assert declared_checksum == hashlib.sha256(serialized.encode("utf-8")).hexdigest()
    assert payload["dataset_checksum"]


def test_report_identity_changes_when_prediction_horizon_changes():
    baseline = run_benchmark(make_dataset(), seed=11)
    changed_dataset = make_dataset()
    changed_dataset.prediction_horizon = 3.0
    changed = run_benchmark(changed_dataset, seed=11)

    assert [result.log_loss for result in baseline.results] == [result.log_loss for result in changed.results]
    assert baseline.dataset_checksum != changed.dataset_checksum
    assert baseline.checksum != changed.checksum


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


def test_incomplete_provenance_cannot_be_reported_as_formal_evidence():
    dataset = make_dataset(synthetic=False)
    dataset.provenance = {"dataset_id": "local-incomplete", "complete": False}
    report = run_benchmark(dataset)
    assert report.status == ForecastStatus.INSUFFICIENT_DATA.value
    assert all(result.status != ForecastStatus.FORMAL_FORECAST_EVIDENCE.value for result in report.results)


def test_ordinary_valid_held_out_empirical_benchmark_is_inconclusive_locally():
    dataset = make_dataset("triadic", synthetic=False)
    dataset.adjudication_metadata = {
        "null_models": {"families": ["label-permutation"]},
        "calibration": {"metric": "ece"},
        "locked_split": {"strategy": "subject-held-out"},
        "multiplicity": {"method": "holm"},
    }
    report = run_benchmark(dataset, seed=7)
    assert report.status == ForecastStatus.INCONCLUSIVE.value
    assert all(result.status != ForecastStatus.FORMAL_FORECAST_EVIDENCE.value for result in report.results)
    assert report.formal_bayes_factor is None and report.scientific_pass is False
    assert report.adjudication["external_independent_adjudication_required"] is True


def test_self_attested_formal_metadata_cannot_promote_forecast_evidence():
    dataset = make_dataset("triadic", synthetic=False)
    dataset.provenance = {
        "dataset_id": "complete-local-data",
        "complete": True,
        "formal_bayes_factor": 10_000.0,
        "scientific_pass": True,
    }
    dataset.adjudication_metadata = {
        "null_models": {"families": ["label-permutation"]},
        "calibration": {"metric": "ece"},
        "locked_split": {"strategy": "subject-held-out"},
        "multiplicity": {"method": "holm"},
        "formal_evidence": True,
        "evidence_adjudicated": True,
    }
    report = run_benchmark(dataset, seed=7)
    payload = report.to_dict()
    assert report.status == ForecastStatus.INCONCLUSIVE.value
    assert payload["formal_bayes_factor"] is None
    assert payload["scientific_pass"] is False
    assert "formal_bayes_factor" in payload["adjudication"]["caller_formal_metadata_ignored"]
    assert "formal_evidence" in payload["adjudication"]["caller_formal_metadata_ignored"]


def test_missing_optional_dependency_does_not_trigger_network_or_false_pass():
    report = run_benchmark(make_dataset("triadic", missing_respiration=True))
    assert report.status == ForecastStatus.SYNTHETIC_DEMO_ONLY.value
    source = Path(__file__).resolve().parents[2] / "analysis" / "transition_forecasting" / "benchmark.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    imports = [node.names[0].name for node in ast.walk(tree) if isinstance(node, ast.Import) and node.names]
    assert not any(name in {"socket", "requests", "urllib", "httpx"} for name in imports)


def test_synthetic_cli_demo_supplies_explicit_feature_time_lineage(tmp_path, monkeypatch):
    output = tmp_path / "synthetic-report.json"
    monkeypatch.setattr(
        sys,
        "argv",
        ["run_transition_benchmark.py", "--synthetic-demo", "--output", str(output)],
    )

    assert transition_benchmark_main() == 0
    report = json.loads(output.read_text(encoding="utf-8"))

    assert report["status"] == ForecastStatus.SYNTHETIC_DEMO_ONLY.value
    assert report["dataset_checksum"]


def test_target_derived_preprocessing_cannot_use_test_rows():
    dataset = make_dataset()
    report = run_benchmark(dataset, preprocessing_fit_indices=list(range(60, 72)))
    assert report.status == ForecastStatus.LEAKAGE_DETECTED.value


def test_auprc_tied_scores_is_invariant_to_row_order():
    scores = np.array([0.5, 0.5])
    assert _auprc(np.array([1, 0]), scores) == pytest.approx(0.5)
    assert _auprc(np.array([0, 1]), scores) == pytest.approx(0.5)


def test_empty_adjudication_sequences_are_missing():
    assert _metadata_is_missing([])
    assert _metadata_is_missing(())

    dataset = make_dataset(synthetic=False)
    dataset.adjudication_metadata = {
        "null_models": [],
        "calibration": {},
        "locked_split": (),
        "multiplicity": {},
    }
    report = run_benchmark(dataset)

    assert "null_models" in report.adjudication["missing_requirements"]
    assert "locked_split" in report.adjudication["missing_requirements"]


@pytest.mark.parametrize("declaration", [
    {"families": []},
    {"families": {}},
    {"method": ""},
    {"metric": None},
    {"outer": {"inner": []}},
    [{}],
    [[]],
])
def test_nested_empty_adjudication_declarations_are_missing(declaration):
    # Regression (#357 remediation): a non-empty mapping whose leaves are all empty is not a declaration.
    assert _metadata_is_missing(declaration)


def test_nested_empty_null_model_declaration_stays_missing_in_report():
    dataset = make_dataset(synthetic=False)
    dataset.adjudication_metadata = {
        "null_models": {"families": []},
        "calibration": {"metric": "ece"},
        "locked_split": {"strategy": "subject-held-out"},
        "multiplicity": {"method": "holm"},
    }
    report = run_benchmark(dataset)
    assert "null_models" in report.adjudication["missing_requirements"]


def test_auprc_multi_row_ties_are_invariant_to_row_order():
    # Lock: tie groups are evaluated at their threshold, so reordering rows inside a tie cannot move AUPRC.
    y = np.array([0, 1, 0, 1, 1, 0])
    scores = np.array([0.9, 0.5, 0.5, 0.5, 0.2, 0.9])
    expected = 1.3 / 3  # 0.9: 0 positives; 0.5: 2 positives at precision 2/5; 0.2: 1 positive at precision 3/6.
    assert _auprc(y, scores) == pytest.approx(expected)
    for order in itertools.permutations(range(len(y))):
        order = np.array(order)
        assert _auprc(y[order], scores[order]) == pytest.approx(expected)

