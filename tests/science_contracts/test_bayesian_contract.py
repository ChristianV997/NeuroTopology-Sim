from __future__ import annotations

import numpy as np

from sim.pitnn.bayesian_falsification import (
    bayes_factor_from_marginal_likelihoods,
    bayes_factor_proxy_from_rss,
    classify_falsification_status,
    compare_models,
    validate_falsification_input,
)


def _passing_controls() -> dict:
    return {"phase_randomization": {"status": "PASS", "seed": 0, "method": "fft_phase_randomization"}}


def _empirical_kwargs() -> dict:
    return {
        "data_mode": "empirical_local",
        "provenance_status": "complete",
        "analysis_interpretable": True,
        "controls": _passing_controls(),
        "method": "formal_marginal_likelihood",
        "validation_status": "VALID",
        "multiplicity_status": "not_needed",
        "effective_sample_count": 32,
    }


def test_formal_k_threshold_mapping_is_strict():
    assert classify_falsification_status(99.999, **_empirical_kwargs()) == "NOT_SUPPORTED"
    assert classify_falsification_status(100.0, **_empirical_kwargs()) == "NOT_SUPPORTED"
    assert classify_falsification_status(100.001, **_empirical_kwargs()) == "PASS"


def test_invalid_or_missing_k_is_inconclusive():
    assert classify_falsification_status(None, **_empirical_kwargs()) == "INCONCLUSIVE"
    assert classify_falsification_status(float("nan"), **_empirical_kwargs()) == "INCONCLUSIVE"
    assert classify_falsification_status(-1.0, **_empirical_kwargs()) == "INCONCLUSIVE"


def test_synthetic_input_cannot_pass():
    assert classify_falsification_status(
        1_000.0,
        data_mode="synthetic_demo",
        provenance_status="synthetic",
        analysis_interpretable=True,
        controls=_passing_controls(),
        method="formal_marginal_likelihood",
    ) == "NOT_SUPPORTED"


def test_provenance_and_input_validation_fail_closed():
    signal = np.linspace(-1.0, 1.0, 32)
    incomplete = validate_falsification_input(
        signal,
        {"q_emp_mean": 0.1},
        data_mode="empirical_local",
        provenance={"dataset_id": "ds-test"},
    )
    assert incomplete["status"] == "INCONCLUSIVE"
    assert incomplete["provenance_status"] == "incomplete"

    constant = validate_falsification_input(
        np.ones(32),
        {"q_emp_mean": 0.1},
        data_mode="empirical_local",
        provenance={"dataset_id": "ds-test", "source": "local.csv", "sample_rate_hz": 250},
    )
    assert constant["status"] == "INCONCLUSIVE"
    assert any("constant" in error for error in constant["errors"])

    paired = validate_falsification_input(
        signal,
        {"q_emp_mean": 0.1},
        data_mode="empirical_local",
        provenance={"dataset_id": "ds-test", "source": "local.csv", "sample_rate_hz": 250},
        paired_subjects=1,
    )
    assert paired["status"] == "INCONCLUSIVE"
    assert any("paired" in error for error in paired["errors"])


def test_proxy_is_explicit_and_structured():
    result = bayes_factor_proxy_from_rss(1.0, 2.0, n=40, k_model=3, k_null=2)
    assert result["method"] == "bic_proxy"
    assert result["formal"] is False
    assert result["parameter_count"] == {"model": 3, "null": 2}
    assert result["model"]["aicc"] != result["null"]["aicc"]
    assert result["k_value"] > 1.0


def test_formal_marginal_likelihood_result_is_not_rss_proxy():
    result = bayes_factor_from_marginal_likelihoods(
        101.0,
        1.0,
        model_prior=0.5,
        null_prior=0.5,
        assumptions={"likelihood": "declared"},
    )
    assert result["method"] == "formal_marginal_likelihood"
    assert result["formal"] is True
    assert result["k_value"] == 101.0
    assert result["posterior_odds"] == 101.0


def test_compare_models_keeps_legacy_keys_and_blocks_synthetic_pass():
    x = np.linspace(0.0, 1.0, 64)
    signal = np.sin(2 * np.pi * x) + 0.05 * np.cos(10 * np.pi * x)
    result = compare_models(signal, {"q_emp_series": np.sin(4 * np.pi * x)})
    for key in ("status", "method", "k_value", "threshold", "data_mode", "provenance_status", "sample_count", "feature_count", "uncertainty", "controls", "warnings", "errors"):
        assert key in result
    assert result["data_mode"] == "synthetic"
    assert result["verdict"] != "PASS"
    assert result["bayes_factor"] == result["k_value"]
