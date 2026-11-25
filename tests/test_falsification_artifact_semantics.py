"""Contract tests for falsification artifact consumers.

These tests exercise only the offline API/export boundary. They intentionally
do not execute a solver or claim that the current proxy is a Wilson--Cowan
likelihood.
"""

import json

import numpy as np

from runs.run_record import RunRecordV1
from scripts.export_dsim_artifacts import export_artifacts
from sim.pitnn.api_bridge import (
    canonical_json,
    export_falsification_payload,
    export_topology_trace_payload,
    serialize_falsification_result,
)


def _formal_report(**overrides):
    report = {
        "evidence_method": "formal_marginal_likelihood",
        "formal_bayes_factor": 101.0,
        "bayes_factor": 101.0,
        "verdict": "PASS",
        "data_mode": "empirical",
        "empirical_provenance": {
            "status": "complete",
            "dataset_id": "ds-local-test",
            "source": "local fixture supplied by the caller",
            "source_file": "inputs/example.edf",
            "sample_rate_hz": 256.0,
        },
        "sample_count": 64,
        "effective_sample_count": 32,
        "null_control_status": {"status": "passed", "passed": True},
        "multiplicity_status": "not_needed",
        "model_comparison_status": "formal",
        "analysis_interpretable": True,
    }
    report.update(overrides)
    return report


def test_caller_supplied_formal_metadata_cannot_pass():
    payload = serialize_falsification_result(_formal_report())
    assert payload["evidence_method"] == "formal_marginal_likelihood"
    assert payload["formal_bayes_factor"] is None
    assert payload["unverified_formal_ratio"] == 101.0
    assert payload["proxy_bayes_factor"] is None
    assert payload["scientific_eligibility"] is False
    assert payload["verdict"] == "INCONCLUSIVE"
    assert payload["synthetic_demo"] is False


def test_synthetic_proxy_pass_is_rejected_and_value_is_preserved():
    payload = export_falsification_payload({
        "source_kind": "synthetic_demo",
        "evidence_method": "bic_proxy",
        "proxy_bayes_factor": 250.0,
        "bayes_factor": 250.0,
        "verdict": "PASS",
        "comparison": {"pitnn": {"rss": 1.0, "aicc": 2.0}, "classical_wilson_cowan": {"rss": 3.0, "aicc": 4.0}},
    })
    assert payload["synthetic_demo"] is True
    assert payload["proxy_bayes_factor"] == 250.0
    assert payload["formal_bayes_factor"] is None
    assert payload["bayes_factor"] == 250.0  # legacy numeric compatibility
    assert payload["verdict"] == "NOT_SUPPORTED"
    assert payload["scientific_eligibility"] is False
    assert "PROXY_ONLY" in payload["reason_codes"]
    assert "SYNTHETIC_PASS_REJECTED" in payload["reason_codes"]


def test_empirical_formal_evidence_with_incomplete_provenance_is_inconclusive():
    payload = serialize_falsification_result(_formal_report(empirical_provenance={}))
    assert payload["formal_bayes_factor"] is None
    assert payload["unverified_formal_ratio"] == 101.0
    assert payload["empirical_provenance"]["status"] == "incomplete"
    assert payload["verdict"] == "INCONCLUSIVE"
    assert payload["scientific_eligibility"] is False
    assert "INCOMPLETE_PROVENANCE" in payload["reason_codes"]


def test_legacy_numeric_bayes_factor_is_not_inferred_as_formal():
    payload = serialize_falsification_result({"bayes_factor": 250.0, "verdict": "PASS"})
    assert payload["evidence_kind"] == "unknown"
    assert payload["formal_bayes_factor"] is None
    assert payload["proxy_bayes_factor"] is None
    assert payload["bayes_factor_legacy_compatibility"]["value"] == 250.0
    assert payload["bayes_factor_legacy_compatibility"]["deprecated"] is True
    assert payload["verdict"] == "INCONCLUSIVE"
    assert "UNKNOWN_EVIDENCE_METHOD" in payload["reason_codes"]


def test_unknown_evidence_method_cannot_be_promoted_by_a_numeric_value():
    payload = serialize_falsification_result(_formal_report(
        evidence_method="future_unknown_method",
        formal_bayes_factor=500.0,
    ))
    assert payload["evidence_kind"] == "unknown"
    assert payload["formal_bayes_factor"] is None
    assert payload["verdict"] == "INCONCLUSIVE"
    assert "UNKNOWN_EVIDENCE_METHOD" in payload["reason_codes"]


def test_nonfinite_artifact_values_become_json_null():
    payload = serialize_falsification_result({
        "evidence_method": "formal_marginal_likelihood",
        "formal_bayes_factor": np.nan,
        "bayes_factor": np.inf,
        "verdict": "INCONCLUSIVE",
        "nonfinite_metric": -np.inf,
    })
    encoded = json.dumps(payload, sort_keys=True, allow_nan=False)
    decoded = json.loads(encoded)
    assert decoded["formal_bayes_factor"] is None
    assert decoded["bayes_factor_legacy_compatibility"]["value"] is None


def test_serialization_is_deterministic_and_json_safe():
    first = serialize_falsification_result(_formal_report())
    second = serialize_falsification_result(_formal_report())
    assert first == second
    assert canonical_json(first) == canonical_json(second)


def test_topology_observables_remain_separate():
    payload = export_topology_trace_payload([{
        "time_s": 0.0,
        "winding_number": 1.0,
        "topological_charge": 0.25,
        "beta1_loops": 2,
        "scalar_chirality": -0.5,
    }])
    assert payload["graph_beta1"] == [2]
    assert payload["winding_number"] == [1.0]
    assert payload["topological_charge"] == [0.25]
    assert payload["scalar_chirality"] == [-0.5]


def test_run_record_v1_round_trip_remains_unchanged():
    payload = serialize_falsification_result({"source_kind": "synthetic_demo", "bayes_factor": 1.0})
    record = RunRecordV1.make(
        "artifact-consumer-test",
        "hypothesis",
        data_mode="synthetic_demo",
        verdict=payload["verdict"],
        metrics={"falsification": payload},
    )
    restored = RunRecordV1.from_dict(record.to_dict())
    assert restored.schema_version == record.schema_version
    assert restored.metrics["falsification"]["semantic_schema"] == "PITNN.FalsificationConsumer.v1"


def test_exported_artifact_keeps_existing_schema_and_adds_semantics(tmp_path):
    summary = tmp_path / "summary.json"
    summary.write_text(json.dumps({
        "source_kind": "synthetic_demo",
        "bayes_factor": 1.0,
        "verdict": "NOT_SUPPORTED",
        "comparison": {
            "pitnn": {"rss": 1.0, "aicc": 2.0},
            "classical_wilson_cowan": {"rss": 2.0, "aicc": 3.0},
        },
    }), encoding="utf-8")
    manifest = export_artifacts(summary, output_dir=tmp_path / "out")
    assert manifest["schema"] == "PITNN.DSIM.Manifest.v1"
    artifact = json.loads((tmp_path / "out" / "falsification_summary.json").read_text(encoding="utf-8"))
    assert artifact["schema"] == "PITNN.DSIM.Falsification.v1"
    assert artifact["bayes_factor"] == 1.0
    assert artifact["formal_bayes_factor"] is None
    assert artifact["synthetic_demo"] is True


def test_consumer_is_offline(monkeypatch):
    import socket

    def fail_network(*args, **kwargs):
        raise AssertionError("network access is forbidden in artifact consumers")

    monkeypatch.setattr(socket, "create_connection", fail_network)
    payload = serialize_falsification_result({"source_kind": "synthetic_demo", "bayes_factor": 1.0})
    assert payload["verdict"] == "NOT_SUPPORTED"
