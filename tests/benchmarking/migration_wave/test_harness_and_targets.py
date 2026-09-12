"""In-process probes and current-main target coverage."""
from __future__ import annotations

from tools.benchmarking.pipeline_efficiency.budgets import ResourceBudgets
from tools.benchmarking.migration_wave.harness import run_all, run_in_process
from tools.benchmarking.migration_wave.probes import PROBES, run_probe
from tools.benchmarking.migration_wave.schema import EVIDENCE_CLASS, TARGET_NAMES


def test_all_targets_run_on_current_main():
    for name in sorted(TARGET_NAMES):
        row = run_probe(name, seed=0, size=32)
        assert row["evidence_class"] == EVIDENCE_CLASS
        assert row["synthetic"] is True
        assert row["status"] in {"ok", "production_unavailable", "checksum_mismatch", "partial_state", "duplicate_work"}
        if row["status"] == "ok":
            assert row["checksum"]
            assert row["worker_count"] == 1


def test_measured_splits_correctness_and_telemetry():
    measured = run_in_process("planning_latency", seed=0, size=32, repetitions=1)
    assert measured["ok"] is True
    assert "checksum" in measured
    assert "runtime_best_s" in measured
    assert measured.get("rss_after_bytes") != 0


def test_run_all_current_main_only():
    report = run_all(
        ResourceBudgets(),
        seed=0,
        size=32,
        repetitions=1,
        variants=["current_main"],
    )
    assert report["evidence_class"] == EVIDENCE_CLASS
    assert report["synthetic"] is True
    mains = [row for row in report["results"] if row["variant"] == "current_main"]
    assert {row["target"] for row in mains} == set(TARGET_NAMES)
    assert report["config"]["max_workers"] == 1


def test_probe_registry_matches_schema():
    assert set(PROBES) == set(TARGET_NAMES)
