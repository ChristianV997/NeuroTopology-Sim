from __future__ import annotations

from tools.integration_state import ci_classifier


def test_no_data_is_unavailable():
    result = ci_classifier.classify_check("x")
    assert result.classification == "unavailable"


def test_passing():
    result = ci_classifier.classify_check("x", status="completed", conclusion="success")
    assert result.classification == "passing"


def test_pending_when_not_completed():
    result = ci_classifier.classify_check("x", status="queued")
    assert result.classification == "pending"


def test_skipped_conclusion():
    result = ci_classifier.classify_check("x", status="completed", conclusion="skipped")
    assert result.classification == "skipped"


def test_plain_failure_is_failing_not_infrastructure_blocked():
    result = ci_classifier.classify_check("x", status="completed", conclusion="failure")
    assert result.classification == "failing"


def test_disk_space_signature_is_infrastructure_blocked():
    result = ci_classifier.classify_check(
        "x", status="completed", conclusion="failure", failure_signature="No space left on device",
    )
    assert result.classification == "infrastructure_blocked"


def test_billing_signature_is_infrastructure_blocked():
    result = ci_classifier.classify_check(
        "x", status="completed", conclusion="failure",
        failure_signature="This run was not started because recent account payments have failed.",
    )
    assert result.classification == "infrastructure_blocked"


def test_action_required_conclusion_is_infrastructure_blocked():
    result = ci_classifier.classify_check("x", status="completed", conclusion="action_required")
    assert result.classification == "infrastructure_blocked"


def test_unrecognized_conclusion_is_unavailable_not_fabricated():
    result = ci_classifier.classify_check("x", status="completed", conclusion="something_new")
    assert result.classification == "unavailable"


def test_classify_all_and_as_state_map():
    checks = {
        "a": {"status": "completed", "conclusion": "success"},
        "b": {"status": "completed", "conclusion": "failure"},
        "c": {},
    }
    state_map = ci_classifier.as_state_map(ci_classifier.classify_all(checks))
    assert state_map == {"a": "passing", "b": "failing", "c": "unavailable"}
