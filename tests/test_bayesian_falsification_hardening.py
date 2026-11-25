import numpy as np

from sim.pitnn.bayesian_falsification import (
    bayes_factor_from_marginal_likelihoods,
    bayes_factor_proxy_from_rss,
    classify_falsification_status,
    compare_models,
    generate_null_controls,
    multiplicity_correction,
    separate_topology_metrics,
    validate_falsification_input,
)


def _pass_kwargs():
    return {
        "method": "formal_marginal_likelihood",
        "data_mode": "empirical",
        "validation_status": "VALID",
        "provenance_status": "complete",
        "controls_pass": True,
        "multiplicity_status": "not_needed",
        "effective_sample_count": 32,
    }


def test_absolute_gate_is_strict_at_and_around_100():
    assert classify_falsification_status(99.999, **_pass_kwargs()) == "NOT_SUPPORTED"
    assert classify_falsification_status(100.0, **_pass_kwargs()) == "NOT_SUPPORTED"
    assert classify_falsification_status(100.001, **_pass_kwargs()) == "INCONCLUSIVE"


def test_invalid_or_missing_k_is_inconclusive():
    assert classify_falsification_status(None, **_pass_kwargs()) == "INCONCLUSIVE"
    assert classify_falsification_status(float("nan"), **_pass_kwargs()) == "INCONCLUSIVE"
    assert classify_falsification_status(1000.0, method="formal_marginal_likelihood", controls_pass=True, multiplicity_status="not_needed", effective_sample_count=32) == "INCONCLUSIVE"


def test_formal_bayes_factor_is_distinguished_from_rss_proxy():
    proxy = bayes_factor_proxy_from_rss(1.0, 100.0, 64, 5, 4)
    formal = bayes_factor_from_marginal_likelihoods(101.0, 1.0)
    assert proxy["formal"] is False
    assert proxy["method"] == "bic_proxy"
    assert formal["formal"] is True
    assert formal["method"] == "formal_marginal_likelihood"
    assert np.isclose(formal["k_value"], 101.0)


def test_bic_complexity_penalty_is_explicit_and_stronger_than_aic():
    aic = bayes_factor_proxy_from_rss(1.0, 2.0, 64, 10, 2, selected_metric="aic")
    bic = bayes_factor_proxy_from_rss(1.0, 2.0, 64, 10, 2, selected_metric="bic")
    assert bic["selected_evidence_metric"] == "bic"
    assert bic["k_value"] < aic["k_value"]
    assert bic["aicc"]["model"] is not None


def test_synthetic_comparison_can_never_pass_even_with_large_proxy_k():
    signal = np.linspace(-1.0, 1.0, 64)
    result = compare_models(signal, {"q_emp_series": np.sin(np.linspace(0, 6, 64))})
    assert result["data_mode"] == "synthetic"
    assert result["verdict"] != "PASS"
    assert result["formal"] is False


def test_invalid_empirical_input_is_inconclusive_with_provenance_reason():
    result = compare_models(np.ones(32), {"q_emp_mean": 1.0}, data_mode="empirical")
    assert result["verdict"] == "INCONCLUSIVE"
    assert result["k_value"] is None
    assert result["provenance_status"] == "missing_or_incomplete"


def test_validation_catches_small_effective_n_pairs_and_constant_signals():
    validation = validate_falsification_input(
        np.ones(32),
        data_mode="empirical",
        provenance={"dataset_id": "d", "source": "s", "source_file": "x", "sample_rate_hz": 100},
        paired_subjects=1,
        effective_sample_count=4,
        n_tests=1,
    )
    assert validation["status"] == "INCONCLUSIVE"
    assert any("constant" in error for error in validation["errors"])
    assert any("paired" in error for error in validation["errors"])
    assert any("effective" in error for error in validation["errors"])


def test_multiple_comparisons_must_be_declared_and_can_be_corrected():
    unknown = validate_falsification_input(np.arange(32.0), n_tests=3)
    assert unknown["multiplicity_status"] == "missing"
    corrected = validate_falsification_input(np.arange(32.0), n_tests=3, multiplicity_correction="holm")
    assert corrected["multiplicity_status"] == "corrected"
    adjusted = multiplicity_correction([0.01, 0.04], method="bonferroni")
    assert adjusted["status"] == "PASS"
    assert adjusted["adjusted_p_values"] == [0.02, 0.08]


def test_null_controls_are_seeded_and_labelled():
    signal = np.sin(np.linspace(0, 10, 64))
    first = generate_null_controls(signal, labels=["a", "b", "a", "b"], seed=17, block_size=8)
    second = generate_null_controls(signal, labels=["a", "b", "a", "b"], seed=17, block_size=8)
    for name in ("flat_signal", "independent_gaussian", "phase_shuffled", "stationary_surrogate"):
        assert first[name]["method"]
        assert first[name]["seed"] == 17
        assert np.array_equal(first[name]["values"], second[name]["values"])
    assert first["condition_label_permutation"] == second["condition_label_permutation"]


def test_topology_metric_names_remain_separate():
    metrics = separate_topology_metrics({"beta1_loops": 2, "q_emp_mean": 3, "chirality": 4})
    assert metrics == {"graph_beta1": 2.0, "spatial_winding_q": 3.0, "scalar_chirality": 4.0}


def test_result_schema_preserves_legacy_fields_and_adds_evidence_metadata():
    result = compare_models(np.random.default_rng(3).normal(size=64), {"q_emp_mean": 0.0})
    for key in ("bayes_factor", "verdict", "log_bayes_factor", "pitnn", "classical_wilson_cowan"):
        assert key in result
    for key in ("status", "method", "k_value", "threshold", "data_mode", "provenance_status", "sample_count", "feature_count", "effective_sample_count", "uncertainty", "controls", "warnings", "errors"):
        assert key in result
    assert result["classical_wilson_cowan"]["likelihood_status"] == "not_implemented"
