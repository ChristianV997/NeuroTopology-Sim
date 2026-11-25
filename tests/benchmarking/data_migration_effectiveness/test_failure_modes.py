"""Timeout, corruption, partial-transfer, disk-budget, and missing-metric cases."""
from __future__ import annotations

import sys

from tools.benchmarking.data_migration_effectiveness.budgets import ResourceBudgets, compare_budget
from tools.benchmarking.data_migration_effectiveness.harness import run_target
from tools.benchmarking.data_migration_effectiveness.telemetry import measure
from tools.benchmarking.data_migration_effectiveness.workloads import TARGETS, TargetSpec
import tools.benchmarking.data_migration_effectiveness.telemetry as telemetry


def test_timeout_case_is_local_and_checksum_stable():
    rec = run_target("timeout_case", ResourceBudgets(), seed=0, size=32, repetitions=1)
    assert rec["status"] == "timeout"
    assert rec["deterministic"]["checksum_match"] is True
    body = rec["deterministic"]["correctness_candidate"]
    assert body["success"] is False
    assert rec["scientific_improvement_claimed"] is False


def test_corruption_case_detects_local_bitflip():
    rec = run_target("corruption_case", ResourceBudgets(), seed=0, size=32, repetitions=1)
    assert rec["deterministic"]["checksum_match"] is True
    body = rec["deterministic"]["correctness_candidate"]
    assert body["first_success"] is True
    assert body["detected_mismatch"] is True


def test_partial_transfer_cleans_stale_part():
    rec = run_target("partial_transfer_case", ResourceBudgets(), seed=0, size=32, repetitions=1)
    assert rec["deterministic"]["checksum_match"] is True
    body = rec["deterministic"]["correctness_candidate"]
    assert body["cleaned"] >= 1
    assert body["stale_remaining"] is False


def test_disk_budget_rejects_oversized_object():
    rec = run_target("disk_budget_case", ResourceBudgets(), seed=0, size=32, repetitions=1)
    assert rec["deterministic"]["checksum_match"] is True
    body = rec["deterministic"]["correctness_candidate"]
    assert body["success"] is False
    assert body["error_code"] in {"CACHE_BUDGET_EXCEEDED", "DISK_EXHAUSTION", "ACTIVE_LEASE_LOCKED"}
    assert body["payload_size"] > body["max_cache_bytes"]


def test_retry_overhead_recovers_after_transient():
    rec = run_target("retry_overhead", ResourceBudgets(), seed=0, size=32, repetitions=1)
    assert rec["deterministic"]["checksum_match"] is True
    body = rec["deterministic"]["correctness_candidate"]
    assert body["success"] is True
    assert body["attempts"] >= 3
    assert rec["telemetry"]["candidate"]["retry_attempts"] >= 3


def test_manifest_recovery_from_corrupt_dest():
    rec = run_target("manifest_recovery", ResourceBudgets(), seed=0, size=32, repetitions=1)
    assert rec["status"] == "ok"
    assert rec["deterministic"]["correctness_candidate"]["recovered"] is True


def test_cache_occupancy_and_eviction_recorded():
    rec = run_target("cache_occupancy_and_eviction", ResourceBudgets(), seed=0, size=32, repetitions=1)
    assert rec["deterministic"]["checksum_match"] is True
    occ = rec["telemetry"]["candidate"]["cache_occupancy_bytes"]
    evicted = rec["telemetry"]["candidate"]["evicted_bytes"]
    assert occ is None or occ >= 0
    assert evicted is None or evicted >= 0


def test_budget_overrun():
    tiny = ResourceBudgets(memory_bytes=1, disk_bytes=1)
    rec = run_target("planning_latency", tiny, seed=0, size=32, repetitions=1)
    assert rec["deterministic"]["budget"]["within_budget"] is False
    assert rec["status"] == "budget_overrun"


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
    assert out["cache_occupancy_bytes"] is None
    assert out["planning_latency_s"] is None


def test_checksum_mismatch():
    broken = TargetSpec(
        name="planning_latency",
        baseline=TARGETS["planning_latency"].baseline,
        candidate=lambda fx: {"checksum": "deadbeef", "feature_count": 0},
    )
    TARGETS["_tmp_mismatch"] = broken
    try:
        rec = run_target("_tmp_mismatch", ResourceBudgets(), seed=0, size=16, repetitions=1)
        assert rec["status"] == "checksum_mismatch"
        assert rec["deterministic"]["checksum_match"] is False
    finally:
        TARGETS.pop("_tmp_mismatch", None)


def test_malformed_record():
    broken = TargetSpec(
        name="planning_latency",
        baseline=TARGETS["planning_latency"].baseline,
        candidate=lambda fx: {"feature_count": 0},
    )
    TARGETS["_tmp_malformed"] = broken
    try:
        rec = run_target("_tmp_malformed", ResourceBudgets(), seed=0, size=16, repetitions=1)
        assert rec["status"] == "malformed_record"
    finally:
        TARGETS.pop("_tmp_malformed", None)


def test_target_exception_is_error():
    broken = TargetSpec(
        name="planning_latency",
        baseline=TARGETS["planning_latency"].baseline,
        candidate=lambda fx: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    TARGETS["_tmp_boom"] = broken
    try:
        rec = run_target("_tmp_boom", ResourceBudgets(), seed=0, size=16, repetitions=1)
        assert rec["status"] == "error"
        assert rec["deterministic"]["checksum_match"] is None
    finally:
        TARGETS.pop("_tmp_boom", None)
