"""The valid example is a well-formed, explicitly hypothetical mapping, and nothing more."""
from __future__ import annotations

import json

from tools.research_claim_gate.gate import evaluate_claim


def _sources(mapping):
    return {source["source_id"]: source for source in mapping["sources"]}


def test_example_is_a_valid_hypothesis_mapping(valid_mapping, check):
    report = check(valid_mapping)
    assert report["contract_status"] == "VALID_HYPOTHESIS_MAPPING"
    assert report["errors"] == []


def test_example_resolves_to_existing_code(valid_mapping, check):
    implementation = check(valid_mapping)["implementation"]
    assert implementation == {
        "metric_kind": "analytic_phase_proxy",
        "metric_kind_found": True,
        "module": "validation/analytic_phase.py",
        "output_key": "phase_grad",
        "output_key_found": True,
        "resolved": True,
        "sha256_matches": True,
        "symbol": "channel_phase_gradient_metrics",
        "symbol_found": True,
    }


def test_example_grants_no_evidence(valid_mapping, check):
    report = check(valid_mapping)
    assert report["evidence_ready"] is False
    assert report["gate"]["decision"] == "CLAIM_ADMISSIBLE"
    assert report["gate"]["claim_class"] == "hypothesis"
    assert report["gate"]["scientific_eligibility"] is False
    assert report["gate"]["scientific_pass"] is False
    assert report["gate"]["formal_bayes_factor"] is None


def test_gate_reference_matches_a_direct_gate_call(valid_mapping, check):
    report = check(valid_mapping)
    interpretation = valid_mapping["interpretation"]
    first = _sources(valid_mapping)[interpretation["source_ids"][0]]
    direct = evaluate_claim({
        "claim_id": report["gate"]["claim_id"],
        "text": interpretation["proposed_interpretation"],
        "claim_class": "hypothesis",
        "evidence_class": "hypothesis",
        "data_mode": "none_declared",
        "proxy_status": "proxy",
        "provenance": {"source_id": first["source_id"], "source_uri": first["uri"], "dataset_version": first["version"]},
    })
    assert direct.decision == report["gate"]["decision"]
    assert list(direct.reason_codes) == report["gate"]["reason_codes"]


def test_report_is_deterministic_and_finite_json(valid_mapping, check):
    first = json.dumps(check(valid_mapping), sort_keys=True, allow_nan=False)
    second = json.dumps(check(valid_mapping), sort_keys=True, allow_nan=False)
    assert first == second
    assert json.loads(first)["schema"] == "NeuroTopologySim.MeasurementHypothesisReport.v2"


def test_theory_namespace_term_is_allowed_on_the_interpretation_side(valid_mapping, check):
    mapping = dict(valid_mapping)
    mapping["interpretation"] = {**valid_mapping["interpretation"], "theory_term": "TTFCD.phase_circulation"}
    report = check(mapping)
    assert report["contract_status"] == "VALID_HYPOTHESIS_MAPPING"
    assert report["errors"] == []
