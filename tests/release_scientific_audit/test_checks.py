"""Unit tests for the individual check functions, independent of the
fixture-driven end-to-end scenarios in test_fixtures_release_decision.py."""
from __future__ import annotations

from tools.release_scientific_audit import claims_checks, decision, engineering_checks, evidence_checks, provenance_checks, topology_checks
from tools.release_scientific_audit.models import (
    CapabilitySnapshot,
    CIStatusReport,
    FalsificationPayload,
    Finding,
    MergeMatrixEntry,
    PerformanceClaim,
    ProvenanceRecord,
    ScientificGateReport,
    TestSummary,
    TopologySummary,
)

# ---------------------------------------------------------------------------
# provenance_checks
# ---------------------------------------------------------------------------

def test_provenance_no_source_kind_is_blocking():
    findings = provenance_checks.check_synthetic_vs_empirical_provenance(
        (ProvenanceRecord(component="x", source_kind=None),)
    )
    assert any(f.severity == "blocking" for f in findings)


def test_provenance_recognized_source_kind_is_info_only():
    findings = provenance_checks.check_synthetic_vs_empirical_provenance(
        (ProvenanceRecord(component="x", source_kind="empirical_local"),)
    )
    assert all(f.severity == "info" for f in findings)


def test_provenance_unrecognized_source_kind_is_warning():
    findings = provenance_checks.check_synthetic_vs_empirical_provenance(
        (ProvenanceRecord(component="x", source_kind="mystery_kind"),)
    )
    assert any(f.severity == "warning" for f in findings)


def test_effective_n_missing_is_blocking():
    findings = provenance_checks.check_sample_size_and_effective_n(
        (ProvenanceRecord(component="x", sample_size=100, effective_sample_size=None),)
    )
    assert any(f.severity == "blocking" for f in findings)


def test_effective_n_exceeding_sample_size_is_blocking():
    findings = provenance_checks.check_sample_size_and_effective_n(
        (ProvenanceRecord(component="x", sample_size=10, effective_sample_size=20),)
    )
    assert any(f.severity == "blocking" for f in findings)


def test_effective_n_valid_is_info():
    findings = provenance_checks.check_sample_size_and_effective_n(
        (ProvenanceRecord(component="x", sample_size=100, effective_sample_size=10),)
    )
    assert all(f.severity == "info" for f in findings)


def test_missing_provenance_empty_is_insufficient_data():
    findings = provenance_checks.check_missing_provenance(())
    assert len(findings) == 1
    assert findings[0].insufficient_data is True
    assert findings[0].severity == "blocking"


def test_missing_provenance_field_present_but_incomplete_is_not_insufficient_data():
    findings = provenance_checks.check_missing_provenance(
        (ProvenanceRecord(component="x", source_kind="empirical_local", dataset_id=None, seed=1),)
    )
    assert findings[0].insufficient_data is False
    assert "dataset_id" in findings[0].summary


# ---------------------------------------------------------------------------
# evidence_checks
# ---------------------------------------------------------------------------

def test_proxy_evidence_with_pass_is_blocking():
    findings = evidence_checks.check_proxy_vs_formal_evidence(
        (FalsificationPayload(component="x", verdict="PASS", evidence_kind="proxy"),), None,
    )
    assert any(f.severity == "blocking" for f in findings)


def test_formal_evidence_with_pass_is_not_blocked_by_this_rule():
    findings = evidence_checks.check_proxy_vs_formal_evidence(
        (FalsificationPayload(component="x", verdict="PASS", evidence_kind="formal"),), None,
    )
    assert not any(f.severity == "blocking" for f in findings)


def test_k_gate_pass_with_bayes_factor_below_threshold_is_blocking():
    findings = evidence_checks.check_k_gate_semantics(
        (FalsificationPayload(component="x", verdict="PASS", bayes_factor=50.0),), None,
    )
    assert any(f.severity == "blocking" and "does not exceed" in f.summary for f in findings)


def test_k_gate_pass_with_non_finite_bayes_factor_is_blocking():
    findings = evidence_checks.check_k_gate_semantics(
        (FalsificationPayload(component="x", verdict="PASS", bayes_factor=float("inf")),), None,
    )
    assert any(f.severity == "blocking" and "non-finite" in f.summary for f in findings)


def test_k_gate_pass_on_synthetic_data_mode_is_blocking():
    findings = evidence_checks.check_k_gate_semantics(
        (FalsificationPayload(component="x", verdict="PASS", bayes_factor=150.0, data_mode="synthetic"),), None,
    )
    assert any("synthetic data" in f.summary for f in findings if f.severity == "blocking")


def test_k_gate_threshold_altered_is_blocking():
    findings = evidence_checks.check_k_gate_semantics((), ScientificGateReport(k_gate_threshold=50.0))
    assert any(f.severity == "blocking" for f in findings)


def test_k_gate_declared_not_only_condition_is_blocking():
    findings = evidence_checks.check_k_gate_semantics((), ScientificGateReport(k_gate_is_only_pass_condition=False))
    assert any(f.severity == "blocking" for f in findings)


def test_null_control_absent_with_pass_is_blocking():
    findings = evidence_checks.check_null_control_presence(
        (FalsificationPayload(component="x", verdict="PASS", null_control_present=False),), None,
    )
    assert any(f.severity == "blocking" for f in findings)


def test_null_control_present_with_pass_is_clean():
    findings = evidence_checks.check_null_control_presence(
        (FalsificationPayload(component="x", verdict="PASS", null_control_present=True),), None,
    )
    assert not any(f.severity == "blocking" for f in findings)


def test_multiplicity_relevant_and_not_corrected_is_blocking():
    findings = evidence_checks.check_multiple_comparison_status(
        ScientificGateReport(multiplicity_relevant=True, multiplicity_correction_applied=False)
    )
    assert any(f.severity == "blocking" for f in findings)


def test_multiplicity_not_relevant_is_info():
    findings = evidence_checks.check_multiple_comparison_status(
        ScientificGateReport(multiplicity_relevant=False)
    )
    assert all(f.severity == "info" for f in findings)


def test_wilson_cowan_label_without_confirmation_is_blocking():
    findings = evidence_checks.check_wilson_cowan_labeling(
        ScientificGateReport(classical_baseline_label="classical_wilson_cowan", classical_baseline_is_real_wilson_cowan=None)
    )
    assert any(f.severity == "blocking" for f in findings)


def test_wilson_cowan_label_confirmed_real_is_info():
    findings = evidence_checks.check_wilson_cowan_labeling(
        ScientificGateReport(classical_baseline_label="classical_wilson_cowan", classical_baseline_is_real_wilson_cowan=True)
    )
    assert all(f.severity == "info" for f in findings)


def test_non_wilson_cowan_label_is_info():
    findings = evidence_checks.check_wilson_cowan_labeling(
        ScientificGateReport(classical_baseline_label="classical_harmonic_baseline")
    )
    assert all(f.severity == "info" for f in findings)


def test_finite_numeric_fields_flags_nan():
    findings = evidence_checks.check_finite_numeric_fields(
        (FalsificationPayload(component="x", numeric_fields=(1.0, float("nan"))),)
    )
    assert any(f.severity == "blocking" for f in findings)


def test_finite_numeric_fields_clean_for_all_finite():
    findings = evidence_checks.check_finite_numeric_fields(
        (FalsificationPayload(component="x", numeric_fields=(1.0, 2.0)),)
    )
    assert findings == []


# ---------------------------------------------------------------------------
# topology_checks
# ---------------------------------------------------------------------------

def test_topology_field_collision_across_namespaces_is_blocking():
    findings = topology_checks.check_topology_namespace_separation((
        TopologySummary(namespace="spatial_topology", fields={"beta1": 1}),
        TopologySummary(namespace="graph_topology", fields={"beta1": 2}),
    ))
    assert any(f.severity == "blocking" for f in findings)


def test_topology_separate_namespaces_no_collision_is_clean():
    findings = topology_checks.check_topology_namespace_separation((
        TopologySummary(namespace="spatial_topology", fields={"Qz_mean": 1.0}),
        TopologySummary(namespace="graph_topology", fields={"beta1": 2}),
    ))
    assert not any(f.severity == "blocking" for f in findings)


def test_topology_duplicate_namespace_is_blocking():
    findings = topology_checks.check_topology_namespace_separation((
        TopologySummary(namespace="spatial_topology", fields={"a": 1}),
        TopologySummary(namespace="spatial_topology", fields={"b": 2}),
    ))
    assert any(f.severity == "blocking" for f in findings)


def test_topology_empty_is_warning_not_blocking():
    findings = topology_checks.check_topology_namespace_separation(())
    assert findings[0].severity == "warning"


# ---------------------------------------------------------------------------
# engineering_checks
# ---------------------------------------------------------------------------

def test_performance_claim_described_as_scientific_evidence_is_blocking():
    findings = engineering_checks.check_performance_claims(
        (PerformanceClaim(label="x", metric="speedup", value=1.5, described_as_scientific_evidence=True),)
    )
    assert any(f.severity == "blocking" for f in findings)


def test_performance_claim_non_finite_is_blocking():
    findings = engineering_checks.check_performance_claims(
        (PerformanceClaim(label="x", metric="speedup", value=float("inf")),)
    )
    assert any(f.severity == "blocking" for f in findings)


def test_capability_required_but_unclassified_is_blocking():
    findings = engineering_checks.check_optional_dependency_availability(
        CapabilitySnapshot(capabilities={}, required_for_release=("torch",))
    )
    assert any(f.severity == "blocking" for f in findings)


def test_capability_required_and_classified_unavailable_is_warning_not_blocking():
    findings = engineering_checks.check_optional_dependency_availability(
        CapabilitySnapshot(capabilities={"torch": False}, required_for_release=("torch",))
    )
    assert not any(f.severity == "blocking" for f in findings)
    assert any(f.severity == "warning" for f in findings)


def test_capability_available_is_info():
    findings = engineering_checks.check_optional_dependency_availability(
        CapabilitySnapshot(capabilities={"numpy": True}, required_for_release=("numpy",))
    )
    assert all(f.severity == "info" for f in findings)


def test_ci_infrastructure_blocked_is_blocking_and_distinct_from_real_failure():
    findings = engineering_checks.check_unresolved_failures_and_timeouts(
        None, CIStatusReport(checks={"core-tests": "infrastructure_blocked"})
    )
    assert any(f.severity == "blocking" and "infrastructure" in f.summary.lower() for f in findings)


def test_ci_real_failure_is_blocking_and_says_actually_failing():
    findings = engineering_checks.check_unresolved_failures_and_timeouts(
        None, CIStatusReport(checks={"core-tests": "failing"})
    )
    assert any("actually failing" in f.summary for f in findings)


def test_test_summary_failures_and_timeouts_both_reported():
    findings = engineering_checks.check_unresolved_failures_and_timeouts(
        TestSummary(failed=2, timed_out=1, failed_ids=("a", "b"), timed_out_ids=("c",)), None,
    )
    summaries = [f.summary for f in findings if f.severity == "blocking"]
    assert any("failure" in s for s in summaries)
    assert any("timeout" in s for s in summaries)


# ---------------------------------------------------------------------------
# claims_checks
# ---------------------------------------------------------------------------

def test_claims_optimistic_label_with_no_blockers_is_a_warning_not_blocking():
    findings = claims_checks.check_claims_exceeding_evidence(
        (), ScientificGateReport(overall_status_label="CLEAN / RELEASE-READY"), [],
    )
    assert not any(f.severity == "blocking" for f in findings)


def test_claims_cautionary_label_matches_real_blockers_is_not_flagged():
    prior = [Finding("k_gate_semantics", "blocking", "bad", "x")]
    findings = claims_checks.check_claims_exceeding_evidence(
        (), ScientificGateReport(overall_status_label="INCONCLUSIVE / NOT RELEASE-READY"), prior,
    )
    assert findings == []


def test_claims_optimistic_label_with_real_blockers_is_flagged_as_warning():
    prior = [Finding("k_gate_semantics", "blocking", "bad", "x")]
    findings = claims_checks.check_claims_exceeding_evidence(
        (), ScientificGateReport(overall_status_label="CLEAN / RELEASE-READY"), prior,
    )
    assert findings and findings[0].severity == "warning"


def test_claims_merge_matrix_optimistic_reason_with_blockers_is_warning():
    prior = [Finding("k_gate_semantics", "blocking", "bad", "x")]
    findings = claims_checks.check_claims_exceeding_evidence(
        (MergeMatrixEntry("#1", "Integrated", "Validated and passed all tests"),), None, prior,
    )
    assert findings and findings[0].severity == "warning"


# ---------------------------------------------------------------------------
# decision
# ---------------------------------------------------------------------------

def test_decision_no_findings_is_release_ready():
    assert decision.derive_release_decision([])[0] == "RELEASE_READY"


def test_decision_only_warnings_is_review_only():
    findings = [Finding("x", "warning", "s", "e")]
    assert decision.derive_release_decision(findings)[0] == "REVIEW_ONLY"


def test_decision_only_insufficient_data_blockers_is_inconclusive():
    findings = [Finding("missing_provenance", "blocking", "s", "e", insufficient_data=True)]
    assert decision.derive_release_decision(findings)[0] == "INCONCLUSIVE"


def test_decision_safety_blocker_wins_over_everything():
    findings = [
        Finding("dashboard_solver_isolation", "blocking", "s", "e"),
        Finding("k_gate_semantics", "blocking", "s", "e"),
        Finding("unresolved_failures_and_timeouts", "blocking", "N CI check(s) actually failing: x", "e"),
    ]
    assert decision.derive_release_decision(findings)[0] == "BLOCKED_BY_SCIENCE"
    assert decision.derive_release_decision(findings)[1] == ("DASHBOARD_SOLVER_ISOLATION_VIOLATION",)


def test_decision_scientific_blocker_wins_over_test_and_infra():
    findings = [
        Finding("k_gate_semantics", "blocking", "s", "e"),
        Finding("unresolved_failures_and_timeouts", "blocking", "N CI check(s) actually failing: x", "e"),
    ]
    assert decision.derive_release_decision(findings)[0] == "BLOCKED_BY_SCIENCE"


def test_decision_real_test_failure_wins_over_infrastructure_when_both_present():
    findings = [
        Finding("unresolved_failures_and_timeouts", "blocking", "N CI check(s) actually failing: x", "e"),
        Finding("unresolved_failures_and_timeouts", "blocking", "N CI check(s) infrastructure/billing-blocked: y", "e"),
    ]
    assert decision.derive_release_decision(findings)[0] == "BLOCKED_BY_TESTS"


def test_decision_infrastructure_only_is_blocked_by_infrastructure():
    findings = [Finding("unresolved_failures_and_timeouts", "blocking", "N CI check(s) infrastructure/billing-blocked: y", "e")]
    assert decision.derive_release_decision(findings)[0] == "BLOCKED_BY_INFRASTRUCTURE"


def test_decision_mixed_genuine_and_insufficient_reports_genuine_category():
    findings = [
        Finding("k_gate_semantics", "blocking", "s", "e"),
        Finding("missing_provenance", "blocking", "s", "e", insufficient_data=True),
    ]
    assert decision.derive_release_decision(findings)[0] == "BLOCKED_BY_SCIENCE"
