"""Timeout, isolated CLI, and no-network execution."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from tools.benchmarking.data_migration_effectiveness.harness import run_all
from tools.benchmarking.data_migration_effectiveness.telemetry import execute_child
from tools.benchmarking.data_migration_effectiveness.workloads import TARGETS, production_available

REPO_ROOT = Path(__file__).resolve().parents[3]
_SPEC = importlib.util.spec_from_file_location(
    "benchmark_data_migration_effectiveness",
    REPO_ROOT / "scripts" / "benchmark_data_migration_effectiveness.py",
)
cli = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = cli
_SPEC.loader.exec_module(cli)


def test_child_timeout():
    res = execute_child([sys.executable, "-c", "import time; time.sleep(60)"], timeout_s=1.0)
    assert res.timed_out is True
    assert res.exit_code != 0
    assert res.elapsed_s < 20


def test_isolated_cli(tmp_path, capsys):
    rc = cli.main(
        [
            "--isolated",
            "--size",
            "32",
            "--repetitions",
            "1",
            "--per-target-timeout-s",
            "30",
            "--json-stdout",
            "--output",
            str(tmp_path / "iso"),
        ]
    )
    out = capsys.readouterr().out
    report = json.loads(out)
    assert report["evidence_class"] == "performance_only"
    assert report["network_accessed"] is False
    assert report["scientific_improvement_claimed"] is False
    assert report["isolated"] is True
    assert len(report["results"]) == len(TARGETS)
    assert rc in (0, 1)


def test_no_network_execution():
    report = run_all(seed=0, size=32, repetitions=1)
    blob = json.dumps(report).lower()
    assert "openneuro.org" not in blob
    assert "amazonaws.com" not in blob
    assert "dandiarchive" not in blob
    assert report["network_accessed"] is False
    assert report["full_dataset_download"] is False
    flags = production_available()
    assert flags["chunk_cache"] is True
    assert flags["policy_enforcement"] is True
    assert flags["streaming_bounded"] is True


def test_worker_count_is_one():
    report = run_all(seed=0, size=32, repetitions=1)
    assert report["config"]["max_workers"] == 1
    for rec in report["results"]:
        tel = rec.get("telemetry") or {}
        assert tel.get("worker_count") == 1
