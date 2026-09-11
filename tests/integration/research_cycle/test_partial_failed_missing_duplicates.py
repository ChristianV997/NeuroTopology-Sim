"""Partial runs, failed stages, missing artifacts, and duplicate records."""
from __future__ import annotations

from pathlib import Path

from tests.integration.research_cycle.fixtures import (
    ARTIFACT_ID,
    failed_simulation_chain,
    happy_chain,
    partial_chain,
    write_chain,
)
from tests.integration.research_cycle.inspector import inspect_directory, stamp_checksum, write_document


def test_partial_runs_remain_partial(tmp_path: Path) -> None:
    write_chain(tmp_path, partial_chain())
    report = inspect_directory(tmp_path)
    assert report.status == "PARTIAL"
    by_id = {doc.record_id: doc for doc in report.documents}
    assert by_id[ARTIFACT_ID].status == "PARTIAL"
    downstream = [
        doc for doc in report.documents if ARTIFACT_ID in doc.parent_ids or doc.stage in {
            "validation_report",
            "evidence_graph",
            "release_evidence_report",
        }
    ]
    assert downstream
    assert all(doc.status != "COMPLETE" or ARTIFACT_ID not in doc.parent_ids for doc in downstream)
    assert "metrics.json" in report.missing_artifacts
    assert not any(doc.scientific_verdict in {"PASS", "SUPPORTED"} for doc in report.documents)


def test_failed_stage_produces_diagnosable_downstream_state(tmp_path: Path) -> None:
    write_chain(tmp_path, failed_simulation_chain())
    report = inspect_directory(tmp_path)
    assert report.status == "FAILED"
    assert report.upstream_failures
    for doc in report.documents:
        if doc.stage in {
            "artifact_manifest",
            "validation_report",
            "evidence_graph",
            "release_evidence_report",
        }:
            assert doc.status in {"FAILED", "BLOCKED", "PARTIAL", "INCOMPLETE"}
            assert doc.diagnostics.get("upstream_failures")
            assert doc.scientific_verdict in {"BLOCKED", "INCONCLUSIVE", "NOT_APPLICABLE"}


def test_missing_artifacts_are_visible(tmp_path: Path) -> None:
    docs = happy_chain()
    artifacts = dict(docs[4])
    artifacts["status"] = "INCOMPLETE"
    artifacts["payload"] = dict(artifacts["payload"])
    artifacts["payload"]["check_artifacts"] = True
    artifacts["payload"]["artifacts"] = [
        {"relative_path": "summary.json", "sha256": "a" * 64, "size_bytes": 1},
        {"relative_path": "metrics.json", "sha256": "b" * 64, "size_bytes": 1},
    ]
    artifacts["diagnostics"] = {
        "missing": ["summary.json", "metrics.json"],
        "errors": ["required metrics artifact is absent"],
        "duplicates": [],
    }
    write_chain(tmp_path, docs[:4] + [stamp_checksum(artifacts)] + docs[5:])
    report = inspect_directory(tmp_path)
    assert "summary.json" in report.missing_artifacts
    assert "metrics.json" in report.missing_artifacts
    assert report.status in {"INCOMPLETE", "BLOCKED", "PARTIAL"}


def test_duplicate_records_are_detected(tmp_path: Path) -> None:
    docs = happy_chain()
    duplicate = dict(docs[2])
    duplicate["record_id"] = docs[1]["record_id"]
    write_chain(tmp_path, docs)
    write_document(tmp_path / "09_duplicate_hypothesis.json", stamp_checksum(duplicate))
    report = inspect_directory(tmp_path)
    assert report.duplicate_record_ids
    assert docs[1]["record_id"] in report.duplicate_record_ids
    assert report.status != "COMPLETE"


def test_broken_parent_checksum_is_not_evidence(tmp_path: Path) -> None:
    docs = happy_chain()
    run = dict(docs[3])
    run["parent_checksums"] = ["0" * 64]
    write_chain(tmp_path, docs[:3] + [stamp_checksum(run)] + docs[4:])
    report = inspect_directory(tmp_path)
    assert any("parent checksum" in item for item in report.errors)
    assert report.status != "COMPLETE"
