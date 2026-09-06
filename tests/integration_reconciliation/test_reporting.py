from __future__ import annotations

import json

from tools.integration_reconciliation import github_source, reconcile, reporting
from tools.integration_reconciliation.models import WorkOrder


def _tiny_report(git_fixture_repo):
    work_orders = (WorkOrder("wo-a", "feature A", expected_branch="feature-a", reported_pr_number=None),)
    return reconcile.reconcile(git_fixture_repo, work_orders, target_ref="origin/main", github_snapshot=github_source.empty_snapshot())


def test_to_json_is_valid_and_strict(git_fixture_repo):
    report = _tiny_report(git_fixture_repo)
    text = reporting.to_json(report)
    parsed = json.loads(text)  # must not raise
    assert parsed["schema"] == reconcile.REPORT_SCHEMA
    assert parsed["entries"][0]["stages"]["pr_present"]["value"] is False
    assert parsed["entries"][0]["pr"]["number"]["value"] is None
    assert "evidence" in parsed["entries"][0]["pr"]["number"]


def test_to_markdown_contains_the_work_order_row(git_fixture_repo):
    report = _tiny_report(git_fixture_repo)
    text = reporting.to_markdown(report)
    assert "feature A" in text
    assert "| yes | yes | no |" in text  # reported, branch present, PR present


def test_to_markdown_is_a_non_empty_string(git_fixture_repo):
    report = _tiny_report(git_fixture_repo)
    assert isinstance(reporting.to_markdown(report), str)
    assert len(reporting.to_markdown(report)) > 0
