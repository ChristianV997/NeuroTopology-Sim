"""Quality gate: status classification, the synthetic-cannot-PASS
guardrail, topology namespace separation, provenance completeness, and
finite-value checks."""
from __future__ import annotations

import math

from tools.integration_bridge import quality_gate


# ---- classify_status ----

def test_exception_is_classified_as_error_never_not_supported():
    status, notes = quality_gate.classify_status(
        raw_status=None, data_mode="empirical_local", exception_occurred=True, insufficient_data=False
    )
    assert status == "ERROR"


def test_insufficient_data_is_classified_as_inconclusive():
    status, notes = quality_gate.classify_status(
        raw_status=None, data_mode="empirical_local", exception_occurred=False, insufficient_data=True
    )
    assert status == "INCONCLUSIVE"


def test_missing_raw_status_with_no_other_flags_is_inconclusive_not_pass():
    status, notes = quality_gate.classify_status(
        raw_status=None, data_mode="empirical_local", exception_occurred=False, insufficient_data=False
    )
    assert status == "INCONCLUSIVE"


def test_synthetic_pass_is_downgraded_to_not_supported():
    status, notes = quality_gate.classify_status(
        raw_status="PASS", data_mode="synthetic", exception_occurred=False, insufficient_data=False
    )
    assert status == "NOT_SUPPORTED"
    assert any("synthetic" in note for note in notes)


def test_synthetic_demo_alias_also_blocks_pass():
    status, _ = quality_gate.classify_status(
        raw_status="PASS", data_mode="synthetic_demo", exception_occurred=False, insufficient_data=False
    )
    assert status == "NOT_SUPPORTED"


def test_empirical_pass_is_preserved():
    status, notes = quality_gate.classify_status(
        raw_status="PASS", data_mode="empirical_local", exception_occurred=False, insufficient_data=False
    )
    assert status == "PASS"


def test_falsified_prefixed_verdicts_map_to_not_supported():
    status, notes = quality_gate.classify_status(
        raw_status="FALSIFIED: NOISE_DOMINANT", data_mode="empirical_local",
        exception_occurred=False, insufficient_data=False,
    )
    assert status == "NOT_SUPPORTED"


def test_unknown_verdict_string_maps_to_inconclusive_not_silently_passed_through():
    status, notes = quality_gate.classify_status(
        raw_status="SOMETHING_NEW", data_mode="empirical_local",
        exception_occurred=False, insufficient_data=False,
    )
    assert status == "INCONCLUSIVE"


# ---- topology namespace separation ----

def test_top_level_leak_of_beta1_is_rejected():
    errors = quality_gate.check_topology_namespace_separation({"beta1_loops": 3})
    assert errors


def test_top_level_leak_of_winding_number_is_rejected():
    errors = quality_gate.check_topology_namespace_separation({"winding_number": 1.0})
    assert errors


def test_properly_namespaced_result_has_no_leak_errors():
    result = {
        "spatial_topology": {"Qz_mean": 1.0, "Qabs_mean": 2.0, "f_dress": 0.1},
        "graph_topology": {"beta1": 3},
        "scalar_chirality": {"winding_number": 0.5, "topological_charge": 0.2, "beta1_loops": 1},
    }
    assert quality_gate.check_topology_namespace_separation(result) == []


def test_graph_and_spatial_namespaces_are_never_merged():
    """The specific guardrail: graph beta_1 and spatial winding/charge must
    stay separate namespaces, never collapsed into one dict."""
    result = {
        "spatial_topology": {"Qz_mean": 1.0},
        "graph_topology": {"beta1": 2},
    }
    assert result["spatial_topology"] is not result["graph_topology"]
    assert "beta1" not in result["spatial_topology"]
    assert "Qz_mean" not in result["graph_topology"]
    assert quality_gate.check_topology_namespace_separation(result) == []


def test_non_dict_namespace_payload_is_rejected():
    errors = quality_gate.check_topology_namespace_separation({"spatial_topology": 42})
    assert errors


# ---- provenance completeness ----

def test_complete_provenance_has_no_errors():
    provenance = {"data_mode": "synthetic", "dataset_id": "d1", "source_kind": "synthetic_demo", "seed": 0}
    assert quality_gate.check_provenance_completeness(provenance) == []


def test_missing_provenance_field_is_reported():
    provenance = {"data_mode": "synthetic", "dataset_id": "d1", "seed": 0}
    errors = quality_gate.check_provenance_completeness(provenance)
    assert any("source_kind" in e for e in errors)


# ---- finite-value checks ----

def test_all_finite_true_for_ordinary_floats():
    assert quality_gate.all_finite([1.0, 2.5, -3.0])


def test_all_finite_false_for_nan():
    assert not quality_gate.all_finite([1.0, math.nan])


def test_all_finite_false_for_inf():
    assert not quality_gate.all_finite([1.0, math.inf])


# ---- evaluate() end-to-end ----

def test_evaluate_forces_error_on_missing_provenance_even_if_status_would_be_pass():
    status, report = quality_gate.evaluate(
        analysis_result={"bayesian_falsification": {"comparison": {}}},
        provenance={"data_mode": "empirical_local", "dataset_id": "d1"},  # source_kind, seed missing
        raw_status="PASS",
    )
    assert status == "ERROR"
    assert report.status == "ERROR"
    assert report.errors


def test_evaluate_downgrades_synthetic_pass_end_to_end():
    status, report = quality_gate.evaluate(
        analysis_result={"spatial_topology": {"Qz_mean": 1.0}},
        provenance={"data_mode": "synthetic", "dataset_id": "d1", "source_kind": "synthetic_demo", "seed": 0},
        raw_status="PASS",
    )
    assert status == "NOT_SUPPORTED"
    assert report.status == "NOT_SUPPORTED"


def test_evaluate_reports_error_for_non_finite_numeric_field():
    status, report = quality_gate.evaluate(
        analysis_result={"spatial_topology": {"Qz_mean": float("nan")}},
        provenance={"data_mode": "empirical_local", "dataset_id": "d1", "source_kind": "empirical_local", "seed": 0},
        raw_status="NOT_SUPPORTED",
        numeric_fields=[float("nan")],
    )
    assert status == "ERROR"
    assert not report.checks["all_numeric_fields_finite"]
