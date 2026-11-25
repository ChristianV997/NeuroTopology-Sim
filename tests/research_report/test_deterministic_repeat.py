from __future__ import annotations

import json

from tools.research_report.compiler import compile_report
from tools.research_report.render_csv import render_csv_tables
from tools.research_report.render_markdown import render_markdown

NOW = "2026-01-01T00:00:00+00:00"


def _rich_manifest(manifest_factory):
    return manifest_factory(
        {
            "reconciliation": {
                "pull_requests": [
                    {"pr_number": 2, "branch": "b", "base_branch": "main", "state": "open", "mergeable": True, "ci_status": "passed", "changed_files": ["b.py", "a.py"]},
                    {"pr_number": 1, "branch": "a", "base_branch": "main", "state": "open", "mergeable": True, "ci_status": "passed", "changed_files": ["a.py"]},
                ]
            },
            "falsification": {
                "results": [
                    {"hypothesis_id": "HYP-2", "data_mode": "synthetic", "metric_type": "proxy_K", "metric_value": 1.1, "unit": None, "verdict": "PASS"},
                    {"hypothesis_id": "HYP-1", "data_mode": "empirical", "metric_type": "bayes_factor", "metric_value": 2.2, "unit": None, "verdict": "PASS"},
                ]
            },
        }
    )


def test_repeated_compile_is_byte_identical(manifest_factory):
    manifest = _rich_manifest(manifest_factory)

    report1 = compile_report(manifest, now=NOW, repo="r", base_ref="main", base_commit="abc")
    report2 = compile_report(manifest, now=NOW, repo="r", base_ref="main", base_commit="abc")

    json1 = json.dumps(report1, indent=2, sort_keys=True, allow_nan=False)
    json2 = json.dumps(report2, indent=2, sort_keys=True, allow_nan=False)
    assert json1 == json2

    assert render_markdown(report1) == render_markdown(report2)
    assert render_csv_tables(report1) == render_csv_tables(report2)

    # Input ordering must not leak into output ordering.
    assert report1["pull_requests"]["pull_requests"][0]["pr_number"] == 1
    assert report1["falsification_status"]["results"][0]["hypothesis_id"] == "HYP-1"


def test_omitted_now_only_changes_generated_at(manifest_factory):
    manifest = _rich_manifest(manifest_factory)

    report1 = compile_report(manifest)
    report2 = compile_report(manifest)

    report1_no_ts = {k: v for k, v in report1.items() if k != "generated_at"}
    report2_no_ts = {k: v for k, v in report2.items() if k != "generated_at"}
    assert report1_no_ts == report2_no_ts
