from __future__ import annotations

import json
import socket

import pytest

from tools.higher_order_integration.triadic_adapter import (
    FEATURE_SCHEMA_VERSION,
    INPUT_SCHEMA_VERSION,
    TriadicContractError,
    adapt_triadic_output,
    validate_serialized_feature_record,
)


def valid_envelope(*, synthetic: bool = True) -> dict:
    source = "a" * 64
    provenance = "b" * 64
    return {
        "schema_version": INPUT_SCHEMA_VERSION,
        "channels": ["C1", "C2", "C3", "C4"],
        "window": {
            "window_id": "window-0001",
            "start_s": 0.0,
            "end_s": 2.0,
            "sample_count": 200,
            "sampling_rate_hz": 100.0,
            "units": "uV" if not synthetic else "a.u.",
            "condition_labels": ["rest"],
        },
        "method": {
            "estimator": "combined_matrix_entropy_residualized",
            "surrogate_method": "none",
            "seed": 17,
        },
        "resources": {
            "candidate_count": 2,
            "max_triads": 4,
            "bounded": True,
            "memory_telemetry": {
                "estimated_input_memory_bytes": 6400,
                "estimated_candidate_memory_bytes": 4096,
            },
        },
        "provenance": {
            "source_id": "synthetic://triadic-test" if synthetic else "dataset-recording-01",
            "source_checksum": source,
            "provenance_checksum": provenance,
            "data_mode": "synthetic_demo" if synthetic else "empirical",
            "synthetic_demo": synthetic,
            "evidence_class": "synthetic_demo" if synthetic else "empirical_provenance_complete",
        },
        "result": {
            "interactions": [
                {
                    "triad_id": "triad:0,1,2",
                    "channel_indices": [0, 1, 2],
                    "matrix_entropy_score": 0.4,
                    "nonlinear_interaction_score": 0.3,
                    "combined_score": 0.35,
                    "sample_count": 200,
                    "condition_label": "rest",
                },
                {
                    "triad_id": "triad:0,1,3",
                    "channel_indices": [0, 1, 3],
                    "matrix_entropy_score": 0.2,
                    "nonlinear_interaction_score": 0.1,
                    "combined_score": 0.15,
                    "sample_count": 200,
                    "condition_label": "rest",
                },
            ],
            "top_triads": [{"triad_id": "triad:0,1,2"}],
            "complexity_telemetry": {
                "input_channels": 4,
                "candidate_count": 2,
            },
            "controls": {
                "pairwise_connectivity": {"status": "available", "metric": 0.1},
                "psd_control": {"status": "available", "metric": 0.2},
                "common_driver_control": {"status": "available", "metric": 0.05},
            },
            "warnings": [],
        },
    }


def test_valid_output_has_explicit_schema_and_separate_namespaces():
    record = adapt_triadic_output(valid_envelope())
    data = record.to_dict()
    assert data["schema_version"] == FEATURE_SCHEMA_VERSION
    assert data["evidence_class"] == "synthetic_demo"
    assert data["features"]["triadic_statistical_dependence"]["statistical_interpretation"] == "triadic_statistical_dependence_only"
    assert data["features"]["graph_beta_1"] == {"status": "separate_namespace", "value": None}
    assert data["features"]["spatial_phase_charge"]["value"] is None
    validate_serialized_feature_record(data)


def test_pr279_result_shape_is_accepted_without_importing_the_solver():
    envelope = valid_envelope()
    envelope["resources"]["candidate_triads"] = envelope["resources"].pop("candidate_count")
    result = envelope["result"]
    for item in result["interactions"]:
        item["channels"] = item.pop("channel_indices")
        item["channel_labels"] = [envelope["channels"][index] for index in item["channels"]]
        item.pop("triad_id")
    result["top_triads"] = [dict(result["interactions"][0])]
    result["pairwise_control"] = result["controls"].pop("pairwise_connectivity")
    result["psd_control"] = result["controls"].pop("psd_control")
    result["complexity_telemetry"]["candidate_triads"] = result["complexity_telemetry"].pop("candidate_count")
    record = adapt_triadic_output(envelope)
    assert record.to_dict()["features"]["pairwise_connectivity"]["status"] == "available"
    assert record.to_dict()["features"]["triadic_statistical_dependence"]["triads"][0]["triad_id"] == "triad:0,1,2"


def test_empirical_status_requires_and_preserves_explicit_provenance():
    data = adapt_triadic_output(valid_envelope(synthetic=False)).to_dict()
    assert data["synthetic_demo"] is False
    assert data["evidence_class"] == "empirical_provenance_complete"
    assert data["provenance"]["data_mode"] == "empirical"


def test_missing_units_sampling_rate_or_source_checksum_is_rejected():
    for field_path in (("window", "units"), ("window", "sampling_rate_hz"), ("provenance", "source_checksum")):
        envelope = valid_envelope()
        envelope[field_path[0]].pop(field_path[1])
        with pytest.raises(TriadicContractError):
            adapt_triadic_output(envelope)


def test_nonfinite_scores_and_malformed_shapes_are_rejected():
    envelope = valid_envelope()
    envelope["result"]["interactions"][0]["combined_score"] = float("nan")
    with pytest.raises(TriadicContractError):
        adapt_triadic_output(envelope)

    envelope = valid_envelope()
    envelope["result"]["interactions"][0]["channel_indices"] = [0, 1]
    with pytest.raises(TriadicContractError):
        adapt_triadic_output(envelope)


def test_duplicate_channels_triads_and_invalid_ids_are_rejected():
    envelope = valid_envelope()
    envelope["channels"][1] = envelope["channels"][0]
    with pytest.raises(TriadicContractError):
        adapt_triadic_output(envelope)

    envelope = valid_envelope()
    envelope["result"]["interactions"].append(dict(envelope["result"]["interactions"][0]))
    with pytest.raises(TriadicContractError):
        adapt_triadic_output(envelope)

    envelope = valid_envelope()
    envelope["result"]["interactions"][0]["triad_id"] = "graph-beta1:0,1,2"
    with pytest.raises(TriadicContractError):
        adapt_triadic_output(envelope)


def test_deterministic_ordering_and_repeat_are_stable():
    first = adapt_triadic_output(valid_envelope())
    second = adapt_triadic_output(valid_envelope())
    assert first.to_json() == second.to_json()
    envelope = valid_envelope()
    envelope["result"]["interactions"].reverse()
    reordered = adapt_triadic_output(envelope)
    assert [item["triad_id"] for item in reordered.to_dict()["features"]["triadic_statistical_dependence"]["triads"]] == [
        "triad:0,1,2",
        "triad:0,1,3",
    ]


def test_unbounded_candidates_synthetic_empirical_confusion_and_behavior_labels_rejected():
    envelope = valid_envelope()
    envelope["resources"]["candidate_count"] = 5
    with pytest.raises(TriadicContractError):
        adapt_triadic_output(envelope)

    envelope = valid_envelope()
    envelope["provenance"]["data_mode"] = "empirical"
    with pytest.raises(TriadicContractError):
        adapt_triadic_output(envelope)

    envelope = valid_envelope()
    envelope["behavior_label"] = "inferred"
    with pytest.raises(TriadicContractError):
        adapt_triadic_output(envelope)


def test_topology_labels_cannot_be_attached_to_statistical_scores():
    envelope = valid_envelope()
    envelope["result"]["interactions"][0]["spatial_charge"] = 0.4
    with pytest.raises(TriadicContractError):
        adapt_triadic_output(envelope)


def test_channel_permutation_is_normalized_to_channel_identity():
    envelope = valid_envelope()
    envelope["channels"] = ["C3", "C1", "C2", "C4"]
    interactions = envelope["result"]["interactions"]
    for item in interactions:
        item["channel_indices"] = [2, 1, 0] if item["triad_id"] == "triad:0,1,2" else [2, 1, 3]
        item["triad_id"] = "triad:0,1,2" if item["triad_id"] == "triad:0,1,2" else "triad:1,2,3"
    envelope["result"]["top_triads"] = [{"triad_id": "triad:0,1,2"}]
    record = adapt_triadic_output(envelope)
    assert record.to_dict()["features"]["triadic_statistical_dependence"]["triads"][0]["channel_names"] == ["C3", "C1", "C2"]


def test_finite_json_uses_null_for_unavailable_control_values():
    envelope = valid_envelope()
    envelope["result"]["controls"]["pairwise_connectivity"]["optional_metric"] = float("inf")
    data = adapt_triadic_output(envelope).to_dict()
    assert data["features"]["pairwise_connectivity"]["optional_metric"] is None
    assert "Infinity" not in json.dumps(data, allow_nan=False)


def test_no_network_behavior(monkeypatch):
    def fail_socket(*args, **kwargs):
        raise AssertionError("network access is forbidden")

    monkeypatch.setattr(socket, "socket", fail_socket)
    record = adapt_triadic_output(valid_envelope())
    assert record.to_dict()["validation_findings"]["status"] == "VALID"
