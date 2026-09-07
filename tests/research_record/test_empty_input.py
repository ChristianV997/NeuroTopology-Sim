from __future__ import annotations

import json

from tools.research_record.compiler import compile_record

NOW = "2026-01-01T00:00:00+00:00"


def test_empty_but_present_input_compiles_to_a_complete_empty_record(manifest_factory):
    """Every section present but empty (the manifest_factory defaults) --
    distinct from partial_record's *missing* sections."""
    manifest = manifest_factory({})

    record = compile_record(manifest, now=NOW)

    assert record["status"] == "complete"
    assert record["pr_state"]["pull_requests"] == []
    assert record["agent_contribution_table"]["contributions"] == []
    assert record["falsification_semantics"]["results"] == []
    assert record["topology_readiness"]["checks"] == []
    assert record["release_manifest"]["entries"] == []
    assert record["scientific_gate_reports"]["gates"] == []
    assert record["blocker_reports"]["blockers"] == []
    assert record["artifact_references"]["artifacts"] == []
    assert record["operator_notes"]["notes"] == []
    assert record["unresolved_blockers"] == []
    assert record["conflicts"] == []
    assert record["scientific_verdict"] == "NOT_APPLICABLE"
    assert record["final_release_recommendation"] == "READY_FOR_REVIEW"
    # Still fully JSON-serializable with nothing null-unsafe.
    json.dumps(record, allow_nan=False)


def test_manifest_pointing_at_nothing_is_partial(tmp_path):
    """An empty manifest (no keys at all) -- every section is "not_provided"."""
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text("{}", encoding="utf-8")

    record = compile_record(manifest_path, now=NOW)

    assert record["status"] == "partial"
    assert all(v["error"] == "not_provided" for v in record["completeness"].values())
    assert record["final_release_recommendation"] == "INCOMPLETE_EVIDENCE"
