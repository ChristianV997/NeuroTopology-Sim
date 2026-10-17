"""Deterministic checksums, counter deltas, and target inventory."""
from __future__ import annotations

import json

from tools.benchmarks.batch2_pipeline.budgets import ResourceBudgets
from tools.benchmarks.batch2_pipeline.harness import run_all, run_target
from tools.benchmarks.batch2_pipeline.schema import TARGET_NAMES
from tools.benchmarks.batch2_pipeline.workloads import TARGETS


def test_all_targets_registered():
    assert set(TARGETS) == set(TARGET_NAMES)


def test_deterministic_checksums_stable_across_runs():
    huge = ResourceBudgets(memory_bytes=10**12, disk_bytes=10**12, max_workers=1)
    a = run_all(huge, seed=7, size=12, repetitions=1)
    b = run_all(huge, seed=7, size=12, repetitions=1)
    assert a["all_equivalent"] is True
    for ra, rb in zip(a["results"], b["results"]):
        assert ra["deterministic"]["checksum_baseline"] == rb["deterministic"]["checksum_baseline"]
        assert ra["deterministic"]["checksum_candidate"] == rb["deterministic"]["checksum_candidate"]
        assert ra["deterministic"]["checksum_match"] is True


def test_full_recording_reread_reduces_reads():
    rec = run_target(
        TARGETS["full_recording_reread"],
        ResourceBudgets(max_workers=1),
        seed=0,
        size=12,
        repetitions=1,
    )
    base = rec["telemetry"]["baseline"]["counters"]
    cand = rec["telemetry"]["candidate"]["counters"]
    assert base["read_counts"] > cand["read_counts"]
    assert rec["status"] == "ok"


def test_preprocess_per_window_reduces_preprocess_calls():
    rec = run_target(
        TARGETS["preprocess_per_window"],
        ResourceBudgets(max_workers=1),
        seed=0,
        size=12,
        repetitions=1,
    )
    base = rec["telemetry"]["baseline"]["counters"]
    cand = rec["telemetry"]["candidate"]["counters"]
    assert base["preprocess_calls"] > cand["preprocess_calls"]
    assert cand["preprocess_calls"] == 1


def test_checkpoint_splits_process_and_fsync():
    rec = run_target(
        TARGETS["checkpoint_fsync_overhead"],
        ResourceBudgets(max_workers=1),
        seed=0,
        size=12,
        repetitions=1,
    )
    base = rec["telemetry"]["baseline"]["counters"]
    cand = rec["telemetry"]["candidate"]["counters"]
    assert base["fsync_calls"] > cand["fsync_calls"]
    assert base["process_work_s"] is not None
    assert base["checkpoint_s"] is not None
    assert cand["checkpoint_s"] is not None


def test_finite_json_report():
    report = run_all(ResourceBudgets(max_workers=1), seed=0, size=8, repetitions=1)
    text = json.dumps(report, allow_nan=False)
    json.loads(text, parse_constant=lambda t: (_ for _ in ()).throw(ValueError(t)))


def test_bottleneck_ranking_present():
    report = run_all(ResourceBudgets(max_workers=1), seed=0, size=8, repetitions=1)
    assert len(report["bottleneck_ranking"]) == len(TARGETS)
    assert report["bottleneck_ranking"][0]["rank"] == 1
