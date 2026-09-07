from tools.release_manifest import ci_classifier


def test_passing_check():
    name, ev = ci_classifier.classify_check("build", {"status": "completed", "conclusion": "success"})
    assert ev.value == "passing"


def test_bare_failure_without_signature_is_failing_never_downgraded():
    name, ev = ci_classifier.classify_check("build", {"status": "completed", "conclusion": "failure"})
    assert ev.value == "failing"


def test_failure_with_signature_is_infrastructure_blocked():
    name, ev = ci_classifier.classify_check(
        "build",
        {"status": "completed", "conclusion": "failure", "failure_signature": "billing/quota blocked before any step ran"},
    )
    assert ev.value == "infrastructure_blocked"


def test_pending_check():
    name, ev = ci_classifier.classify_check("build", {"status": "in_progress"})
    assert ev.value == "pending"


def test_skipped_check():
    name, ev = ci_classifier.classify_check("build", {"status": "completed", "conclusion": "skipped"})
    assert ev.value == "skipped"


def test_no_data_is_unavailable():
    name, ev = ci_classifier.classify_check("build", {})
    assert ev.value == "unavailable"


def test_unrecognized_conclusion_is_unavailable():
    name, ev = ci_classifier.classify_check("build", {"status": "completed", "conclusion": "weird"})
    assert ev.value == "unavailable"


def test_worst_check_state_prioritizes_failing_over_infrastructure_blocked():
    classified = ci_classifier.classify_all_checks(
        {
            "a": {"status": "completed", "conclusion": "failure", "failure_signature": "quota"},
            "b": {"status": "completed", "conclusion": "failure"},
        }
    )
    assert ci_classifier.worst_check_state(classified) == "failing"


def test_worst_check_state_empty_is_unavailable():
    assert ci_classifier.worst_check_state({}) == "unavailable"
