"""Budget overrun, checksum mismatch, malformed records, and missing metrics."""
from __future__ import annotations

import sys

from tools.benchmarks.batch2_pipeline.budgets import ResourceBudgets, compare_budget
from tools.benchmarks.batch2_pipeline.harness import run_target
from tools.benchmarks.batch2_pipeline.telemetry import measure
from tools.benchmarks.batch2_pipeline.workloads import TARGETS, TargetSpec
import tools.benchmarks.batch2_pipeline.telemetry as telemetry


def test_budget_pass():
    huge = ResourceBudgets(memory_bytes=10**12, disk_bytes=10**12, max_workers=1)
    rec = run_target(
        TARGETS["subject_loop_disk_staging"],
        huge,
        seed=0,
        size=8,
        repetitions=1,
    )
    assert rec["deterministic"]["budget"]["within_budget"] is True
    assert rec["status"] == "ok"


def test_budget_overrun_memory():
    tiny = ResourceBudgets(memory_bytes=1, disk_bytes=10**12, max_workers=1)
    rec = run_target(TARGETS["full_recording_reread"], tiny, seed=0, size=12, repetitions=1)
    assert rec["deterministic"]["budget"]["within_budget"] is False
    assert rec["status"] == "budget_overrun"


def test_budget_overrun_disk():
    tiny = ResourceBudgets(memory_bytes=10**12, disk_bytes=1, max_workers=1)
    rec = run_target(TARGETS["subject_loop_disk_staging"], tiny, seed=0, size=12, repetitions=1)
    assert rec["deterministic"]["budget"]["checks"]["disk_within_budget"] is False
    assert rec["status"] == "budget_overrun"


def test_missing_metric_is_null_not_zero():
    result = compare_budget(
        {
            "tracemalloc_peak_bytes": 100,
            "disk_bytes": None,
            "runtime_best_s": 0.01,
            "rss_after_bytes": None,
            "worker_count": 1,
        },
        ResourceBudgets(memory_bytes=1000, max_workers=1),
    )
    assert result["checks"]["disk_within_budget"] is None
    assert result["checks"]["rss_within_budget"] is None


def test_runtime_and_rss_budgets_are_advisory_not_status_gates():
    """Regression: brittle wall-clock/RSS thresholds must not set budget_overrun."""
    tiny_timing = ResourceBudgets(
        memory_bytes=10**12,
        # This workload has no disk measurement; keep the test scoped to the
        # advisory runtime/RSS limits instead of expecting a disk-budget pass.
        disk_bytes=None,
        runtime_s=1e-18,
        rss_bytes=1,
        max_workers=1,
    )
    rec = run_target(
        TARGETS["full_recording_reread"], tiny_timing, seed=0, size=8, repetitions=1
    )
    checks = rec["deterministic"]["budget"]["checks"]
    assert checks["runtime_within_budget"] is False
    # RSS may be unavailable (None) on some hosts; when present it must be advisory.
    assert checks["rss_within_budget"] in (False, None)
    assert rec["deterministic"]["budget"]["within_budget"] is True
    assert rec["status"] == "ok"
    assert "advisory resource note" in " ".join(rec.get("recommendations") or [])


def test_measure_reports_null_for_unavailable(monkeypatch):
    monkeypatch.setattr(telemetry, "_PSUTIL", None)
    monkeypatch.setattr(sys, "platform", "darwin")
    out = measure(lambda: {"checksum": "abc", "feature_count": 1}, repetitions=1)
    assert out["rss_after_bytes"] is None
    assert out["disk_bytes"] is None
    assert out["read_counts"] is None


def test_checksum_mismatch():
    base = TARGETS["window_cache_hits"]
    broken = TargetSpec(
        name="mismatch",
        path_family="test",
        make_fixture=base.make_fixture,
        baseline=base.baseline,
        candidate=lambda fx: {"checksum": "deadbeef", "feature_count": 0, "worker_count": 1},
    )
    rec = run_target(broken, ResourceBudgets(max_workers=1), seed=0, size=8, repetitions=1)
    assert rec["status"] == "checksum_mismatch"
    assert rec["deterministic"]["checksum_match"] is False


def test_malformed_record():
    base = TARGETS["window_cache_hits"]
    malformed = TargetSpec(
        name="malformed",
        path_family="test",
        make_fixture=base.make_fixture,
        baseline=base.baseline,
        candidate=lambda fx: {"feature_count": 0, "worker_count": 1},
    )
    rec = run_target(malformed, ResourceBudgets(max_workers=1), seed=0, size=8, repetitions=1)
    assert rec["status"] == "malformed_record"


def test_target_exception_is_error():
    base = TARGETS["window_cache_hits"]
    boom = TargetSpec(
        name="boom",
        path_family="test",
        make_fixture=base.make_fixture,
        baseline=base.baseline,
        candidate=lambda fx: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    rec = run_target(boom, ResourceBudgets(max_workers=1), seed=0, size=8, repetitions=1)
    assert rec["status"] == "error"
