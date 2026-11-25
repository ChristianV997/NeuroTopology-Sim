"""Exhaustive unit tests for governance/merge_gate.py.

Every test constructs a MergeGateInput in-memory and asserts on the
returned MergeGateDecision -- no fixture files, no git, no network
anywhere in this file.
"""
from __future__ import annotations

from governance.merge_gate import DECISION_STATES, MergeGateInput, evaluate


def _base(**overrides) -> MergeGateInput:
    """A fully-green baseline input: every override starts from a PR that
    would be READY_FOR_MERGE, so each test only needs to override the one
    field it's actually testing."""
    defaults = dict(
        pr_state="open", draft=False, branch_present=True, pr_present=True,
        mergeable=True, is_stacked=False, required_checks={"tests": "passing"},
        governance_validated=True, secret_scan_clean=True,
    )
    defaults.update(overrides)
    return MergeGateInput(**defaults)


# ---------------------------------------------------------------------------
# Baseline / decision-state coverage
# ---------------------------------------------------------------------------

def test_fully_green_input_is_ready_for_merge():
    decision = evaluate(_base())
    assert decision.decision == "READY_FOR_MERGE"
    assert "ALL_GATES_PASSED" in decision.reason_codes


def test_every_decision_state_is_reachable():
    """A meta-test: construct one input per decision state and confirm
    all eight are actually producible, not just declared in
    DECISION_STATES."""
    reachable = {
        evaluate(_base()).decision,
        evaluate(_base(draft=True)).decision,
        evaluate(_base(is_stacked=True, stack_dependency_resolved=False)).decision,
        evaluate(_base(required_checks={"tests": "failing"})).decision,
        evaluate(_base(infrastructure_blocked=True)).decision,
        evaluate(_base(scientific_review_required=True)).decision,
        evaluate(_base(duplicate=True)).decision,
        evaluate(_base(dashboard_imports_solver=True)).decision,
    }
    assert reachable == DECISION_STATES


def test_decision_to_dict_is_json_shaped():
    decision = evaluate(_base())
    payload = decision.to_dict()
    assert payload["decision"] == "READY_FOR_MERGE"
    assert isinstance(payload["reason_codes"], list)


# ---------------------------------------------------------------------------
# Rule 1: a PR with unstarted checks is not passing
# ---------------------------------------------------------------------------

def test_not_run_check_is_not_ready_for_merge():
    decision = evaluate(_base(required_checks={"tests": "not_run"}))
    assert decision.decision != "READY_FOR_MERGE"
    assert decision.decision == "READY_FOR_REVIEW"
    assert "CHECKS_INCOMPLETE" in decision.reason_codes


def test_pending_check_is_not_ready_for_merge():
    decision = evaluate(_base(required_checks={"tests": "pending"}))
    assert decision.decision == "READY_FOR_REVIEW"


def test_unrecognized_check_state_defaults_to_not_run_never_passing():
    decision = evaluate(_base(required_checks={"tests": "some_new_unknown_state"}))
    assert decision.decision == "READY_FOR_REVIEW"
    assert "CHECKS_INCOMPLETE" in decision.reason_codes


def test_missing_governance_validation_blocks_merge_readiness():
    """Rule 7 folded through rule 1: governance_validated=None means the
    'governance' pseudo-check is not_run, which alone is enough to keep
    the PR out of READY_FOR_MERGE."""
    decision = evaluate(_base(governance_validated=None))
    assert decision.decision != "READY_FOR_MERGE"


def test_missing_secret_scan_blocks_merge_readiness():
    decision = evaluate(_base(secret_scan_clean=None))
    assert decision.decision != "READY_FOR_MERGE"


def test_failed_governance_validation_is_blocked_by_ci():
    decision = evaluate(_base(governance_validated=False))
    assert decision.decision == "BLOCKED_BY_CI"
    assert any("governance" in code for code in decision.reason_codes)


def test_failed_secret_scan_is_blocked_by_ci():
    decision = evaluate(_base(secret_scan_clean=False))
    assert decision.decision == "BLOCKED_BY_CI"
    assert any("secret_scan" in code for code in decision.reason_codes)


# ---------------------------------------------------------------------------
# Rule 2: billing-blocked checks are not test failures and not passes
# ---------------------------------------------------------------------------

def test_billing_blocked_check_is_not_blocked_by_ci():
    decision = evaluate(_base(required_checks={"tests": "billing_blocked"}))
    assert decision.decision != "BLOCKED_BY_CI"
    assert decision.decision == "BLOCKED_BY_INFRASTRUCTURE"
    assert "BILLING_BLOCKED" in decision.reason_codes


def test_billing_blocked_check_is_not_ready_for_merge():
    decision = evaluate(_base(required_checks={"tests": "billing_blocked"}))
    assert decision.decision != "READY_FOR_MERGE"


def test_billing_blocked_flag_alone_also_blocks():
    decision = evaluate(_base(billing_blocked=True))
    assert decision.decision == "BLOCKED_BY_INFRASTRUCTURE"
    assert "BILLING_BLOCKED" in decision.reason_codes


def test_billing_blocked_reason_code_distinct_from_infrastructure_blocked_reason_code():
    billing = evaluate(_base(required_checks={"tests": "billing_blocked"}))
    infra = evaluate(_base(required_checks={"tests": "infrastructure_blocked"}))
    assert billing.reason_codes[0] != infra.reason_codes[0]
    assert billing.reason_codes[0] == "BILLING_BLOCKED"
    assert infra.reason_codes[0] == "INFRASTRUCTURE_BLOCKED"


# ---------------------------------------------------------------------------
# Rule 3: a scientific PR with synthetic PASS claims is rejected
# ---------------------------------------------------------------------------

def test_synthetic_data_with_empirical_pass_claim_is_rejected():
    decision = evaluate(_base(synthetic_data_claims=True, claims_empirical_pass=True))
    assert decision.decision == "REJECTED_UNSAFE"
    assert "SYNTHETIC_EMPIRICAL_PASS_CLAIM" in decision.reason_codes


def test_synthetic_data_without_pass_claim_is_not_rejected_on_that_basis():
    decision = evaluate(_base(synthetic_data_claims=True, claims_empirical_pass=False))
    assert decision.decision != "REJECTED_UNSAFE"


def test_empirical_pass_claim_without_synthetic_data_is_not_rejected_on_that_basis():
    decision = evaluate(_base(synthetic_data_claims=False, claims_empirical_pass=True))
    assert decision.decision != "REJECTED_UNSAFE"


def test_rejection_takes_priority_over_everything_else():
    """Even a PR that would otherwise be perfectly green is rejected the
    moment a synthetic-empirical-PASS claim is present."""
    decision = evaluate(_base(synthetic_data_claims=True, claims_empirical_pass=True))
    assert decision.decision == "REJECTED_UNSAFE"


# ---------------------------------------------------------------------------
# Rule 4: a proxy Bayes factor cannot satisfy a formal evidence gate
# ---------------------------------------------------------------------------

def test_proxy_bayes_factor_for_formal_gate_is_rejected():
    decision = evaluate(_base(requires_formal_bayes_factor=True, bayes_factor_evidence_kind="proxy"))
    assert decision.decision == "REJECTED_UNSAFE"
    assert "PROXY_BAYES_FACTOR_FOR_FORMAL_GATE" in decision.reason_codes


def test_formal_bayes_factor_for_formal_gate_is_not_rejected_on_that_basis():
    decision = evaluate(_base(requires_formal_bayes_factor=True, bayes_factor_evidence_kind="formal"))
    assert decision.decision != "REJECTED_UNSAFE"


def test_proxy_bayes_factor_when_formal_gate_not_required_is_fine():
    decision = evaluate(_base(requires_formal_bayes_factor=False, bayes_factor_evidence_kind="proxy"))
    assert decision.decision != "REJECTED_UNSAFE"


def test_no_bayes_factor_kind_with_formal_gate_required_is_not_rejected_by_this_rule():
    """None is not "proxy" -- absence of a Bayes-factor claim at all is a
    different situation than an explicitly-proxy one satisfying a formal
    gate; this rule only fires on an explicit proxy/formal mismatch."""
    decision = evaluate(_base(requires_formal_bayes_factor=True, bayes_factor_evidence_kind=None))
    assert decision.decision != "REJECTED_UNSAFE"


# ---------------------------------------------------------------------------
# Rule 5: a stacked PR cannot be merge-ready until its dependency is
# resolved or its effective diff is independently validated
# ---------------------------------------------------------------------------

def test_stacked_with_unresolved_dependency_is_blocked():
    decision = evaluate(_base(is_stacked=True, stack_dependency_resolved=False))
    assert decision.decision == "BLOCKED_BY_DEPENDENCY"
    assert "STACKED_DEPENDENCY_UNRESOLVED" in decision.reason_codes


def test_stacked_with_unknown_dependency_state_is_blocked():
    decision = evaluate(_base(is_stacked=True, stack_dependency_resolved=None))
    assert decision.decision == "BLOCKED_BY_DEPENDENCY"


def test_stacked_with_resolved_dependency_is_not_blocked_by_dependency():
    decision = evaluate(_base(is_stacked=True, stack_dependency_resolved=True))
    assert decision.decision != "BLOCKED_BY_DEPENDENCY"
    assert decision.decision == "READY_FOR_MERGE"


def test_stacked_with_independently_validated_effective_diff_is_not_blocked():
    """The rule's escape hatch: even with an unresolved base dependency,
    independent validation of THIS PR's own effective diff is sufficient."""
    decision = evaluate(
        _base(is_stacked=True, stack_dependency_resolved=False, effective_diff_independently_validated=True)
    )
    assert decision.decision != "BLOCKED_BY_DEPENDENCY"


def test_not_stacked_ignores_stack_dependency_fields():
    decision = evaluate(_base(is_stacked=False, stack_dependency_resolved=False))
    assert decision.decision != "BLOCKED_BY_DEPENDENCY"


# ---------------------------------------------------------------------------
# Rule 6: a dashboard route importing a solver is rejected
# ---------------------------------------------------------------------------

def test_dashboard_importing_solver_is_rejected():
    decision = evaluate(_base(dashboard_imports_solver=True))
    assert decision.decision == "REJECTED_UNSAFE"
    assert "DASHBOARD_IMPORTS_SOLVER" in decision.reason_codes


def test_dashboard_not_importing_solver_is_not_rejected_on_that_basis():
    decision = evaluate(_base(dashboard_imports_solver=False))
    assert decision.decision != "REJECTED_UNSAFE"


def test_dashboard_rejection_overrides_scientific_review_and_ci_state():
    decision = evaluate(_base(
        dashboard_imports_solver=True, scientific_review_required=True,
        required_checks={"tests": "failing"},
    ))
    assert decision.decision == "REJECTED_UNSAFE"
    assert decision.reason_codes == ("DASHBOARD_IMPORTS_SOLVER",)


# ---------------------------------------------------------------------------
# Rule 7: missing governance or secret validation blocks merge
# (see also the rule-1-folded tests above; these test the explicit-failure path)
# ---------------------------------------------------------------------------

def test_governance_and_secret_both_missing_still_single_clean_decision():
    decision = evaluate(_base(governance_validated=None, secret_scan_clean=None))
    assert decision.decision == "READY_FOR_REVIEW"
    assert "governance" in decision.reason_codes
    assert "secret_scan" in decision.reason_codes


def test_governance_validated_true_and_secret_clean_true_permits_merge():
    decision = evaluate(_base(governance_validated=True, secret_scan_clean=True))
    assert decision.decision == "READY_FOR_MERGE"


# ---------------------------------------------------------------------------
# Rule 8: duplicate work requires an explicit replacement decision
# ---------------------------------------------------------------------------

def test_duplicate_without_explicit_decision_is_blocked():
    decision = evaluate(_base(duplicate=True, explicit_replacement_decision=False))
    assert decision.decision == "BLOCKED_BY_DUPLICATE_OR_SUPERSEDED_WORK"
    assert "DUPLICATE_WORK_DETECTED" in decision.reason_codes


def test_superseded_without_explicit_decision_is_blocked():
    decision = evaluate(_base(superseded=True, explicit_replacement_decision=False))
    assert decision.decision == "BLOCKED_BY_DUPLICATE_OR_SUPERSEDED_WORK"
    assert "SUPERSEDED_WORK_DETECTED" in decision.reason_codes


def test_duplicate_with_explicit_replacement_decision_is_not_blocked_on_that_basis():
    decision = evaluate(_base(duplicate=True, explicit_replacement_decision=True))
    assert decision.decision != "BLOCKED_BY_DUPLICATE_OR_SUPERSEDED_WORK"
    assert decision.decision == "READY_FOR_MERGE"


def test_both_duplicate_and_superseded_report_both_reason_codes():
    decision = evaluate(_base(duplicate=True, superseded=True, explicit_replacement_decision=False))
    assert set(decision.reason_codes) == {"DUPLICATE_WORK_DETECTED", "SUPERSEDED_WORK_DETECTED"}


# ---------------------------------------------------------------------------
# Rule 9: the policy must be pure and network-free (structural/meta test)
# ---------------------------------------------------------------------------

def test_no_network_or_filesystem_imports_in_merge_gate_module():
    import ast
    from pathlib import Path

    source_path = Path(__file__).resolve().parents[2] / "governance" / "merge_gate.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    forbidden = {"socket", "requests", "urllib", "http", "subprocess", "os"}
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported.isdisjoint(forbidden), f"unexpected imports: {imported & forbidden}"


def test_evaluate_never_raises_on_default_input():
    evaluate(MergeGateInput())  # every field left at its conservative default


# ---------------------------------------------------------------------------
# Rule 10: output must include machine-readable reason codes
# ---------------------------------------------------------------------------

def test_every_decision_has_at_least_one_reason_code():
    inputs = [
        _base(),
        _base(draft=True),
        _base(is_stacked=True, stack_dependency_resolved=False),
        _base(required_checks={"tests": "failing"}),
        _base(infrastructure_blocked=True),
        _base(scientific_review_required=True),
        _base(duplicate=True),
        _base(dashboard_imports_solver=True),
        _base(synthetic_data_claims=True, claims_empirical_pass=True),
        _base(requires_formal_bayes_factor=True, bayes_factor_evidence_kind="proxy"),
        _base(branch_present=False),
        _base(pr_present=False),
        _base(mergeable=False),
    ]
    for gate_input in inputs:
        decision = evaluate(gate_input)
        assert len(decision.reason_codes) >= 1, decision
        assert all(isinstance(code, str) and code for code in decision.reason_codes)


def test_reason_codes_are_stable_strings_not_objects():
    decision = evaluate(_base(required_checks={"tests": "failing"}))
    for code in decision.reason_codes:
        assert isinstance(code, str)


# ---------------------------------------------------------------------------
# Determinism (explicit repeat test, per the mission's required validation)
# ---------------------------------------------------------------------------

def test_evaluate_is_deterministic_across_many_repeats():
    gate_input = _base(is_stacked=True, stack_dependency_resolved=False, scientific_review_required=True)
    first = evaluate(gate_input)
    for _ in range(200):
        assert evaluate(gate_input) == first


def test_evaluate_is_deterministic_for_every_decision_branch():
    scenarios = [
        _base(),
        _base(draft=True),
        _base(required_checks={"tests": "not_run"}),
        _base(required_checks={"tests": "failing"}),
        _base(required_checks={"tests": "billing_blocked"}),
        _base(infrastructure_blocked=True),
        _base(scientific_review_required=True),
        _base(duplicate=True),
        _base(superseded=True),
        _base(dashboard_imports_solver=True),
        _base(synthetic_data_claims=True, claims_empirical_pass=True),
        _base(requires_formal_bayes_factor=True, bayes_factor_evidence_kind="proxy"),
        _base(is_stacked=True, stack_dependency_resolved=False),
        _base(branch_present=False),
        _base(pr_present=False),
        _base(mergeable=False),
    ]
    for scenario in scenarios:
        baseline = evaluate(scenario)
        for _ in range(20):
            assert evaluate(scenario) == baseline


# ---------------------------------------------------------------------------
# Branch / PR existence sanity
# ---------------------------------------------------------------------------

def test_branch_not_present_is_blocked_by_dependency():
    decision = evaluate(_base(branch_present=False))
    assert decision.decision == "BLOCKED_BY_DEPENDENCY"
    assert "BRANCH_NOT_PRESENT" in decision.reason_codes


def test_pr_not_present_is_ready_for_review_not_a_hard_block():
    decision = evaluate(_base(pr_present=False))
    assert decision.decision == "READY_FOR_REVIEW"
    assert "NO_PR_YET" in decision.reason_codes


def test_branch_and_pr_both_absent_reports_branch_absence_first():
    decision = evaluate(_base(branch_present=False, pr_present=False))
    assert decision.decision == "BLOCKED_BY_DEPENDENCY"


# ---------------------------------------------------------------------------
# Draft / mergeability
# ---------------------------------------------------------------------------

def test_draft_pr_is_ready_for_review_not_merge():
    decision = evaluate(_base(draft=True))
    assert decision.decision == "READY_FOR_REVIEW"
    assert "DRAFT" in decision.reason_codes


def test_merge_conflict_is_blocked_by_ci():
    decision = evaluate(_base(mergeable=False))
    assert decision.decision == "BLOCKED_BY_CI"
    assert "MERGE_CONFLICT" in decision.reason_codes


def test_unknown_mergeability_does_not_block_on_that_basis_alone():
    decision = evaluate(_base(mergeable=None))
    assert decision.decision == "READY_FOR_MERGE"


# ---------------------------------------------------------------------------
# Priority ordering between tiers
# ---------------------------------------------------------------------------

def test_duplicate_takes_priority_over_stacked_dependency():
    decision = evaluate(_base(
        duplicate=True, explicit_replacement_decision=False,
        is_stacked=True, stack_dependency_resolved=False,
    ))
    assert decision.decision == "BLOCKED_BY_DUPLICATE_OR_SUPERSEDED_WORK"


def test_stacked_dependency_takes_priority_over_ci_failure():
    decision = evaluate(_base(
        is_stacked=True, stack_dependency_resolved=False,
        required_checks={"tests": "failing"},
    ))
    assert decision.decision == "BLOCKED_BY_DEPENDENCY"


def test_scientific_review_takes_priority_over_plain_ci_failure():
    """Scientific claims require STRICTER gates than ordinary code
    changes -- a scientific-review-required PR is reported as such even
    when a plain check is also failing."""
    decision = evaluate(_base(
        scientific_review_required=True, required_checks={"tests": "failing"},
    ))
    assert decision.decision == "BLOCKED_BY_SCIENTIFIC_REVIEW"


def test_infrastructure_block_takes_priority_over_plain_ci_failure():
    decision = evaluate(_base(required_checks={"a": "infrastructure_blocked", "b": "failing"}))
    assert decision.decision == "BLOCKED_BY_INFRASTRUCTURE"
