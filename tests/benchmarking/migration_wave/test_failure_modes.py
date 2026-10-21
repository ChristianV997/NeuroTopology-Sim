"""Timeout, checksum mismatch, malformed records, budget, partial, duplicate."""
from __future__ import annotations

import sys

from tools.benchmarking.pipeline_efficiency.budgets import ResourceBudgets, compare_budget
from tools.benchmarking.pipeline_efficiency.telemetry import execute_child, measure
from tools.benchmarking.migration_wave.harness import _row_from_measured
from tools.benchmarking.migration_wave.probes import run_probe
from tools.benchmarking.migration_wave.schema import TargetStatus
import tools.benchmarking.pipeline_efficiency.telemetry as telemetry


def test_budget_overrun():
    tiny = ResourceBudgets(memory_bytes=1, disk_bytes=1)
    measured = measure(lambda: run_probe("bounded_transfer_planning", seed=0, size=32), repetitions=1)
    row = _row_from_measured("current_main", "bounded_transfer_planning", measured, tiny)
    assert row["deterministic"]["budget"]["within_budget"] is False
    assert row["status"] == TargetStatus.BUDGET_OVERRUN.value


def test_missing_metric_is_null_not_zero():
    result = compare_budget(
        {"tracemalloc_peak_bytes": 100, "disk_bytes": None, "runtime_best_s": 0.01, "rss_after_bytes": None},
        ResourceBudgets(memory_bytes=1000),
    )
    assert result["checks"]["disk_within_budget"] is None
    assert result["checks"]["rss_within_budget"] is None


def test_measure_reports_null_for_unavailable(monkeypatch):
    monkeypatch.setattr(telemetry, "_PSUTIL", None)
    monkeypatch.setattr(sys, "platform", "darwin")
    out = measure(lambda: {"checksum": "abc", "feature_count": 1}, repetitions=1)
    assert out["rss_after_bytes"] is None
    assert out["disk_bytes"] is None


def test_checksum_mismatch_injected():
    row = _row_from_measured(
        "pr_331",
        "planning_latency",
        {
            "ok": True,
            "checksum": "deadbeef",
            "status": "ok",
            "payload": {"status": "ok", "surface": "chunk_cache", "production_available": True, "correctness": {}},
            "runtime_best_s": 0.01,
            "tracemalloc_peak_bytes": 100,
            "rss_after_bytes": None,
            "disk_bytes": None,
        },
        ResourceBudgets(),
    )
    assert row["deterministic"]["checksum"] == "deadbeef"


def test_malformed_record():
    row = _row_from_measured(
        "current_main",
        "planning_latency",
        {"ok": False, "reason": "malformed_result", "checksum": None},
        ResourceBudgets(),
    )
    assert row["status"] == TargetStatus.MALFORMED_RECORD.value


def test_timeout_child():
    res = execute_child([sys.executable, "-c", "import time; time.sleep(60)"], timeout_s=1.0)
    assert res.timed_out is True
    assert res.elapsed_s < 20


def test_checksum_verification_detects_mismatch():
    row = run_probe("checksum_verification", seed=0, size=32)
    assert row["production_available"] is True
    assert row["correctness"]["mismatch_detected"] is True
    assert row["status"] == "ok"


def test_duplicate_work_flag_present():
    row = run_probe("cache_occupancy", seed=0, size=32)
    assert row["status"] in {"ok", "duplicate_work", "production_unavailable"}
    if row["status"] != "production_unavailable":
        assert "duplicate_work" in row
        assert row["duplicate_work"] in {True, False}
