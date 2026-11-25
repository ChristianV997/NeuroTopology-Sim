"""Budget overrun, checksum mismatch, malformed records, and missing metrics."""
from __future__ import annotations

import sys

from tools.benchmarking.pipeline_efficiency.budgets import ResourceBudgets, compare_budget
from tools.benchmarking.pipeline_efficiency.harness import run_target
from tools.benchmarking.pipeline_efficiency.telemetry import measure
from tools.benchmarking.pipeline_efficiency.workloads import TARGETS, TargetSpec
import tools.benchmarking.pipeline_efficiency.telemetry as telemetry


def test_budget_pass():
    huge = ResourceBudgets(memory_bytes=10**12, disk_bytes=10**12)
    rec = run_target(TARGETS["manifest_planning"], huge, seed=0, size=8, repetitions=1)
    assert rec["deterministic"]["budget"]["within_budget"] is True
    assert rec["status"] == "ok"


def test_budget_overrun():
    tiny = ResourceBudgets(memory_bytes=1, disk_bytes=1)
    rec = run_target(TARGETS["manifest_planning"], tiny, seed=0, size=12, repetitions=1)
    assert rec["deterministic"]["budget"]["within_budget"] is False
    assert rec["status"] == "budget_overrun"
    assert any("budget" in item for item in rec["recommendations"])


def test_missing_metric_is_null_not_zero():
    result = compare_budget(
        {
            "tracemalloc_peak_bytes": 100,
            "disk_bytes": None,
            "runtime_best_s": 0.01,
            "rss_after_bytes": None,
        },
        ResourceBudgets(memory_bytes=1000),
    )
    assert result["checks"]["disk_within_budget"] is None
    assert result["checks"]["rss_within_budget"] is None
    result2 = compare_budget(
        {"tracemalloc_peak_bytes": 100, "disk_bytes": None},
        ResourceBudgets(disk_bytes=1000),
    )
    assert result2["checks"]["disk_within_budget"] is None
    assert result2["within_budget"] is None


def test_measure_reports_null_for_unavailable(monkeypatch):
    monkeypatch.setattr(telemetry, "_PSUTIL", None)
    monkeypatch.setattr(sys, "platform", "darwin")
    out = measure(lambda: {"checksum": "abc", "feature_count": 1}, repetitions=1)
    assert out["rss_after_bytes"] is None
    assert out["disk_bytes"] is None


def test_checksum_mismatch():
    base = TARGETS["checkpoint_recovery_planning"]
    broken = TargetSpec(
        name="mismatch",
        make_fixture=base.make_fixture,
        baseline=base.baseline,
        candidate=lambda fx: {"checksum": "deadbeef", "feature_count": 0},
    )
    rec = run_target(broken, ResourceBudgets(), seed=0, size=8, repetitions=1)
    assert rec["status"] == "checksum_mismatch"
    assert rec["deterministic"]["checksum_match"] is False


def test_malformed_record():
    base = TARGETS["checkpoint_recovery_planning"]
    malformed = TargetSpec(
        name="malformed",
        make_fixture=base.make_fixture,
        baseline=base.baseline,
        candidate=lambda fx: {"feature_count": 0},
    )
    rec = run_target(malformed, ResourceBudgets(), seed=0, size=8, repetitions=1)
    assert rec["status"] == "malformed_record"


def test_target_exception_is_error():
    base = TARGETS["checkpoint_recovery_planning"]
    boom = TargetSpec(
        name="boom",
        make_fixture=base.make_fixture,
        baseline=base.baseline,
        candidate=lambda fx: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    rec = run_target(boom, ResourceBudgets(), seed=0, size=8, repetitions=1)
    assert rec["status"] == "error"
