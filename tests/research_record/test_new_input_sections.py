from __future__ import annotations

from tools.research_record.compiler import compile_record

NOW = "2026-01-01T00:00:00+00:00"


def test_release_manifest_is_a_pure_passthrough(manifest_factory):
    manifest = manifest_factory(
        {"release_manifest": {"schema_version": "1.0.0", "repo": "NeuroTopology-Sim", "commit": "abc123", "branch": "main", "generated_at": "2026-01-01", "entries": [{"id": "x"}]}}
    )
    record = compile_record(manifest, now=NOW)
    rm = record["release_manifest"]
    assert rm["schema_version"] == "1.0.0"
    assert rm["commit"] == "abc123"
    assert rm["entries"] == [{"id": "x"}]


def test_scientific_gate_reports_feed_falsification_style_verdicts(manifest_factory):
    manifest = manifest_factory(
        {"scientific_gate_reports": {"gates": [{"gate_id": "HYP-GATE-1", "description": "threshold gate", "claim_class": "empirical", "data_mode": "empirical", "verdict": "FAIL"}]}}
    )
    record = compile_record(manifest, now=NOW)
    gate = record["scientific_gate_reports"]["gates"][0]
    assert gate["verdict"] == "FAIL"
    # empirical + FAIL -> classified as "empirical observation" (not formal,
    # since scientific_gate_reports carries no formal-metric distinction),
    # and empirical observation IS verdict-eligible, so FAIL surfaces.
    assert record["scientific_verdict"] == "FAIL"


def test_blocker_reports_are_merged_into_unresolved_blockers_with_origin(manifest_factory):
    manifest = manifest_factory({"blocker_reports": {"blockers": [{"blocker_id": "B-1", "description": "AWS credentials missing", "severity": "high", "source": "operator"}]}})
    record = compile_record(manifest, now=NOW)
    reported = [b for b in record["unresolved_blockers"] if b["kind"] == "reported_blocker"]
    assert len(reported) == 1
    assert reported[0]["origin"] == "reported"
    assert reported[0]["id"] == "B-1"
    assert any("B-1" in action for action in record["next_priorities"])


def test_artifact_references_are_recorded_but_never_read(manifest_factory, tmp_path):
    # A path that does not exist on disk must still be accepted -- this is
    # a *reference*, not a load.
    nonexistent = str(tmp_path / "does" / "not" / "exist.json")
    manifest = manifest_factory({"artifact_references": {"artifacts": [{"label": "missing artifact", "path": nonexistent, "kind": "contract"}]}})
    record = compile_record(manifest, now=NOW)
    artifact = record["artifact_references"]["artifacts"][0]
    assert artifact["path"] == nonexistent
    assert artifact["label"] == "missing artifact"


def test_artifact_entry_without_a_path_is_skipped_not_crashed(manifest_factory):
    manifest = manifest_factory({"artifact_references": {"artifacts": [{"label": "no path here"}]}})
    record = compile_record(manifest, now=NOW)
    assert record["artifact_references"]["artifacts"] == []
    assert record["completeness"]["artifact_references"]["available"] is True


def test_operator_notes_carry_declared_labels(manifest_factory):
    manifest = manifest_factory({"operator_notes": {"notes": [{"note": "topology pipeline needs a second reviewer", "epistemic_label": "hypothesis", "author": "operator"}]}})
    record = compile_record(manifest, now=NOW)
    assert record["operator_notes"]["notes"][0]["declared_epistemic_label"] == "hypothesis"
