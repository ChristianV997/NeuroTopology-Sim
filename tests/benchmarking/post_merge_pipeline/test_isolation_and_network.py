"""Timeout, isolated CLI, bounded workers, and no-network execution."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from tools.benchmarking.post_merge_pipeline.harness import run_all
from tools.benchmarking.pipeline_efficiency.telemetry import execute_child
from tools.benchmarking.post_merge_pipeline.workloads import TARGETS

REPO_ROOT = Path(__file__).resolve().parents[3]
_SPEC = importlib.util.spec_from_file_location(
    "benchmark_post_merge_pipeline",
    REPO_ROOT / "scripts" / "benchmark_post_merge_pipeline.py",
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
            "45",
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
    report = run_all(seed=0, size=8, repetitions=1)
    assert report["config"]["max_workers"] == 1
    for rec in report["results"]:
        assert (rec.get("telemetry") or {}).get("worker_count") == 1


def test_no_network_execution():
    report = run_all(seed=0, size=8, repetitions=1)
    blob = json.dumps(report).lower()
    assert "amazonaws.com" not in blob
    assert "dandiarchive" not in blob
    assert report["production_probe"]["network_used"] is False
    assert report["production_probe"]["remote_data_accessed"] is False
