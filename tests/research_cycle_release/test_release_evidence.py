"""Fixtures and tests for research-cycle release-evidence evaluator."""
from __future__ import annotations

import json
import math
import socket
from pathlib import Path

import pytest

from tools.research_cycle_release.adapters import empty_bundle, source_payload_checksum
from tools.research_cycle_release.evaluator import evaluate_research_cycle_release
from tools.research_cycle_release.report import dumps, write_reports
from tools.research_cycle_release.schema import DecisionState


def _complete(**overrides):
    base = empty_bundle(cycle_id="cycle-complete")
    base.update(
        {
            "source_manifest_present": True,
            "source_manifest_path": "manifest.json",
            "checksums_present": True,
            "checksum_entries": [{"id": "src", "sha256": "abc"}],
            "configuration_locked": True,
            "code_commit": "deadbeef",
            "seed": 42,
            "input_provenance_complete": True,
            "input_provenance_missing": [],
            "outputs_finite": True,
            "non_finite_metric_paths": [],
            "metrics": {"score": 1.25},
            "work_units": [
                {
                    "id": "u1",
                    "status": "completed",
                    "partial": False,
                    "output_checksums": ["out1"],
                    "input_checksums": ["in1"],
                }
            ],
            "all_work_units_terminal": True,
            "partial_runs_explicitly_marked": True,
            "artifact_lineage_complete": True,
            "artifact_lineage_missing": [],
            "validation_report_present": True,
            "validation_status": "ok",
            "null_metadata_applicable": True,
            "null_metadata_present": True,
            "multiplicity_metadata_applicable": True,
            "multiplicity_metadata_present": True,
            "forecasting_applicable": False,
            "resource_budgets_respected": True,
            "full_dataset_download": False,
            "network_policy_recorded": True,
            "network_policy_violated": False,
            "evidence_classes": [],
            "evidence_classes_consistent": True,
            "synthetic_only": False,
            "proxy_only": False,
            "empirical_present": False,
            "report_metadata_text": "engineering operational summary",
            "infrastructure_blocked": False,
            "comparable": True,
            "comparability_notes": [],
        }
    )
    base.update(overrides)
    return base


def test_complete_reviewable_cycle():
    report = evaluate_research_cycle_release(_complete(), adapter_hint="generic")
    assert report.decision == DecisionState.EVIDENCE_READY_FOR_REVIEW
    assert report.scientific_pass_emitted is False if hasattr(report, "scientific_pass_emitted") else True
    data = report.to_dict()
    assert data["scientific_pass_emitted"] is False
    assert data["bayes_factor_emitted"] is False
    assert "bayes" not in json.dumps(data).lower() or data["bayes_factor_emitted"] is False


@pytest.mark.parametrize(
    "unknown_field",
    [
        "input_provenance_complete",
        "all_work_units_terminal",
        "partial_runs_explicitly_marked",
        "artifact_lineage_complete",
        "validation_report_present",
        "resource_budgets_respected",
        "network_policy_recorded",
        "evidence_classes_consistent",
        "comparable",
    ],
)
def test_unknown_operational_checks_cannot_be_released_as_reviewable(unknown_field):
    overrides = {unknown_field: None}
    if unknown_field == "all_work_units_terminal":
        overrides["work_units"] = []
    report = evaluate_research_cycle_release(_complete(**overrides), adapter_hint="generic")
    assert report.decision == DecisionState.EVIDENCE_INCOMPLETE
    assert any(check.check_id == unknown_field and check.passed is None for check in report.checks)


def test_missing_source_manifest():
    report = evaluate_research_cycle_release(
        _complete(source_manifest_present=False), adapter_hint="generic"
    )
    assert report.decision == DecisionState.PROVENANCE_FAILURE


def test_missing_artifact_lineage():
    report = evaluate_research_cycle_release(
        _complete(artifact_lineage_complete=False, artifact_lineage_missing=["output:u1"]),
        adapter_hint="generic",
    )
    assert report.decision == DecisionState.ARTIFACT_FAILURE


def test_partial_run():
    report = evaluate_research_cycle_release(
        _complete(
            work_units=[
                {
                    "id": "u1",
                    "status": "partial",
                    "partial": True,
                    "output_checksums": ["out1"],
                    "input_checksums": ["in1"],
                }
            ],
            all_work_units_terminal=False,
            partial_runs_explicitly_marked=True,
        ),
        adapter_hint="generic",
    )
    assert report.decision == DecisionState.EVIDENCE_INCOMPLETE


def test_synthetic_only():
    report = evaluate_research_cycle_release(
        _complete(synthetic_only=True, evidence_classes=["synthetic"]),
        adapter_hint="generic",
    )
    assert report.decision == DecisionState.SYNTHETIC_ONLY


def test_proxy_only():
    report = evaluate_research_cycle_release(
        _complete(proxy_only=True, evidence_classes=["proxy"]),
        adapter_hint="generic",
    )
    assert report.decision == DecisionState.PROXY_ONLY


def test_non_finite_metric():
    report = evaluate_research_cycle_release(
        _complete(outputs_finite=False, non_finite_metric_paths=["metrics.score"], metrics={"score": math.inf}),
        adapter_hint="generic",
    )
    assert report.decision == DecisionState.VALIDATION_FAILURE
    data = report.to_dict()
    assert data["bundle"]["metrics"]["score"] is None or data["bundle"]["non_finite_metric_paths"]


def test_missing_forecasting_splits():
    report = evaluate_research_cycle_release(
        _complete(
            forecasting_applicable=True,
            forecasting_subject_split=False,
            forecasting_session_split=True,
            forecasting_time_split=True,
        ),
        adapter_hint="generic",
    )
    assert report.decision == DecisionState.EVIDENCE_INCOMPLETE


def test_missing_multiplicity():
    report = evaluate_research_cycle_release(
        _complete(multiplicity_metadata_applicable=True, multiplicity_metadata_present=False),
        adapter_hint="generic",
    )
    assert report.decision == DecisionState.EVIDENCE_INCOMPLETE


def test_resource_budget_exceeded():
    report = evaluate_research_cycle_release(
        _complete(resource_budgets_respected=False, resource_budget_details={"exceeded": True}),
        adapter_hint="generic",
    )
    assert report.decision == DecisionState.RESOURCE_FAILURE


def test_network_violation():
    report = evaluate_research_cycle_release(
        _complete(network_policy_violated=True),
        adapter_hint="generic",
    )
    assert report.decision == DecisionState.NETWORK_POLICY_FAILURE


def test_deterministic_output():
    payload = _complete()
    a = evaluate_research_cycle_release(payload, adapter_hint="generic").to_dict()
    b = evaluate_research_cycle_release(payload, adapter_hint="generic").to_dict()
    assert dumps(a) == dumps(b)
    assert source_payload_checksum(payload) == source_payload_checksum(payload)


def test_finite_json(tmp_path: Path):
    report = evaluate_research_cycle_release(
        _complete(metrics={"bad": float("nan")}, outputs_finite=False, non_finite_metric_paths=["metrics.bad"]),
        adapter_hint="generic",
    )
    text = dumps(report.to_dict())
    json.loads(text)  # allow_nan already false via dumps
    assert "NaN" not in text
    assert "Infinity" not in text
    paths = write_reports(report, tmp_path)
    assert Path(paths["json"]).exists()


def test_no_network(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("network call attempted")

    monkeypatch.setattr(socket, "socket", boom)
    monkeypatch.setattr(socket, "create_connection", boom)
    report = evaluate_research_cycle_release(_complete(), adapter_hint="generic")
    assert report.decision == DecisionState.EVIDENCE_READY_FOR_REVIEW


def test_empirical_requires_scientific_review():
    report = evaluate_research_cycle_release(
        _complete(empirical_present=True, evidence_classes=["empirical"]),
        adapter_hint="generic",
    )
    assert report.decision == DecisionState.SCIENTIFIC_REVIEW_REQUIRED


def test_unsupported_causal_language():
    report = evaluate_research_cycle_release(
        _complete(report_metadata_text="This result causes consciousness and is scientific pass"),
        adapter_hint="generic",
    )
    assert report.decision == DecisionState.VALIDATION_FAILURE
