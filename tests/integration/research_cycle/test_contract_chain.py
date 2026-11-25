"""Happy-path file chain: versions, checksums, provenance, determinism."""
from __future__ import annotations

import json
from pathlib import Path

from tests.integration.research_cycle.contracts import PIPELINE_CONTRACT, STAGE_ORDER
from tests.integration.research_cycle.fixtures import happy_chain, write_chain, write_happy_chain
from tests.integration.research_cycle.inspector import (
    canonical_checksum,
    inspect_directory,
    parse_stage_document,
    stamp_checksum,
)


def test_every_producer_declares_schema_version(tmp_path: Path) -> None:
    paths = write_happy_chain(tmp_path)
    assert len(paths) == len(STAGE_ORDER)
    for path, stage in zip(paths, STAGE_ORDER):
        document = json.loads(path.read_text(encoding="utf-8"))
        assert document["schema_version"]
        assert document["stage"] == stage
        assert document["pipeline_contract"] == PIPELINE_CONTRACT
        parsed = parse_stage_document(path)
        assert parsed.schema_version == document["schema_version"]


def test_checksums_and_ids_stable_across_serialization(tmp_path: Path) -> None:
    first = write_happy_chain(tmp_path / "a")
    second = write_happy_chain(tmp_path / "b")
    for left, right in zip(first, second):
        raw_left = left.read_bytes()
        raw_right = right.read_bytes()
        assert raw_left == raw_right
        doc = json.loads(raw_left.decode("utf-8"))
        assert doc["record_id"]
        assert doc["checksum"] == canonical_checksum(doc)
        reloaded = json.loads(json.dumps(doc, sort_keys=True))
        assert reloaded["record_id"] == doc["record_id"]
        assert canonical_checksum(reloaded) == doc["checksum"]


def test_provenance_links_remain_intact(tmp_path: Path) -> None:
    write_happy_chain(tmp_path)
    report = inspect_directory(tmp_path)
    assert report.status == "COMPLETE"
    by_id = {doc.record_id: doc for doc in report.documents}
    for doc in report.documents:
        for parent_id, parent_checksum in zip(doc.parent_ids, doc.parent_checksums):
            parent = by_id[parent_id]
            assert parent.checksum == parent_checksum
            assert parent.record_id == parent_id


def test_pipeline_is_deterministic_on_identical_fixtures(tmp_path: Path) -> None:
    write_happy_chain(tmp_path / "one")
    write_happy_chain(tmp_path / "two")
    first = inspect_directory(tmp_path / "one")
    second = inspect_directory(tmp_path / "two")
    assert first.to_dict() == second.to_dict()
    assert [doc.checksum for doc in first.documents] == [doc.checksum for doc in second.documents]


def test_nested_payload_records_declare_schema_versions(tmp_path: Path) -> None:
    write_happy_chain(tmp_path)
    hyp = json.loads((tmp_path / "03_hypothesis_experiment_manifest.json").read_text(encoding="utf-8"))
    payload = hyp["payload"]
    assert payload["schema_version"] == "ResearchCycleRegistry.v1"
    hypothesis = next(iter(payload["hypotheses"].values()))
    plan = next(iter(payload["plans"].values()))
    assert hypothesis["schema_version"] == "HypothesisRecord.v1"
    assert plan["schema_version"] == "ExperimentPlan.v1"
    run = json.loads((tmp_path / "04_simulation_run_manifest.json").read_text(encoding="utf-8"))
    assert run["payload"]["schema_version"] == "0.1"
    lit = json.loads((tmp_path / "01_literature_source_manifest.json").read_text(encoding="utf-8"))
    assert lit["payload"]["schema"] == "NeuroTopologySim.EmpiricalSourceManifest.v1"


def test_stamp_checksum_is_idempotent() -> None:
    chain = happy_chain()
    for document in chain:
        again = stamp_checksum(dict(document))
        assert again["checksum"] == document["checksum"]
        assert again["record_id"] == document["record_id"]


GOLDEN_ROOT = Path(__file__).resolve().parent / "golden"


def test_write_chain_uses_declared_stage_order(tmp_path: Path) -> None:
    paths = write_chain(tmp_path, happy_chain())
    names = [path.name for path in paths]
    assert names == [f"{index:02d}_{stage}.json" for index, stage in enumerate(STAGE_ORDER, start=1)]


def test_committed_golden_happy_chain_is_complete() -> None:
    report = inspect_directory(GOLDEN_ROOT / "happy")
    assert report.status == "COMPLETE"
    assert [doc.stage for doc in report.documents] == list(STAGE_ORDER)
    assert report.solver_executed is False
    assert report.network_accessed is False


def test_committed_golden_partial_and_failed_remain_non_complete() -> None:
    partial = inspect_directory(GOLDEN_ROOT / "partial")
    failed = inspect_directory(GOLDEN_ROOT / "failed")
    assert partial.status == "PARTIAL"
    assert failed.status == "FAILED"
    assert partial.missing_artifacts
    assert failed.upstream_failures
