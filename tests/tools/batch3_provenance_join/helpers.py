from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


LEDGER_SCHEMA = "awareness-studio-research-cycle.v1"
EVENT_SCHEMA = "awareness-studio-research-cycle-event.v1"


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def write_json(path: Path, value: Any) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return path


def ledger_record(record_type: str, cycle_id: str, **fields: Any) -> dict[str, Any]:
    id_field = {
        "source_snapshot": "snapshot_id",
        "evidence_record": "evidence_id",
        "claim": "claim_id",
        "hypothesis": "hypothesis_id",
        "experiment_spec": "experiment_id",
        "run_record": "run_record_id",
        "artifact_manifest": "artifact_manifest_id",
        "validation_report": "validation_report_id",
        "theory_revision": "revision_id",
    }[record_type]
    record = {
        "record_type": record_type,
        **fields,
        "cycle_id": cycle_id,
        "parent_ids": fields.get("parent_ids", []),
        "child_ids": fields.get("child_ids", []),
        "status": fields.get("status", "COMPLETED"),
        "schema_version": LEDGER_SCHEMA,
        "record_id": fields[id_field],
    }
    record["checksum"] = sha(record)
    return record


def ledger_export(cycle_id: str, records: list[dict[str, Any]], *, parent_cycle_id: str | None = None, links: list[dict[str, str]] | None = None) -> dict[str, Any]:
    cycle = {
        "cycle_id": cycle_id,
        "parent_cycle_id": parent_cycle_id,
        "status": "IN_PROGRESS",
        "finalized": False,
        "metadata": {},
    }
    cycle["created_hash"] = sha({"cycle_id": cycle_id, "parent_cycle_id": parent_cycle_id, "metadata": {}})
    events = []
    previous = None
    for sequence, record in enumerate(records, 1):
        event = {
            "cycle_id": cycle_id,
            "event_id": f"event-{cycle_id}-{sequence}",
            "sequence": sequence,
            "event_type": record["record_type"],
            "producer": "fixture",
            "status": record["status"],
            "payload": record,
            "previous_hash": previous,
            "schema_version": EVENT_SCHEMA,
        }
        event["event_hash"] = sha(event)
        previous = event["event_hash"]
        events.append(event)
    document = {
        "schema_version": LEDGER_SCHEMA,
        "cycle": cycle,
        "records": records,
        "events": events,
        "links": links or [],
    }
    document["export_checksum"] = sha(document)
    return document


def valid_fixture(root: Path) -> list[Path]:
    root.mkdir(parents=True, exist_ok=True)
    (root / "source_data").mkdir(exist_ok=True)
    source_bytes = b"explicit synthetic input fixture\n"
    (root / "source.bin").write_bytes(source_bytes)
    source_sha = hashlib.sha256(source_bytes).hexdigest()
    summary_bytes = b'{"fixture_metric":0.25}\n'
    (root / "summary.json").write_bytes(summary_bytes)
    summary_sha = hashlib.sha256(summary_bytes).hexdigest()
    run = {
        "schema_version": "0.1",
        "run_id": "run-fixture-1",
        "run_kind": "hypothesis",
        "created_at": "2026-01-01T00:00:00Z",
        "elapsed_s": 0.1,
        "data_mode": "synthetic",
        "dataset_id": "dataset-fixture-1",
        "git_commit": "abc123",
        "input": {"dataset_id": "dataset-fixture-1", "seed": 4, "source_sha256": source_sha},
        "config": {"window_samples": 32},
        "artifacts": {"summary": "summary.json"},
        "source": "explicit fixture",
    }
    run_path = write_json(root / "run.json", run)
    output_manifest = {
        "schema": "NTS.IntegrationArtifactManifest.v1",
        "run_id": run["run_id"],
        "metadata": {"evidence_class": "synthetic_demo_only"},
        "artifacts": [{"relative_path": "summary.json", "sha256": summary_sha, "size_bytes": len(summary_bytes)}],
    }
    manifest_path = write_json(root / "out-manifest.json", output_manifest)
    source_manifest = {
        "schema": "NeuroTopologySim.EmpiricalSourceManifest.v1",
        "dataset_identifier": "dataset-fixture-1",
        "origin": "synthetic_demo",
        "source_url": "https://example.invalid/fixture",
        "local_root": "source_data",
        "license_id": "fixture-license-1",
    }
    source_path = write_json(root / "source-manifest.json", source_manifest)
    source_snapshot = ledger_record(
        "source_snapshot",
        "cycle-fixture-1",
        snapshot_id="snapshot-fixture-1",
        source_uri="source.bin",
        source_sha256=source_sha,
        data_mode="synthetic",
        evidence_class="synthetic_demonstration",
        claim_scope="fixture only",
        scientific_limitations=["Engineering fixture only."],
        source_format="fixture",
        captured_at="2026-01-01T00:00:00Z",
        metadata={"dataset_identifier": "dataset-fixture-1", "source_id": "dataset-fixture-1", "license_id": "fixture-license-1"},
    )
    evidence = ledger_record(
        "evidence_record",
        "cycle-fixture-1",
        evidence_id="evidence-fixture-1",
        source_snapshot_ids=["snapshot-fixture-1"],
        observation="Fixture record; no scientific observation.",
        data_mode="synthetic",
        evidence_class="synthetic_demonstration",
        claim_scope="fixture only",
        scientific_limitations=["Synthetic fixture."],
        metrics={},
    )
    ledger_path = write_json(root / "cycle-export.json", ledger_export("cycle-fixture-1", [source_snapshot, evidence]))
    identity = {
        "dataset_id": "dataset-fixture-1",
        "artifact_ids": ["artifact-summary-1"],
        "requested_use": "transition_export",
        "transition_record_ids": [],
        "phase_space_coordinate_ids": [],
    }
    bundle = {
        "schema_version": "1",
        "bundle_id": hashlib.sha256(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()[:16],
        "dataset_id": "dataset-fixture-1",
        "artifact_ids": ["artifact-summary-1"],
        "artifact_paths": {"source": "source.bin"},
        "registry_decisions": [{
            "id": "artifact-summary-1",
            "kind": "artifact",
            "requested_use": "transition_export",
            "allowed": True,
            "reason": "fixture-only decision reference",
        }],
        "requested_use": "transition_export",
        "transition_record_ids": [],
        "transition_record_paths": [],
        "phase_space_coordinate_ids": [],
        "phase_space_coordinate_paths": [],
        "limitations": ["Synthetic contract fixture only."],
    }
    bundle_path = write_json(root / "bundle.json", bundle)
    return [run_path, manifest_path, source_path, ledger_path, bundle_path]
