import json

import numpy as np

from sim.pitnn.bayesian_falsification import (
    bayes_factor_from_marginal_likelihoods,
    classify_falsification_status,
    compare_models,
    serialize_falsification_result,
)


def test_legacy_fields_remain_available_but_are_explicitly_deprecated():
    result = compare_models(np.random.default_rng(11).normal(size=64), {"q_emp_mean": 0.0})
    assert isinstance(result["bayes_factor"], (int, float))
    assert result["verdict"] in {"NOT_SUPPORTED", "INCONCLUSIVE"}
    assert result["legacy_bayes_factor_status"] == "deprecated_numeric_compatibility_alias"
    assert "Do not interpret bayes_factor" in result["legacy_bayes_factor_warning"]
    assert "LEGACY_NUMERIC_BAYES_FACTOR_DEPRECATED" in result["reason_codes"]


def test_proxy_result_has_no_formal_bayes_factor():
    result = compare_models(np.random.default_rng(12).normal(size=64), {"q_emp_mean": 0.0})
    assert result["evidence_kind"] == "proxy"
    assert result["is_proxy"] is True
    assert result["is_formal"] is False
    assert result["formal_bayes_factor"] is None
    assert result["proxy_value"] == result["k_value"]
    assert "PROXY_ONLY" in result["reason_codes"]
    assert "WILSON_COWAN_PROXY" in result["reason_codes"]


def test_formal_result_is_separate_and_cannot_pass_without_empirical_metadata():
    result = bayes_factor_from_marginal_likelihoods(101.0, 1.0)
    assert result["evidence_kind"] == "formal"
    assert result["is_formal"] is True
    assert result["is_proxy"] is False
    assert result["formal_bayes_factor"] is not None
    assert result["proxy_value"] is None
    assert classify_falsification_status(result) == "INCONCLUSIVE"


def test_formal_mapping_can_pass_only_when_all_metadata_is_present():
    result = bayes_factor_from_marginal_likelihoods(101.0, 1.0)
    result.update(
        {
            "data_mode": "empirical",
            "provenance_status": "complete",
            "effective_sample_count": 32,
            "multiplicity_correction_status": "not_needed",
            "controls": {"passed": True},
            "evidence_eligible": True,
            "model_comparison_supported": True,
            "validation": {"status": "VALID"},
        }
    )
    enriched = serialize_falsification_result(result)
    assert enriched["scientific_eligibility"] is True
    assert classify_falsification_status(enriched) == "PASS"


def test_invalid_data_has_null_k_and_reason_codes():
    result = compare_models(np.ones(32), {"q_emp_mean": 1.0}, data_mode="empirical")
    assert result["verdict"] == "INCONCLUSIVE"
    assert result["k_value"] is None
    assert result["formal_bayes_factor"] is None
    assert "INVALID_INPUT" in result["reason_codes"]


def test_insufficient_samples_are_not_evidence():
    result = compare_models(
        np.arange(7.0),
        {"q_emp_mean": 1.0},
        data_mode="empirical",
        provenance={"dataset_id": "d", "source": "s", "source_file": "x", "sample_rate_hz": 100},
        n_tests=1,
    )
    assert result["verdict"] == "INCONCLUSIVE"
    assert "INSUFFICIENT_SAMPLE_SIZE" in result["reason_codes"]


def test_unknown_multiple_comparisons_are_not_silent():
    result = compare_models(
        np.arange(64.0),
        {"q_emp_mean": 1.0},
        data_mode="empirical",
        provenance={"dataset_id": "d", "source": "s", "source_file": "x", "sample_rate_hz": 100},
        n_tests=2,
    )
    assert result["verdict"] == "INCONCLUSIVE"
    assert result["multiplicity_correction_status"] == "missing"
    assert "MULTIPLICITY_UNDECLARED" in result["reason_codes"]


def test_pure_noise_null_is_synthetic_and_cannot_pass():
    signal = np.random.default_rng(99).normal(size=128)
    result = compare_models(signal, {"q_emp_series": np.random.default_rng(3).normal(size=128)})
    assert result["data_status"] == "synthetic"
    assert result["verdict"] != "PASS"
    assert "SYNTHETIC_DATA" in result["reason_codes"]


def test_repeated_results_and_serialization_are_deterministic():
    signal = np.random.default_rng(7).normal(size=64)
    first = serialize_falsification_result(compare_models(signal, {"q_emp_mean": 0.0}))
    second = serialize_falsification_result(compare_models(signal, {"q_emp_mean": 0.0}))
    assert first == second
    assert json.dumps(first, sort_keys=True, allow_nan=False) == json.dumps(second, sort_keys=True, allow_nan=False)


def test_json_serializer_preserves_null_semantics_and_no_nan_values():
    result = serialize_falsification_result(
        {
            "status": "INCONCLUSIVE",
            "verdict": "INCONCLUSIVE",
            "method": "bic_proxy",
            "formal": False,
            "k_value": None,
            "bayes_factor": 0.0,
            "data_mode": "empirical",
            "sample_count": 7,
            "effective_sample_count": 7,
            "errors": ["short input"],
            "nan_value": float("nan"),
        }
    )
    encoded = json.dumps(result, sort_keys=True, allow_nan=False)
    decoded = json.loads(encoded)
    assert decoded["k_value"] is None
    assert decoded["formal_bayes_factor"] is None
    assert decoded["proxy_value"] is None
    assert decoded["nan_value"] is None
