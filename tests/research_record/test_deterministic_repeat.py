from __future__ import annotations

import json

from tools.research_record.compiler import compile_record
from tools.research_record.render_csv import render_csv_tables
from tools.research_record.render_markdown import render_markdown

NOW = "2026-01-01T00:00:00+00:00"


def _rich_manifest(manifest_factory):
    return manifest_factory(
        {
            "reconciliation": {
                "pull_requests": [
                    {"pr_number": 2, "branch": "b", "base_branch": "main", "merge_status": "open", "mergeable": True, "ci_status": "passed", "changed_files": ["b.py", "a.py"]},
                    {"pr_number": 1, "branch": "a", "base_branch": "main", "merge_status": "open", "mergeable": True, "ci_status": "passed", "changed_files": ["a.py"]},
                ]
            },
            "falsification": {
                "results": [
                    {"hypothesis_id": "HYP-2", "claim_class": "proxy", "data_mode": "synthetic", "metric_type": "proxy_K", "metric_value": 1.1, "verdict": "INCONCLUSIVE"},
                    {"hypothesis_id": "HYP-1", "claim_class": "empirical", "data_mode": "empirical", "metric_type": "bayes_factor", "metric_value": 2.2, "verdict": "PASS"},
                ]
            },
        }
    )


def test_repeated_compile_is_byte_identical(manifest_factory):
    manifest = _rich_manifest(manifest_factory)

    record1 = compile_record(manifest, now=NOW, repo="r", origin_main_commit="abc", integration_ref="main", integration_commit="abc")
    record2 = compile_record(manifest, now=NOW, repo="r", origin_main_commit="abc", integration_ref="main", integration_commit="abc")

    json1 = json.dumps(record1, indent=2, sort_keys=True, allow_nan=False)
    json2 = json.dumps(record2, indent=2, sort_keys=True, allow_nan=False)
    assert json1 == json2

    assert render_markdown(record1) == render_markdown(record2)
    assert render_csv_tables(record1) == render_csv_tables(record2)

    assert record1["pr_state"]["pull_requests"][0]["pr_number"] == 1
    assert record1["falsification_semantics"]["results"][0]["hypothesis_id"] == "HYP-1"


def test_omitted_now_only_changes_generated_at(manifest_factory):
    manifest = _rich_manifest(manifest_factory)

    record1 = compile_record(manifest)
    record2 = compile_record(manifest)

    record1_no_ts = {k: v for k, v in record1.items() if k != "generated_at"}
    record2_no_ts = {k: v for k, v in record2.items() if k != "generated_at"}
    assert record1_no_ts == record2_no_ts
