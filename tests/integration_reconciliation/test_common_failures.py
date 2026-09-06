from __future__ import annotations

from tools.integration_reconciliation import common_failures


def test_no_findings_when_too_few_work_orders_report_a_check():
    checks = {"a": {"x": "failure"}, "b": {"x": "failure"}}
    assert common_failures.detect_common_check_failures(checks, min_work_orders=3) == []


def test_finding_when_check_fails_everywhere():
    checks = {
        "a": {"x": "failure"}, "b": {"x": "failure"}, "c": {"x": "failure"},
    }
    findings = common_failures.detect_common_check_failures(checks, min_work_orders=3)
    assert len(findings) == 1
    assert findings[0]["check_name"] == "x"
    assert findings[0]["fraction"] == 1.0
    assert set(findings[0]["failing_in"]) == {"a", "b", "c"}


def test_no_finding_when_check_mostly_passes():
    checks = {
        "a": {"x": "success"}, "b": {"x": "success"}, "c": {"x": "failure"},
    }
    assert common_failures.detect_common_check_failures(checks, min_work_orders=3, min_fraction=0.6) == []


def test_none_checks_are_skipped_entirely():
    checks = {"a": None, "b": {"x": "failure"}, "c": {"x": "failure"}, "d": {"x": "failure"}}
    findings = common_failures.detect_common_check_failures(checks, min_work_orders=3)
    assert len(findings) == 1
    assert findings[0]["total_reporting"] == 3


def test_different_checks_are_independent():
    checks = {
        "a": {"x": "failure", "y": "success"},
        "b": {"x": "failure", "y": "success"},
        "c": {"x": "failure", "y": "success"},
    }
    findings = common_failures.detect_common_check_failures(checks, min_work_orders=3)
    names = {f["check_name"] for f in findings}
    assert names == {"x"}
