"""End-to-end fixture tests against the real, canonical
``tools/simulation_artifacts/extractor.py`` (read-only, not modified or
duplicated here). Covers "partial or timed-out simulation" -- the one
required scenario the claim gate itself has no reason code for.
"""
from __future__ import annotations

from pathlib import Path

from tools.simulation_artifacts.extractor import extract_run

_RUNS_DIR = Path(__file__).resolve().parent / "fixtures" / "simulation_runs"
_INCOMPLETE_STATUSES = {"INCOMPLETE", "PARTIAL", "FAILED", "CONFLICTING", "BLOCKED"}


def test_interrupted_run_is_reported_partial_not_complete():
    report = extract_run(_RUNS_DIR / "partial_run")
    assert report["status"] == "PARTIAL"
    assert report["status"] in _INCOMPLETE_STATUSES
    assert "RunRecord.json" in report["diagnostics"]["partial"]
    assert report["read_only"] is True
    assert report["solver_executed"] is False
    assert report["heavy_runtime_imported"] is False


def test_failed_run_is_reported_failed_not_complete():
    report = extract_run(_RUNS_DIR / "failed_run")
    assert report["status"] == "FAILED"
    assert report["status"] in _INCOMPLETE_STATUSES
    assert "RunRecord.json" in report["diagnostics"]["failed"]


def test_complete_run_is_reported_complete_proving_the_suite_is_not_indiscriminate():
    report = extract_run(_RUNS_DIR / "complete_run")
    assert report["status"] == "COMPLETE"
    assert report["diagnostics"] == {"missing": [], "stale": [], "partial": [], "failed": [], "conflicting": [], "errors": []}


def test_partial_and_failed_runs_are_correctly_labeled_synthetic_not_empirical():
    for name in ("partial_run", "failed_run", "complete_run"):
        report = extract_run(_RUNS_DIR / name)
        assert report["evidence"]["synthetic"] is True
        assert report["evidence"]["evidence_class"] == "synthetic_demo_only"


def test_extraction_never_runs_a_solver_or_touches_the_network():
    """The extractor only scans an existing directory; this asserts that
    contract at the report level, not just by not importing anything
    itself."""
    for name in ("partial_run", "failed_run", "complete_run"):
        report = extract_run(_RUNS_DIR / name)
        assert report["read_only"] is True
        assert report["solver_executed"] is False
        assert report["heavy_runtime_imported"] is False
