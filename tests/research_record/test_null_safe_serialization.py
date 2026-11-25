"""JSON requirement: null for unavailable values, and the whole record
must always serialize safely (no NaN/Infinity, no non-JSON-native types)."""
from __future__ import annotations

import json

from tools.research_record.compiler import compile_record

NOW = "2026-01-01T00:00:00+00:00"


def test_missing_optional_fields_are_null_not_absent_or_fabricated(manifest_factory):
    manifest = manifest_factory(
        {
            "reconciliation": {"pull_requests": [{"pr_number": 1, "branch": None, "base_branch": None, "merge_status": "open"}]},
            "dataset_provenance": {"datasets": [{"dataset_id": "ds1"}]},
        }
    )
    record = compile_record(manifest, now=NOW)

    pr = record["pr_state"]["pull_requests"][0]
    assert pr["branch"] is None
    assert pr["mergeable"] is None
    assert pr["superseded_by_pr"] is None

    dataset = record["provenance"]["datasets"][0]
    assert dataset["source"] is None
    assert dataset["n_subjects"] is None
    assert dataset["checksum_source"] == "unknown"  # never fabricated as "independent"


def test_full_record_is_json_serializable_with_no_nan_or_infinity(manifest_factory):
    manifest = manifest_factory(
        {
            "performance_benchmark": {"benchmarks": [{"name": "x", "value": None, "baseline_value": None, "regression_pct": None}]},
            "falsification": {"results": [{"hypothesis_id": "HYP-1", "claim_class": "unknown", "data_mode": "unknown", "metric_type": None, "metric_value": None, "verdict": "unknown"}]},
        }
    )
    record = compile_record(manifest, now=NOW)

    text = json.dumps(record, indent=2, sort_keys=True, allow_nan=False)
    assert "NaN" not in text
    assert "Infinity" not in text

    round_tripped = json.loads(text)
    assert round_tripped == record
