from __future__ import annotations

import ast
import json
from pathlib import Path
import threading

import pytest

from awareness_studio.research_cycle import (
    ArtifactManifest,
    Claim,
    EvidenceClass,
    EvidenceRecord,
    ExperimentSpec,
    Hypothesis,
    ImmutableCycleError,
    ResearchCycleError,
    ResearchCycleLedger,
    RunRecordLink,
    SourceSnapshot,
    TheoryRevision,
    ValidationReport,
    canonical_json,
    record_from_dict,
    sha256_json,
    stable_id,
)


LIMITATIONS = ("This record is metadata and does not establish a scientific conclusion.",)
SOURCE_SHA = "a" * 64
PROVENANCE_SHA = "b" * 64


def source(cycle: str = "cycle-1") -> SourceSnapshot:
    return SourceSnapshot(
        snapshot_id="snapshot-1",
        cycle_id=cycle,
        source_uri="local-fixture://source",
        source_sha256=SOURCE_SHA,
        data_mode="synthetic_demo",
        evidence_class=EvidenceClass.SYNTHETIC_DEMONSTRATION,
        claim_scope="Synthetic fixture provenance only.",
        scientific_limitations=LIMITATIONS,
        metadata={"units": "a.u."},
    )


def chain(cycle: str = "cycle-1") -> list:
    return [
        source(cycle),
        EvidenceRecord("evidence-1", cycle, ("snapshot-1",), "A bounded local fixture was observed.", "synthetic_demo", EvidenceClass.SYNTHETIC_DEMONSTRATION, "Fixture behavior only.", LIMITATIONS, {"score": float("inf")}, ("snapshot-1",)),
        Claim("claim-1", cycle, "The fixture serialization is repeatable.", ("evidence-1",), EvidenceClass.ENGINEERING_FACT, "Serialization behavior only.", LIMITATIONS, parent_ids=("evidence-1",)),
        Hypothesis("hypothesis-1", cycle, "The ledger preserves event order.", ("claim-1",), claim_scope="Ledger behavior only.", parent_ids=("claim-1",)),
        ExperimentSpec("experiment-1", cycle, ("hypothesis-1",), "local fixture execution", {"seed": 7}, parent_ids=("hypothesis-1",)),
        RunRecordLink("run-1", cycle, "experiment-1", "0.1", "c" * 64, "COMPLETED", EvidenceClass.BENCHMARK_RESULT, "Run linkage only.", LIMITATIONS, parent_ids=("experiment-1",)),
        ArtifactManifest("manifest-1", cycle, "run-1", {"result.json": {"sha256": "d" * 64, "path": "artifacts/result.json"}}, EvidenceClass.BENCHMARK_RESULT, "Artifact integrity only.", LIMITATIONS, parent_ids=("run-1",)),
        ValidationReport("validation-1", cycle, ("manifest-1",), "run-1", "REVIEW_REQUIRED", {"finite_json": True}, EvidenceClass.BENCHMARK_RESULT, "Validation behavior only.", LIMITATIONS, parent_ids=("manifest-1",)),
        TheoryRevision("revision-1", cycle, ("hypothesis-1",), ("validation-1",), "Retain the hypothesis for review.", EvidenceClass.SPECULATION, "Revision proposal only.", LIMITATIONS, parent_ids=("validation-1", "hypothesis-1")),
    ]


def test_canonical_serialization_and_stable_hashes():
    left = {"b": 2, "a": [1, True]}
    right = {"a": [1, True], "b": 2}
    assert canonical_json(left) == canonical_json(right)
    assert sha256_json(left) == sha256_json(right)
    assert stable_id("claim", left) == stable_id("claim", right)
    assert SourceSnapshot(**source().__dict__).checksum == source().checksum


def test_full_chain_is_typed_append_only_and_exportable(tmp_path: Path):
    ledger = ResearchCycleLedger(tmp_path / "cycle.sqlite3")
    cycle_id = ledger.create_cycle("cycle-1", metadata={"purpose": "local test"})
    records = chain(cycle_id)
    for record in records:
        ledger.append_record(cycle_id, record)
    assert {item.record_type for item in ledger.records(cycle_id)} == {item.record_type for item in records}
    assert ledger.recover(cycle_id)
    exported = json.loads(ledger.export_json(cycle_id))
    assert exported["schema_version"]
    assert len(exported["records"]) == 9
    assert len(ledger.export_jsonl(cycle_id).splitlines()) == 10
    restored = record_from_dict(next(item for item in exported["records"] if item["record_type"] == "source_snapshot"))
    assert restored.record_id == "snapshot-1"
    assert exported["export_checksum"] == sha256_json({key: value for key, value in exported.items() if key != "export_checksum"})


def test_sequence_monotonicity_idempotency_and_unknown_events(tmp_path: Path):
    ledger = ResearchCycleLedger(tmp_path / "events.sqlite3")
    cycle_id = ledger.create_cycle("cycle-1")
    first = ledger.append_event(cycle_id, "cycle_revision", producer="test", status="REVIEW_REQUIRED", payload={"reason": "method"})
    repeat = ledger.append_event(cycle_id, "cycle_revision", producer="test", status="REVIEW_REQUIRED", payload={"reason": "method"})
    second = ledger.append_event(cycle_id, "cycle_revision", producer="test", status="BLOCKED", payload={"reason": "dependency"})
    assert first.event_id == repeat.event_id
    assert [event.sequence for event in ledger.events(cycle_id)] == [1, 2, 3]
    assert second.previous_hash == first.event_hash
    with pytest.raises(Exception, match="unknown event_type"):
        ledger.append_event(cycle_id, "mystery", producer="test", status="COMPLETED", payload={})


def test_concurrent_writers_get_unique_monotonic_sequences(tmp_path: Path):
    path = tmp_path / "concurrent.sqlite3"
    ResearchCycleLedger(path).create_cycle("cycle-1")
    barrier = threading.Barrier(4)
    errors: list[Exception] = []

    def write(index: int) -> None:
        try:
            ledger = ResearchCycleLedger(path)
            barrier.wait()
            ledger.append_event("cycle-1", "cycle_revision", producer=f"worker-{index}", status="COMPLETED", payload={"index": index})
        except Exception as exc:  # pragma: no cover - failure is asserted below
            errors.append(exc)

    threads = [threading.Thread(target=write, args=(index,)) for index in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
    assert not errors
    events = ResearchCycleLedger(path).events("cycle-1")
    assert [event.sequence for event in events] == list(range(1, 6))
    assert len({event.event_id for event in events}) == 5


def test_interrupted_transaction_rolls_back_and_recovers(tmp_path: Path):
    ledger = ResearchCycleLedger(tmp_path / "interrupted.sqlite3")
    ledger.create_cycle("cycle-1")
    with pytest.raises(RuntimeError):
        with ledger._transaction() as connection:
            ledger._append_event_connection(connection, cycle_id="cycle-1", event_type="cycle_revision", producer="test", status="FAILED", payload={"interrupted": True})
            raise RuntimeError("simulated process interruption")
    assert ledger.recover("cycle-1")
    assert [event.sequence for event in ledger.events("cycle-1")] == [1]
    assert ledger.append_event("cycle-1", "cycle_revision", producer="test", status="COMPLETED", payload={"after": "recovery"}).sequence == 2


def test_finalized_cycle_rejects_edits_and_child_cycle_supports_revision(tmp_path: Path):
    ledger = ResearchCycleLedger(tmp_path / "frozen.sqlite3")
    ledger.create_cycle("cycle-1")
    ledger.append_record("cycle-1", source())
    ledger.finalize_cycle("cycle-1")
    ledger.finalize_cycle("cycle-1")
    with pytest.raises(ImmutableCycleError):
        ledger.append_record("cycle-1", source().__class__(**{**source().__dict__, "snapshot_id": "snapshot-2"}))
    with pytest.raises(ImmutableCycleError):
        ledger.append_event("cycle-1", "cycle_revision", producer="test", status="FAILED", payload={})
    child = ledger.create_child_cycle("cycle-1", "cycle-2", revision_reason="changed method")
    revised = Hypothesis("hypothesis-2", child, "Revised method hypothesis.", ("claim-1",), claim_scope="Revision only.", parent_ids=("snapshot-1",))
    ledger.append_record(child, revised)
    assert ledger.recover(child)


def test_invalid_provenance_and_scientific_promotion_are_rejected():
    with pytest.raises(ResearchCycleError):
        SourceSnapshot("bad", "cycle-1", "local", "not-a-hash", "empirical", EvidenceClass.DESCRIPTIVE_EMPIRICAL, "scope", LIMITATIONS)
    with pytest.raises(ResearchCycleError, match="synthetic"):
        SourceSnapshot("bad", "cycle-1", "local", SOURCE_SHA, "synthetic_demo", EvidenceClass.DESCRIPTIVE_EMPIRICAL, "scope", LIMITATIONS)
    with pytest.raises(ResearchCycleError, match="proxy"):
        Claim("claim-proxy", "cycle-1", "This proxy measurement establishes a causal mechanism.", ("evidence-1",), EvidenceClass.PROXY_INFERENCE, "scope", LIMITATIONS)


def test_finite_json_and_no_network_imports():
    record = EvidenceRecord("evidence-1", "cycle-1", ("snapshot-1",), "fixture", "synthetic_demo", EvidenceClass.SYNTHETIC_DEMONSTRATION, "scope", LIMITATIONS, {"optional": float("inf")})
    encoded = canonical_json(record.to_dict())
    assert json.loads(encoded)["metrics"]["optional"] is None
    source_text = Path(__file__).parents[2] / "src" / "awareness_studio" / "research_cycle" / "ledger.py"
    tree = ast.parse(source_text.read_text(encoding="utf-8"))
    imports = [node.names[0].name for node in ast.walk(tree) if isinstance(node, ast.Import) for _ in [0]]
    assert not {"socket", "requests", "urllib", "httpx"}.intersection(imports)
