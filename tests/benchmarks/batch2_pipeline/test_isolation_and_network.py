"""Timeout, isolated CLI, bounded workers, and no-network execution."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from tools.benchmarks.batch2_pipeline.budgets import ResourceBudgets
from tools.benchmarks.batch2_pipeline.harness import run_all
from tools.benchmarks.batch2_pipeline.telemetry import execute_child
from tools.benchmarks.batch2_pipeline.workloads import TARGETS

REPO_ROOT = Path(__file__).resolve().parents[3]
_SPEC = importlib.util.spec_from_file_location(
    "benchmark_batch2_pipeline",
    REPO_ROOT / "scripts" / "benchmark_batch2_pipeline.py",
)
cli = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = cli
_SPEC.loader.exec_module(cli)


def test_child_timeout():
    res = execute_child([sys.executable, "-c", "import time; time.sleep(60)"], timeout_s=1.0)
    assert res.timed_out is True
    assert res.exit_code != 0
    assert res.elapsed_s < 20


def test_isolated_cli(capsys):
    rc = cli.main(
        [
            "--isolated",
            "--size",
            "8",
            "--repetitions",
            "1",
            "--per-target-timeout-s",
            "30",
            "--json",
        ]
    )
    out = capsys.readouterr().out
    report = json.loads(out)
    assert report["mode"] == "isolated"
    assert report["config"]["max_workers"] == 1
    assert report["config"]["targets"] == sorted(TARGETS)
    assert report["num_targets"] == len(TARGETS)
    assert report["evidence_class"] == "performance_only"
    assert rc in (0, 1)


def test_bounded_worker_count_in_report():
    report = run_all(ResourceBudgets(max_workers=1), seed=0, size=8, repetitions=1)
    assert report["config"]["max_workers"] == 1
    for rec in report["results"]:
        assert (rec.get("telemetry") or {}).get("worker_count") == 1


def test_worker_bound_enforcement_candidate_is_one():
    from tools.benchmarks.batch2_pipeline.harness import run_target

    rec = run_target(
        TARGETS["worker_bound_enforcement"],
        ResourceBudgets(max_workers=1),
        seed=0,
        size=8,
        repetitions=1,
    )
    assert rec["telemetry"]["candidate"]["worker_count"] == 1
    assert rec["telemetry"]["baseline"]["counters"]["worker_count"] > 1
    assert rec["status"] == "ok"


def test_no_network_execution():
    from tools.benchmarks.batch2_pipeline.validator import (
        _hostname_is_remote,
        _string_references_remote_host,
        validate_report,
    )

    report = run_all(ResourceBudgets(max_workers=1), seed=0, size=8, repetitions=1)
    assert report["production_probe"]["network_used"] is False
    assert report["production_probe"]["remote_data_accessed"] is False
    assert report["tooling_availability"]["REA"] == "REA_UNAVAILABLE"
    assert validate_report(report)["ok"] is True

    # Hostname parsing (CodeQL: incomplete URL substring sanitization).
    assert _hostname_is_remote("openneuro.org")
    assert _hostname_is_remote("s3.amazonaws.com")
    assert _hostname_is_remote("api.dandiarchive.org")
    assert not _hostname_is_remote("example.com")
    assert _string_references_remote_host("https://openneuro.org/datasets/ds000001")
    assert _string_references_remote_host("https://bucket.s3.amazonaws.com/x")
    # Protocol-relative URLs must parse netloc (not silently skip).
    assert _string_references_remote_host("//openneuro.org/datasets/ds000001")
    assert _string_references_remote_host("//api.dandiarchive.org/v1")
    # Substring lookalikes must not trip the denylist.
    assert not _string_references_remote_host("https://evilopenneuro.org.attacker.example/x")
    assert not _string_references_remote_host("//evilopenneuro.org.attacker.example/x")
    assert not _string_references_remote_host("notes mentioning openneuro.org in prose")
    assert not _string_references_remote_host(
        "https://example.org/docs/openneuro.org/datasets"
    )
    assert _string_references_remote_host(
        "Dataset source: https://openneuro.org/datasets/ds000001."
    )
    assert _string_references_remote_host(
        "Dataset source: openneuro.org/datasets/ds000001"
    )
    assert _string_references_remote_host(
        "Dataset source: openneuro.org:8443/datasets/ds000001"
    )

    poisoned = dict(report)
    poisoned["notes"] = ["https://openneuro.org/datasets/ds000001"]
    assert "remote_data_reference" in validate_report(poisoned)["violations"]

    poisoned_protocol_relative = dict(report)
    poisoned_protocol_relative["notes"] = ["//openneuro.org/datasets/ds000001"]
    assert "remote_data_reference" in validate_report(poisoned_protocol_relative)["violations"]

    poisoned_prose = dict(report)
    poisoned_prose["notes"] = [
        "Dataset source: (https://openneuro.org/datasets/ds000001)."
    ]
    assert "remote_data_reference" in validate_report(poisoned_prose)["violations"]

    poisoned_schemeless_url = dict(report)
    poisoned_schemeless_url["notes"] = [
        "Dataset source: openneuro.org/datasets/ds000001"
    ]
    assert "remote_data_reference" in validate_report(poisoned_schemeless_url)["violations"]


def test_validator_rejects_non_synthetic_result_row():
    from tools.benchmarks.batch2_pipeline.validator import validate_report

    report = run_all(
        ResourceBudgets(max_workers=1),
        seed=0,
        size=8,
        repetitions=1,
        targets=["full_recording_reread"],
    )
    report["results"][0]["synthetic"] = False

    validation = validate_report(report)

    assert validation["ok"] is False
    assert "row_synthetic_flag_mismatch:full_recording_reread" in validation["violations"]


def test_validator_rejects_budget_pass_with_missing_configured_measurement():
    from tools.benchmarks.batch2_pipeline.validator import validate_report

    report = run_all(
        ResourceBudgets(max_workers=1),
        seed=0,
        size=8,
        repetitions=1,
        targets=["full_recording_reread"],
    )
    budget = report["results"][0]["deterministic"]["budget"]
    budget["budgets"]["disk_bytes"] = 1
    budget["within_budget"] = True
    report["all_within_budget"] = True

    validation = validate_report(report)

    assert validation["ok"] is False
    assert "budget_checks_mismatch:full_recording_reread" in validation["violations"]


def test_empty_report_is_not_valid():
    from tools.benchmarks.batch2_pipeline.validator import validate_report

    report = run_all(ResourceBudgets(max_workers=1), seed=0, size=8, repetitions=1)
    empty_report = {
        **report,
        "config": {**report["config"], "targets": []},
        "num_targets": 0,
        "summary": {},
        "all_equivalent": None,
        "all_within_budget": None,
        "bottleneck_ranking": [],
        "optimization_candidates": [],
        "results": [],
    }

    validation = validate_report(empty_report)

    assert validation["ok"] is False
    assert "empty_results" in validation["violations"]


def test_validator_rejects_unknown_config_target():
    from tools.benchmarks.batch2_pipeline.validator import validate_report

    report = run_all(ResourceBudgets(max_workers=1), seed=0, size=8, repetitions=1)
    report["config"]["targets"] = ["not_a_registered_target"]

    validation = validate_report(report)

    assert validation["ok"] is False
    assert "unknown_target" in validation["violations"]


def test_validator_rejects_non_object_config():
    from tools.benchmarks.batch2_pipeline.validator import validate_report

    report = run_all(ResourceBudgets(max_workers=1), seed=0, size=8, repetitions=1)
    report["config"] = []

    validation = validate_report(report)

    assert validation["ok"] is False
    assert "invalid_config" in validation["violations"]


def test_validator_rejects_missing_target_selection():
    from tools.benchmarks.batch2_pipeline.validator import validate_report

    report = run_all(ResourceBudgets(max_workers=1), seed=0, size=8, repetitions=1)
    report["config"].pop("targets")

    validation = validate_report(report)

    assert validation["ok"] is False
    assert "missing_target_selection" in validation["violations"]


def test_validator_rejects_malformed_record_status():
    from tools.benchmarks.batch2_pipeline.validator import validate_report

    report = run_all(ResourceBudgets(max_workers=1), seed=0, size=8, repetitions=1)
    report["results"][0]["status"] = "malformed_record"
    report["summary"]["ok"] -= 1
    report["summary"]["malformed_record"] = 1
    report["all_equivalent"] = None

    validation = validate_report(report)

    assert validation["ok"] is False
    assert any(item.startswith("malformed_record:") for item in validation["violations"])


def test_validator_rejects_unknown_record_status():
    from tools.benchmarks.batch2_pipeline.validator import validate_report

    report = run_all(ResourceBudgets(max_workers=1), seed=0, size=8, repetitions=1)
    report["results"][0]["status"] = "unrecognized_status"
    report["summary"]["ok"] -= 1
    report["summary"]["unrecognized_status"] = 1

    validation = validate_report(report)

    assert validation["ok"] is False
    assert any("unknown_status" in item for item in validation["violations"])


def test_validator_rejects_success_status_without_matching_checksum():
    from tools.benchmarks.batch2_pipeline.validator import validate_report

    report = run_all(ResourceBudgets(max_workers=1), seed=0, size=8, repetitions=1)
    report["results"][0]["deterministic"]["checksum_match"] = None

    validation = validate_report(report)

    assert validation["ok"] is False
    assert any(item.startswith("success_without_checksum:") for item in validation["violations"])


def test_validator_rejects_non_boolean_equivalence_verdict():
    from tools.benchmarks.batch2_pipeline.validator import validate_report

    report = run_all(ResourceBudgets(max_workers=1), seed=0, size=8, repetitions=1)
    report["all_equivalent"] = "yes"

    validation = validate_report(report)

    assert validation["ok"] is False
    assert "invalid_equivalence_verdict" in validation["violations"]


def test_validator_rejects_non_boolean_budget_measurement():
    from tools.benchmarks.batch2_pipeline.validator import validate_report

    report = run_all(ResourceBudgets(max_workers=1), seed=0, size=8, repetitions=1)
    report["results"][0]["deterministic"]["budget"]["within_budget"] = "yes"
    report["all_within_budget"] = None

    validation = validate_report(report)

    assert validation["ok"] is False
    assert any(item.startswith("invalid_budget_verdict:") for item in validation["violations"])


def test_cli_rejects_unbounded_workers():
    rc = cli.main(["--max-workers", "4", "--size", "4", "--repetitions", "1"])
    assert rc == 2
