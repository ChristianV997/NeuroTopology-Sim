from __future__ import annotations

from tools.integration_reconciliation import ci_interpretation


def test_no_status_or_conclusion_is_not_run():
    result = ci_interpretation.classify_check("x")
    assert result.classification == "not_run"


def test_pending_when_status_not_completed():
    result = ci_interpretation.classify_check("x", status="in_progress", conclusion=None)
    assert result.classification == "pending"


def test_passing_on_success_conclusion():
    result = ci_interpretation.classify_check("x", status="completed", conclusion="success")
    assert result.classification == "passing"


def test_skipped_and_neutral_are_passing():
    assert ci_interpretation.classify_check("x", status="completed", conclusion="skipped").classification == "passing"
    assert ci_interpretation.classify_check("x", status="completed", conclusion="neutral").classification == "passing"


def test_plain_failure_is_failing_not_infrastructure_blocked():
    """A bare 'failure' conclusion with no failure_signature must be
    reported as an actual test failure -- never silently downgraded to
    infrastructure_blocked without evidence."""
    result = ci_interpretation.classify_check("x", status="completed", conclusion="failure")
    assert result.classification == "failing"


def test_disk_space_signature_is_infrastructure_blocked():
    result = ci_interpretation.classify_check(
        "core-tests", status="completed", conclusion="failure",
        failure_signature="ERROR: Could not install packages due to an OSError: [Errno 28] No space left on device",
    )
    assert result.classification == "infrastructure_blocked"


def test_action_required_conclusion_is_billing_blocked():
    result = ci_interpretation.classify_check("x", status="completed", conclusion="action_required")
    assert result.classification == "billing_blocked"


def test_billing_signature_text_is_billing_blocked():
    result = ci_interpretation.classify_check(
        "x", status="completed", conclusion="failure",
        failure_signature="This run was not started because recent account payments have failed.",
    )
    assert result.classification == "billing_blocked"


def test_unrecognized_conclusion_is_unknown_not_fabricated():
    result = ci_interpretation.classify_check("x", status="completed", conclusion="something_new")
    assert result.classification == "unknown"


def test_classify_all_over_multiple_checks():
    checks = {
        "a": {"status": "completed", "conclusion": "success"},
        "b": {"status": "completed", "conclusion": "failure"},
        "c": {"status": "in_progress"},
    }
    results = ci_interpretation.classify_all(checks)
    assert results["a"].classification == "passing"
    assert results["b"].classification == "failing"
    assert results["c"].classification == "pending"


def test_summarize_groups_by_classification():
    checks = {
        "a": {"status": "completed", "conclusion": "success"},
        "b": {"status": "completed", "conclusion": "success"},
        "c": {"status": "completed", "conclusion": "failure"},
    }
    summary = ci_interpretation.summarize(ci_interpretation.classify_all(checks))
    assert summary["passing"] == ["a", "b"]
    assert summary["failing"] == ["c"]
    assert "pending" not in summary
