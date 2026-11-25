"""No-network execution, bounded workers, isolated child timeout."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from tools.benchmarking.pipeline_efficiency.telemetry import execute_child
from tools.benchmarking.migration_wave.harness import run_all
from tools.benchmarking.migration_wave.probes import run_probe

REPO_ROOT = Path(__file__).resolve().parents[3]


def test_no_network_in_probe_payload():
    row = run_probe("planning_latency", seed=0, size=32)
    blob = json.dumps(row).lower()
    assert "amazonaws.com" not in blob
    assert "dandiarchive" not in blob
    assert row.get("network_used") is not True
    assert row.get("remote_data_accessed") is not True


def test_run_all_declares_no_network():
    report = run_all(seed=0, size=32, repetitions=1, variants=["current_main"])
    assert report["network_used"] is False
    assert report["remote_data_accessed"] is False
    assert report["config"]["max_workers"] == 1
    blob = json.dumps(report).lower()
    assert "amazonaws.com" not in blob


def test_child_timeout():
    res = execute_child([sys.executable, "-c", "import time; time.sleep(60)"], timeout_s=1.0)
    assert res.timed_out is True


def test_isolated_child_current_main():
    script = REPO_ROOT / "scripts" / "benchmark_migration_wave.py"
    res = execute_child(
        [
            sys.executable,
            str(script),
            "child",
            "--variant-root",
            str(REPO_ROOT),
            "--target",
            "planning_latency",
            "--seed",
            "0",
            "--size",
            "32",
            "--repetitions",
            "1",
        ],
        timeout_s=45.0,
    )
    assert res.timed_out is False
    assert res.exit_code == 0, res.stderr
    payload = json.loads(res.stdout.strip().splitlines()[-1])
    assert payload.get("ok") is True
    assert payload.get("checksum")
