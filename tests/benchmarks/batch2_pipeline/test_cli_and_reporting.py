"""CLI generate/validate and artifact pack shape."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from tools.benchmarks.batch2_pipeline.reporting import generate
from tools.benchmarks.batch2_pipeline.schema import REQUIRED_OUTPUT_FILES, TARGET_NAMES
from tools.benchmarks.batch2_pipeline.validator import validate_root

REPO_ROOT = Path(__file__).resolve().parents[3]
_SPEC = importlib.util.spec_from_file_location(
    "benchmark_batch2_pipeline_cli2",
    REPO_ROOT / "scripts" / "benchmark_batch2_pipeline.py",
)
cli = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = cli
_SPEC.loader.exec_module(cli)


def test_generate_writes_required_files(tmp_path):
    out = tmp_path / "out"
    report = generate(out, seed=0, size=8, repetitions=1)
    assert report["all_equivalent"] is True
    for rel in REQUIRED_OUTPUT_FILES:
        assert (out / rel).exists(), rel
    validation = validate_root(out)
    assert validation["ok"] is True, validation["violations"]


def test_validate_cli(tmp_path, capsys):
    out = tmp_path / "out"
    generate(out, seed=0, size=8, repetitions=1)
    rc = cli.main(["validate", "--root", str(out)])
    payload = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert payload["ok"] is True


def test_generate_cli(tmp_path, capsys):
    out = tmp_path / "gen"
    rc = cli.main(["generate", "--out", str(out), "--size", "8", "--repetitions", "1"])
    assert rc == 0
    assert "schema=batch2_pipeline/v1" in capsys.readouterr().out
    assert (out / "batch2_pipeline_report.json").exists()


def test_unknown_target_exits_nonzero(capsys):
    """Regression: typos must not look like a successful empty benchmark."""
    rc = cli.main(["--target", "does_not_exist", "--json", "--size", "8", "--repetitions", "1"])
    assert rc != 0
    err = capsys.readouterr().err
    assert "unknown target" in err


def test_isolated_unknown_target_exits_nonzero(capsys):
    rc = cli.main(
        [
            "--isolated",
            "--target",
            "does_not_exist",
            "--json",
            "--per-target-timeout-s",
            "5",
        ]
    )
    out = capsys.readouterr().out
    report = json.loads(out)
    assert rc != 0
    assert report["num_targets"] == 0
    assert "unknown target" in (report.get("error") or "")


def _budget_result(within_budget=True):
    return {
        "within_budget": within_budget,
        "checks": {
            "memory_within_budget": None,
            "disk_within_budget": None,
            "runtime_within_budget": None,
            "rss_within_budget": None,
            "workers_within_budget": True if within_budget is True else None,
        },
        "budgets": {
            "memory_bytes": None,
            "disk_bytes": None,
            "runtime_s": None,
            "rss_bytes": None,
            "max_workers": 1,
        },
    }


def _exit_report(status="ok", *, all_equivalent=True, all_within_budget=True):
    record = {
        "target": "full_recording_reread",
        "status": status,
        "evidence_class": cli.EVIDENCE_CLASS,
        "synthetic": True,
        "telemetry": {
            "candidate": {
                "tracemalloc_peak_bytes": None,
                "disk_bytes": None,
                "worker_count": 1,
            }
        },
        "deterministic": {
            "checksum_match": True,
            "budget": _budget_result(),
        },
    }
    return {
        "schema": cli.SCHEMA_VERSION,
        "schema_version": cli.SCHEMA_VERSION,
        "evidence_class": cli.EVIDENCE_CLASS,
        "synthetic": True,
        "budgets": _budget_result()["budgets"],
        "all_equivalent": all_equivalent,
        "all_within_budget": all_within_budget,
        "config": {"max_workers": 1, "targets": ["full_recording_reread"]},
        "summary": {status: 1},
        "num_targets": 1,
        "results": [record],
    }


def test_cli_exit_code_fails_on_hard_statuses():
    """Isolated timeout/crash/budget overrun must flip the process exit code."""
    assert cli._cli_exit_code(_exit_report()) == 0
    assert cli._cli_exit_code(_exit_report(all_equivalent=False)) == 1
    assert cli._cli_exit_code(_exit_report(all_within_budget=False)) == 1
    assert cli._cli_exit_code(_exit_report("timeout")) == 1
    assert cli._cli_exit_code(_exit_report("child_crash")) == 1
    assert cli._cli_exit_code({"error": "unknown target", "num_targets": 0, "summary": {}}) == 2


def test_cli_exit_code_fails_on_malformed_record():
    report = _exit_report("malformed_record")
    assert cli._cli_exit_code(report) == 1


def test_cli_exit_code_fails_on_non_synthetic_result():
    report = _exit_report()
    report["results"][0]["synthetic"] = False

    assert cli._cli_exit_code(report) != 0


def test_cli_exit_code_fails_on_row_evidence_class_mismatch():
    report = _exit_report()
    report["results"][0]["evidence_class"] = "empirical"

    assert cli._cli_exit_code(report) != 0


def test_cli_exit_code_rejects_budget_pass_with_missing_configured_measurement():
    report = _exit_report()
    row = report["results"][0]
    budget = row["deterministic"]["budget"]
    budget["budgets"]["disk_bytes"] = 1
    budget["checks"]["disk_within_budget"] = True
    row["telemetry"]["candidate"]["disk_bytes"] = None

    assert cli._cli_exit_code(report) != 0


def test_cli_exit_code_rejects_row_budget_relaxation():
    report = _exit_report()
    report["budgets"]["memory_bytes"] = 1
    row = report["results"][0]
    row["telemetry"]["candidate"]["tracemalloc_peak_bytes"] = 50824
    budget = row["deterministic"]["budget"]
    budget["budgets"]["memory_bytes"] = 50825
    budget["checks"]["memory_within_budget"] = True
    budget["within_budget"] = True

    assert cli._cli_exit_code(report) != 0


def test_cli_exit_code_fails_on_unknown_record_status():
    report = _exit_report("unrecognized_status")
    assert cli._cli_exit_code(report) != 0


def test_cli_exit_code_fails_on_unknown_record_target():
    report = _exit_report()
    report["results"][0]["target"] = "not_a_registered_target"
    assert cli._cli_exit_code(report) != 0


def test_cli_exit_code_fails_on_malformed_config():
    report = _exit_report()
    report["config"] = []
    assert cli._cli_exit_code(report) != 0


def test_cli_exit_code_fails_without_required_report_metadata():
    report = _exit_report()
    report.pop("schema")
    report.pop("evidence_class")

    assert cli._cli_exit_code(report) != 0


def test_cli_exit_code_fails_without_target_selection():
    report = _exit_report()
    report["config"].pop("targets")

    assert cli._cli_exit_code(report) != 0


def test_cli_exit_code_fails_when_equivalence_is_unknown():
    report = _exit_report()
    report["all_equivalent"] = None

    assert cli._cli_exit_code(report) != 0


def test_isolated_report_does_not_claim_equivalence_with_unknown_measurements(
    monkeypatch, capsys
):
    records = {
        "full_recording_reread": {
            "target": "full_recording_reread",
            "status": "ok",
            "evidence_class": cli.EVIDENCE_CLASS,
            "synthetic": True,
            "telemetry": {
                "candidate": {
                    "tracemalloc_peak_bytes": None,
                    "disk_bytes": None,
                    "worker_count": 1,
                }
            },
            "deterministic": {
                "checksum_match": True,
                "budget": _budget_result(),
            },
        },
        "window_cache_hits": {
            "target": "window_cache_hits",
            "status": "malformed_record",
            "evidence_class": cli.EVIDENCE_CLASS,
            "synthetic": True,
            "deterministic": {
                "checksum_match": None,
                "budget": _budget_result(None),
            },
        },
    }

    class Child:
        timed_out = False
        exit_code = 0
        stderr = ""
        elapsed_s = 0.0

        def __init__(self, stdout):
            self.stdout = stdout

    def fake_execute_child(argv, *, timeout_s):
        name = argv[4]
        return Child(json.dumps(records[name]))

    monkeypatch.setattr(
        cli,
        "TARGETS",
        {"full_recording_reread": object(), "window_cache_hits": object()},
    )
    monkeypatch.setattr(cli, "execute_child", fake_execute_child)

    rc = cli.main(["--isolated", "--json"])
    report = json.loads(capsys.readouterr().out)

    assert rc != 0
    assert report["all_equivalent"] is None
    assert report["all_within_budget"] is None


def test_generate_cli_fails_when_all_records_are_malformed(tmp_path, monkeypatch):
    malformed_report = {
        "schema": "batch2_pipeline/v1",
        "evidence_class": cli.EVIDENCE_CLASS,
        "synthetic": True,
        "budgets": _budget_result()["budgets"],
        "all_equivalent": None,
        "all_within_budget": None,
        "config": {"max_workers": 1, "targets": sorted(TARGET_NAMES)},
        "summary": {"malformed_record": 7},
        "num_targets": 7,
        "results": [
            {
                "target": target,
                "status": "malformed_record",
                "evidence_class": cli.EVIDENCE_CLASS,
                "synthetic": True,
                "deterministic": {
                    "checksum_match": None,
                "budget": _budget_result(None),
                },
            }
            for target in sorted(TARGET_NAMES)
        ],
    }
    monkeypatch.setattr(cli, "generate", lambda *args, **kwargs: malformed_report)

    rc = cli.main(["generate", "--out", str(tmp_path / "out")])

    assert rc == 1


def test_isolated_honors_memory_budget_passthrough(capsys):
    """Regression: isolated children must receive parent authoritative budgets."""
    rc = cli.main(
        [
            "--isolated",
            "--target",
            "checkpoint_fsync_overhead",
            "--json",
            "--size",
            "8",
            "--repetitions",
            "1",
            "--memory-budget-mb",
            "0.000001",
            "--per-target-timeout-s",
            "60",
        ]
    )
    report = json.loads(capsys.readouterr().out)
    assert rc != 0
    assert report["all_within_budget"] is False
    assert report["summary"].get("budget_overrun", 0) >= 1
    child = report["results"][0]
    assert child["status"] == "budget_overrun"
    assert child["deterministic"]["budget"]["checks"]["memory_within_budget"] is False


def test_isolated_advisory_runtime_rss_do_not_fail_exit(capsys):
    """Advisory timing/RSS must not flip isolated CLI exit by themselves."""
    rc = cli.main(
        [
            "--isolated",
            "--target",
            "checkpoint_fsync_overhead",
            "--json",
            "--size",
            "8",
            "--repetitions",
            "1",
            "--runtime-budget-s",
            "1e-15",
            "--rss-budget-mb",
            "0.000001",
            "--per-target-timeout-s",
            "60",
        ]
    )
    report = json.loads(capsys.readouterr().out)
    assert rc == 0
    assert report["all_within_budget"] is True
    child = report["results"][0]
    assert child["status"] == "ok"
    checks = child["deterministic"]["budget"]["checks"]
    assert checks["runtime_within_budget"] is False
    assert checks["rss_within_budget"] in (False, None)
