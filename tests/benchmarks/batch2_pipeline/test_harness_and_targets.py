"""Deterministic checksums, counter deltas, and target inventory."""
from __future__ import annotations

import json
import pytest
import tools.benchmarks.batch2_pipeline.harness as harness

from tools.benchmarks.batch2_pipeline.budgets import ResourceBudgets
from tools.benchmarks.batch2_pipeline.harness import run_all, run_target
from tools.benchmarks.batch2_pipeline.schema import TARGET_NAMES
from tools.benchmarks.batch2_pipeline.workloads import TARGETS, TargetSpec


def test_all_targets_registered():
    assert set(TARGETS) == set(TARGET_NAMES)


def test_run_all_rejects_unknown_api_target():
    with pytest.raises(ValueError, match="unknown target"):
        run_all(
            ResourceBudgets(max_workers=1),
            seed=0,
            size=8,
            repetitions=1,
            targets=["not_a_registered_target"],
        )


def test_run_all_rejects_empty_target_selection():
    with pytest.raises(ValueError, match="at least one target"):
        run_all(targets=[])


def test_run_all_does_not_claim_complete_success_with_unknown_measurements(monkeypatch):
    base = TARGETS["window_cache_hits"]
    malformed = TargetSpec(
        name=base.name,
        path_family=base.path_family,
        make_fixture=base.make_fixture,
        baseline=base.baseline,
        candidate=lambda fixture: {"feature_count": 0, "worker_count": 1},
    )
    monkeypatch.setitem(harness.TARGETS, base.name, malformed)

    report = run_all(
        ResourceBudgets(max_workers=1),
        seed=0,
        size=8,
        repetitions=1,
        targets=[base.name, "full_recording_reread"],
    )

    assert report["summary"]["malformed_record"] == 1
    assert report["all_equivalent"] is None
    assert report["all_within_budget"] is None


def test_deterministic_checksums_stable_across_runs():
    huge = ResourceBudgets(memory_bytes=10**12, disk_bytes=10**12, max_workers=1)
    a = run_all(huge, seed=7, size=12, repetitions=1)
    b = run_all(huge, seed=7, size=12, repetitions=1)
    assert a["all_equivalent"] is True
    for ra, rb in zip(a["results"], b["results"]):
        assert ra["deterministic"]["checksum_baseline"] == rb["deterministic"]["checksum_baseline"]
        assert ra["deterministic"]["checksum_candidate"] == rb["deterministic"]["checksum_candidate"]
        assert ra["deterministic"]["checksum_match"] is True


def test_engineering_counters_exclude_advisory_timing_and_are_stable():
    """Regression: timing must not live in counters or break counter determinism."""
    from tools.benchmarks.batch2_pipeline.schema import COUNTER_KEYS

    huge = ResourceBudgets(memory_bytes=10**12, disk_bytes=10**12, max_workers=1)
    a = run_all(huge, seed=11, size=12, repetitions=1)
    b = run_all(huge, seed=11, size=12, repetitions=1)
    for ra, rb in zip(a["results"], b["results"]):
        for side in ("baseline", "candidate"):
            counters = ra["telemetry"][side]["counters"]
            assert set(counters) <= set(COUNTER_KEYS)
            assert "process_work_s" not in counters
            assert "checkpoint_s" not in counters
            other = rb["telemetry"][side]["counters"]
            assert {k: counters[k] for k in COUNTER_KEYS} == {
                k: other[k] for k in COUNTER_KEYS
            }
        # Advisory timing remains available on the telemetry object when measured.
        tel = ra["telemetry"]["baseline"]
        assert "process_work_s" in tel and "checkpoint_s" in tel


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
    base_c = rec["telemetry"]["baseline"]["counters"]
    cand_c = rec["telemetry"]["candidate"]["counters"]
    base = rec["telemetry"]["baseline"]
    cand = rec["telemetry"]["candidate"]
    assert base_c["fsync_calls"] > cand_c["fsync_calls"]
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
