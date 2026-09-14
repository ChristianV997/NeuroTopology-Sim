"""Requirement 2: every required classification dimension must be
surfaced somewhere in the composed output. This maps each item in the
task's REQUIRED WORK list to the real validator dimension/field that
carries it, and to the adapter unit test that exercises it.
"""
from __future__ import annotations

from tools.research_cycle_preflight import adapters
from tools.research_plan_quality.models import RUBRIC_DIMENSIONS

from .conftest import PRIOR_RUNS_DIR

# Required classification -> rubric dimension name it is carried by.
REQUIRED_DIMENSIONS_COVERED_BY_PLAN_RUBRIC = {
    "source identity and checksum": ("source_quality_provenance", "dataset_identity_checksum"),
    "condition labels": ("condition_label_validity",),
    "pairing and sample size": ("pairing_sample_size_adequacy",),
    "locked preprocessing": ("preprocessing_lock",),
    "split strategy": ("split_strategy",),
    "null-model metadata": ("null_model_specification",),
    "multiplicity metadata": ("multiplicity_correction",),
    "resource budgets": ("compute_resource_budget",),
    "claim calibration": ("claim_calibration",),
}


def test_every_plan_rubric_dimension_this_task_requires_exists_on_the_real_rubric():
    for dimensions in REQUIRED_DIMENSIONS_COVERED_BY_PLAN_RUBRIC.values():
        for dimension in dimensions:
            assert dimension in RUBRIC_DIMENSIONS


def test_plan_rubric_adapter_reports_all_dimensions(load_request):
    audit = adapters.run_plan_rubric(load_request("complete_plan")["plan"])
    reported = {c["dimension"] for c in audit["criteria"]}
    assert reported == set(RUBRIC_DIMENSIONS)


def test_plan_rubric_adapter_fails_closed_on_unshapeable_plan():
    audit = adapters.run_plan_rubric({"this_is_not_a_real_plan_field": True})
    assert audit["overall_status"] == "BLOCKED"
    assert any("plan_shape" in blocker for blocker in audit["hard_blockers"])


def test_plan_rubric_adapter_treats_empty_plan_as_blocked_not_passing():
    audit = adapters.run_plan_rubric(None)
    assert audit["overall_status"] == "BLOCKED"


def test_claim_gate_adapter_returns_none_for_no_claim():
    assert adapters.run_claim_gate(None) is None


def test_claim_gate_adapter_never_emits_scientific_pass_or_bayes_factor():
    result = adapters.run_claim_gate({
        "claim_id": "C1", "text": "x", "claim_class": "hypothesis", "evidence_class": "hypothesis", "data_mode": "empirical",
    })
    assert result["scientific_pass"] is False
    assert result["formal_bayes_factor"] is None


def test_artifact_lineage_adapter_returns_none_when_no_prior_run():
    assert adapters.run_artifact_lineage(None) is None


def test_artifact_lineage_adapter_classifies_partial_failed_complete_states():
    partial = adapters.run_artifact_lineage(str(PRIOR_RUNS_DIR / "partial_run"))
    failed = adapters.run_artifact_lineage(str(PRIOR_RUNS_DIR / "failed_run"))
    complete = adapters.run_artifact_lineage(str(PRIOR_RUNS_DIR / "complete_run"))
    assert partial["status"] == "PARTIAL"
    assert failed["status"] == "FAILED"
    assert complete["status"] == "COMPLETE"
    for report in (partial, failed, complete):
        assert report["read_only"] is True
        assert report["solver_executed"] is False
        assert report["heavy_runtime_imported"] is False


def test_artifact_lineage_adapter_fails_closed_on_unreadable_directory():
    report = adapters.run_artifact_lineage(str(PRIOR_RUNS_DIR / "this_directory_does_not_exist"))
    assert report["status"] == "BLOCKED"
    assert report["diagnostics"]["errors"]


def test_data_access_adapter_defaults_are_never_permissive():
    classification = adapters.classify_data_access(None)
    assert classification["network_access_requested"] is False
    assert classification["full_dataset_download_requested"] is False
    assert classification["bounded_transfer_declared"] is False
    assert classification["checksum_declared"] is False
    assert classification["violations"] == []
    assert classification["status"] == "CLEAR"


def test_data_access_adapter_rejects_full_dataset_download():
    classification = adapters.classify_data_access({"full_dataset_download_requested": True})
    assert "FULL_DATASET_DOWNLOAD_REJECTED" in classification["violations"]
    assert classification["status"] == "BLOCKED"


def test_data_access_adapter_requires_bounded_transfer_declaration_when_network_requested():
    classification = adapters.classify_data_access({"network_access_requested": True})
    assert "BOUNDED_TRANSFER_NOT_DECLARED" in classification["violations"]
    assert classification["status"] == "BLOCKED"


def test_data_access_adapter_flags_unknown_checksum_for_review_not_as_a_hard_block():
    classification = adapters.classify_data_access({
        "network_access_requested": True, "bounded_transfer_declared": True, "checksum_declared": False,
    })
    assert classification["checksum_classification"] == "checksum_unknown"
    assert classification["violations"] == []
    assert classification["status"] == "REVIEW_REQUIRED"


def test_data_access_adapter_clear_when_bounded_and_checksummed():
    classification = adapters.classify_data_access({
        "network_access_requested": True, "bounded_transfer_declared": True, "checksum_declared": True,
    })
    assert classification["status"] == "CLEAR"
