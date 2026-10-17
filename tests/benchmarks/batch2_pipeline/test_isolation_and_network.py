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
    report = run_all(ResourceBudgets(max_workers=1), seed=0, size=8, repetitions=1)
    blob = json.dumps(report).lower()
    assert "openneuro.org" not in blob
    assert "amazonaws.com" not in blob
    assert "dandiarchive" not in blob
    assert report["production_probe"]["network_used"] is False
    assert report["production_probe"]["remote_data_accessed"] is False
    assert report["tooling_availability"]["REA"] == "REA_UNAVAILABLE"


def test_cli_rejects_unbounded_workers():
    rc = cli.main(["--max-workers", "4", "--size", "4", "--repetitions", "1"])
    assert rc == 2
