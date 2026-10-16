"""Tests for DS005620 evidence packet exporter (P18.2 / O4)."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

_spec = importlib.util.spec_from_file_location(
    "export_ds005620_evidence_packet",
    Path(__file__).parent.parent.parent / "tools" / "export_ds005620_evidence_packet.py",
)
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)
build_evidence_packet = _mod.build_evidence_packet

_BANNED = [
    "proves consciousness", "consciousness proven", "soul proven",
    "afterlife proven", "liberation detected", "ontology solved",
    "ultimate reality", "q equals self", "q equals soul",
    "q_abs equals suffering", "f_dress equals karma",
    "sedated implies no_experience", "unresponsive implies unconscious",
    "topology proves liberation", "eeg proves consciousness",
]


def _setup_manifest(tmp_path: Path) -> Path:
    root = tmp_path / "execution"
    root.mkdir()
    (root / "ds005620_real_benchmark_execution.json").write_text(
        json.dumps({
            "benchmark_completed": True,
            "mode": "mock_e2e",
            "p12_succeeded": True,
            "p13_succeeded": True,
            "p11_succeeded": True,
        }),
        encoding="utf-8",
    )
    (root / "omega_event.json").write_text(
        json.dumps({
            "labels_inferred": False,
            "targets_fabricated": False,
            "source_contracts_modified": False,
            "legacy_mt_real_modified": False,
            "contracts_activated_by_executor": False,
            "p11_promotion_gate_modified": False,
            "consciousness_claims_made": False,
        }),
        encoding="utf-8",
    )
    manifest = {
        "dataset_id": "DS005620",
        "artifact_root": str(root),
        "artifact_count": 2,
        "artifacts": [],
        "safe_claim": "test",
    }
    manifest_path = root / "artifact_manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return manifest_path


def _setup_ontology_root(tmp_path: Path) -> Path:
    """Create a minimal ontology evaluation output directory."""
    ont = tmp_path / "ontology"
    ont.mkdir()
    (ont / "ontology_claim_evaluation.json").write_text(
        json.dumps({
            "max_claim_scope": "engineering_runtime",
            "promotion_state": "engineering_validated",
            "ontology_claim_status": "ontology_quarantined",
            "claims": [{"claim_id": "M1", "allowed": False, "blockers": ["b"]}],
            "blockers": ["run_mode_is_mock_e2e"],
            "safe_claim": "Ontology evaluation constrains claim scopes.",
        }),
        encoding="utf-8",
    )
    (ont / "ontology_promotion_decision.json").write_text(
        json.dumps({
            "ontology_promotion": False,
            "empirical_marker_promotion": False,
            "empirical_topology_promotion": False,
            "mechanism_promotion": False,
            "metaphysical_promotion": False,
        }),
        encoding="utf-8",
    )
    (ont / "bridge_claim_status.json").write_text(
        json.dumps({"bridge_statuses": [{"bridge_id": "B1", "status": "blocked_pending_real_execution"}]}),
        encoding="utf-8",
    )
    return ont


def _setup_metadata_inputs(
    tmp_path: Path,
    *,
    participant_rows: str = (
        "participant_id\texcluded\n"
        "sub-01\tFalse\n"
        "sub-02\tFalse\n"
        "sub-03\tTrue\n"
    ),
    published_counts: dict | None = None,
) -> Path:
    root = tmp_path / "metadata"
    root.mkdir()
    (root / "participants.tsv").write_text(participant_rows, encoding="utf-8")
    (root / "dataset_description.json").write_text(
        json.dumps({"Name": "fixture", "License": "CC0"}), encoding="utf-8"
    )
    (root / "README.txt").write_text(
        "This dataset is licensed under CC-BY-4.0.\n", encoding="utf-8"
    )
    (root / "nemar_metadata.json").write_text(
        json.dumps({
            "dataset_id": "on005620",
            "license": "CC0",
            "participants": 3,
            "tasks": ["awake", "sed", "sed2"],
        }),
        encoding="utf-8",
    )
    (root / "published_counts.json").write_text(
        json.dumps(published_counts or {"analyzed_participants": 2, "attempted_awakenings": 52}),
        encoding="utf-8",
    )
    return root


def _write_json(root: Path, filename: str, value: dict) -> None:
    (root / filename).write_text(json.dumps(value), encoding="utf-8")


def _write_preregistered_plan(root: Path, requirements=None, *, checksum=None) -> dict:
    variables = {"expected_task_requirements": requirements} if requirements is not None else {}
    plan = {
        "schema_version": "ExperimentPlan.v1",
        "plan_id": "plan-ds005620-fixture",
        "hypothesis_id": "hyp-ds005620-fixture",
        "domain": "metadata_reconciliation_fixture",
        "design_type": "metadata_only",
        "variables": variables,
        "target_sample_size": 20,
        "power_analysis": {"method": "not_applicable_to_fixture"},
        "analysis_protocol": "fixture-only; no EEG files are read",
        "data_source": "ds005620",
        "is_synthetic": False,
        "provenance": {
            "preregistration_reference": "https://osf.io/example",
            "registered_at": "2025-01-01T00:00:00Z",
            "authoritative_source_verified": True,
        },
    }
    plan["checksum"] = _mod.canonical_hash(plan) if checksum is None else checksum
    _write_json(root, "preregistered_plan.json", plan)
    return plan


def _write_inventory(root: Path, task_labels: list[str]) -> None:
    _write_json(
        root,
        "file_inventory.json",
        {
            "dataset_id": "ds005620",
            "eeg_candidates": [
                {
                    "subject_id": "sub-01",
                    "session_id": "01",
                    "task_label": task,
                    "run_id": "01",
                    "is_eeg_candidate": True,
                }
                for task in task_labels
            ],
        },
    )


# Original tests (preserved)

def test_evidence_packet_created(tmp_path):
    manifest_path = _setup_manifest(tmp_path)
    artifacts = build_evidence_packet(str(manifest_path), str(tmp_path / "out"))
    assert Path(artifacts["evidence_packet.json"]).exists()
    assert Path(artifacts["evidence_packet.md"]).exists()
    assert Path(artifacts["notion_import_payload.json"]).exists()


def test_evidence_packet_promotion_decision(tmp_path):
    manifest_path = _setup_manifest(tmp_path)
    artifacts = build_evidence_packet(str(manifest_path), str(tmp_path / "out"))
    packet = json.loads(Path(artifacts["evidence_packet.json"]).read_text(encoding="utf-8"))
    assert packet["promotion_decision"] == "engineering_runtime_validated_only"


def test_evidence_packet_all_omega_false(tmp_path):
    manifest_path = _setup_manifest(tmp_path)
    artifacts = build_evidence_packet(str(manifest_path), str(tmp_path / "out"))
    packet = json.loads(Path(artifacts["evidence_packet.json"]).read_text(encoding="utf-8"))
    assert packet["all_omega_invariants_false"] is True


def test_evidence_packet_no_banned_phrases(tmp_path):
    manifest_path = _setup_manifest(tmp_path)
    artifacts = build_evidence_packet(str(manifest_path), str(tmp_path / "out"))
    md_text = Path(artifacts["evidence_packet.md"]).read_text(encoding="utf-8").lower()
    for phrase in _BANNED:
        assert phrase not in md_text, f"banned phrase found in evidence_packet.md: {phrase!r}"


# New O4 tests

def test_evidence_packet_includes_ontology_summary_when_present(tmp_path):
    manifest_path = _setup_manifest(tmp_path)
    ont = _setup_ontology_root(tmp_path)
    artifacts = build_evidence_packet(str(manifest_path), str(tmp_path / "out"), ontology_root=str(ont))
    packet = json.loads(Path(artifacts["evidence_packet.json"]).read_text(encoding="utf-8"))
    assert "ontology_summary" in packet
    assert packet["ontology_summary"]["ontology_available"] is True
    assert packet["ontology_summary"]["max_claim_scope"] == "engineering_runtime"


def test_evidence_packet_ontology_summary_not_available_when_missing(tmp_path):
    manifest_path = _setup_manifest(tmp_path)
    artifacts = build_evidence_packet(str(manifest_path), str(tmp_path / "out"),
                                      ontology_root=str(tmp_path / "missing"))
    packet = json.loads(Path(artifacts["evidence_packet.json"]).read_text(encoding="utf-8"))
    assert packet["ontology_summary"]["ontology_available"] is False
    assert "ontology_evaluation_missing" in packet.get("warnings", [])


def test_evidence_packet_require_ontology_raises_when_missing(tmp_path):
    manifest_path = _setup_manifest(tmp_path)
    with pytest.raises(SystemExit):
        build_evidence_packet(str(manifest_path), str(tmp_path / "out"),
                              ontology_root=str(tmp_path / "missing"),
                              require_ontology=True)


def test_notion_payload_includes_ontology_fields(tmp_path):
    manifest_path = _setup_manifest(tmp_path)
    ont = _setup_ontology_root(tmp_path)
    artifacts = build_evidence_packet(str(manifest_path), str(tmp_path / "out"), ontology_root=str(ont))
    notion = json.loads(Path(artifacts["notion_import_payload.json"]).read_text(encoding="utf-8"))
    assert "ontology_claim_scope" in notion
    assert "ontology_promotion_state" in notion
    assert "ontology_status" in notion
    assert notion["ontology_status"] == "ontology_quarantined"


def test_evidence_markdown_includes_ontology_section(tmp_path):
    manifest_path = _setup_manifest(tmp_path)
    ont = _setup_ontology_root(tmp_path)
    artifacts = build_evidence_packet(str(manifest_path), str(tmp_path / "out"), ontology_root=str(ont))
    md = Path(artifacts["evidence_packet.md"]).read_text(encoding="utf-8")
    assert "## Ontology Claim Scope" in md


def test_mock_evidence_packet_does_not_promote_empirical_claims(tmp_path):
    manifest_path = _setup_manifest(tmp_path)
    ont = _setup_ontology_root(tmp_path)
    artifacts = build_evidence_packet(str(manifest_path), str(tmp_path / "out"), ontology_root=str(ont))
    packet = json.loads(Path(artifacts["evidence_packet.json"]).read_text(encoding="utf-8"))
    summary = packet["ontology_summary"]
    assert summary["empirical_marker_promotion"] is False
    assert summary["empirical_topology_promotion"] is False
    assert summary["mechanism_promotion"] is False
    assert summary["metaphysical_promotion"] is False
    assert summary["ontology_promotion"] is False


def test_claim_scope_dict_in_packet(tmp_path):
    manifest_path = _setup_manifest(tmp_path)
    artifacts = build_evidence_packet(str(manifest_path), str(tmp_path / "out"))
    packet = json.loads(Path(artifacts["evidence_packet.json"]).read_text(encoding="utf-8"))
    scope = packet.get("claim_scope", {})
    assert scope.get("engineering_runtime") is True
    assert scope.get("ontology_candidate") is False


def test_metadata_audit_keeps_cohort_license_and_task_authority_separate(tmp_path):
    manifest_path = _setup_manifest(tmp_path)
    metadata_root = _setup_metadata_inputs(tmp_path)
    artifacts = build_evidence_packet(
        str(manifest_path), str(tmp_path / "out"), metadata_root=str(metadata_root)
    )

    packet = json.loads(Path(artifacts["evidence_packet.json"]).read_text(encoding="utf-8"))
    audit = packet["metadata_reconciliation"]

    assert audit["metadata_parsed"] is True
    assert audit["participant_ids"] == ["sub-01", "sub-02", "sub-03"]
    assert audit["declared_excluded_ids"] == ["sub-03"]
    assert audit["published_counts"]["analyzed_participants"] == 2
    assert audit["cohort_reconciled"] is False
    assert audit["cohort_reconciliation_status"] == "unresolved_count_discrepancy_without_subject_mapping"
    assert audit["license_resolved"] is False
    assert audit["license_conflict"] is True
    assert audit["data_use_ready"] is False
    assert audit["file_inventory_complete_against_declared_requirements"] is None
    assert audit["expected_task_set"] is None


def test_metadata_audit_missing_root_keeps_source_claim_schema():
    audit = _mod._metadata_reconciliation(None)

    assert audit["metadata_parsed"] is False
    assert audit["published_count_source_claims"] is None


def test_metadata_audit_rejects_malformed_participants_tsv(tmp_path):
    metadata_root = _setup_metadata_inputs(tmp_path)
    (metadata_root / "participants.tsv").write_text(
        'participant_id\texcluded\n"sub-01\tFalse\n', encoding="utf-8"
    )

    audit = _mod._metadata_reconciliation(str(metadata_root))

    assert audit["metadata_parsed"] is False
    assert any(error.startswith("participants_tsv_invalid:") for error in audit["metadata_parse_errors"])


def test_metadata_audit_rejects_tsv_rows_with_missing_columns(tmp_path):
    metadata_root = _setup_metadata_inputs(tmp_path)
    (metadata_root / "participants.tsv").write_text(
        "participant_id\texcluded\nsub-01\n", encoding="utf-8"
    )

    audit = _mod._metadata_reconciliation(str(metadata_root))

    assert audit["metadata_parsed"] is False
    assert "participants_tsv_malformed_row:2" in audit["metadata_parse_errors"]


def test_metadata_audit_rejects_malformed_json(tmp_path):
    metadata_root = _setup_metadata_inputs(tmp_path)
    (metadata_root / "dataset_description.json").write_text('{"License":', encoding="utf-8")

    audit = _mod._metadata_reconciliation(str(metadata_root))

    assert audit["metadata_parsed"] is False
    assert "dataset_description_invalid_json:JSONDecodeError" in audit["metadata_parse_errors"]


def test_metadata_audit_rejects_duplicate_json_keys(tmp_path):
    metadata_root = _setup_metadata_inputs(tmp_path)
    (metadata_root / "dataset_description.json").write_text(
        '{"License":"CC0","License":"CC-BY-4.0"}', encoding="utf-8"
    )

    audit = _mod._metadata_reconciliation(str(metadata_root))

    assert audit["metadata_parsed"] is False
    assert "dataset_description_invalid_json:ValueError" in audit["metadata_parse_errors"]


def test_duplicate_subjects_invalidate_cohort_count_but_not_tsv_parsing(tmp_path):
    metadata_root = _setup_metadata_inputs(
        tmp_path,
        participant_rows="participant_id\texcluded\nsub-01\tFalse\nsub-01\tFalse\n",
    )

    audit = _mod._metadata_reconciliation(str(metadata_root))

    assert audit["metadata_parsed"] is True
    assert audit["participants_tsv_count"] is None
    assert "participants_tsv_duplicate_subject:sub-01" in audit["metadata_validation_errors"]
    assert audit["cohort_reconciled"] is None


def test_inventory_missing_declared_task_is_incomplete(tmp_path):
    metadata_root = _setup_metadata_inputs(tmp_path)
    _write_preregistered_plan(
        metadata_root,
        [{"task_label": "awake"}, {"task_label": "sed"}],
    )
    _write_inventory(metadata_root, ["awake"])

    audit = _mod._metadata_reconciliation(str(metadata_root))

    assert audit["expected_task_set"] == ["awake", "sed"]
    assert audit["task_session_run_coverage"]["missing_task_requirements"] == [
        {"task_label": "sed", "session_id": None, "run_id": None, "subject_id": None}
    ]
    assert audit["file_inventory_complete_against_declared_requirements"] is False


def test_inventory_task_absent_from_protocol_is_unexpected(tmp_path):
    metadata_root = _setup_metadata_inputs(tmp_path)
    _write_preregistered_plan(metadata_root, [{"task_label": "awake"}])
    _write_inventory(metadata_root, ["awake", "sed2"])

    audit = _mod._metadata_reconciliation(str(metadata_root))

    assert audit["expected_task_set"] == ["awake"]
    assert audit["task_session_run_coverage"]["unexpected_task_labels"] == ["sed2"]
    assert audit["file_inventory_complete_against_declared_requirements"] is False


def test_inventory_does_not_define_tasks_without_declared_protocol(tmp_path):
    metadata_root = _setup_metadata_inputs(tmp_path)
    _write_inventory(metadata_root, ["awake", "sed", "sed2"])

    audit = _mod._metadata_reconciliation(str(metadata_root))

    assert audit["expected_task_set"] is None
    assert audit["task_session_run_coverage"]["status"] == "not_evaluable_without_verified_protocol"
    assert audit["file_inventory_complete_against_declared_requirements"] is None


def test_missing_task_requirements_in_plan_do_not_use_observed_tasks(tmp_path):
    metadata_root = _setup_metadata_inputs(tmp_path)
    _write_preregistered_plan(metadata_root)
    _write_inventory(metadata_root, ["awake", "sed", "sed2"])

    audit = _mod._metadata_reconciliation(str(metadata_root))

    assert audit["preregistration"]["status"] == "requirements_missing_or_invalid"
    assert "expected_task_requirements_missing" in audit["preregistration"]["errors"]
    assert audit["expected_task_set"] is None
    assert audit["file_inventory_complete_against_declared_requirements"] is None


def test_empty_bytes_sha256_is_not_valid_preregistration_provenance(tmp_path):
    metadata_root = _setup_metadata_inputs(tmp_path)
    _write_preregistered_plan(
        metadata_root,
        [{"task_label": "awake"}],
        checksum="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    )

    audit = _mod._metadata_reconciliation(str(metadata_root))

    assert audit["preregistration"]["plan_integrity_verified"] is False
    assert audit["preregistration"]["status"] == "invalid"
    assert "empty_bytes_sha256_is_not_plan_provenance" in audit["preregistration"]["errors"]
    assert audit["expected_task_set"] is None


def test_empty_source_checksum_cannot_authorize_task_requirements(tmp_path):
    metadata_root = _setup_metadata_inputs(tmp_path)
    plan = _write_preregistered_plan(metadata_root, [{"task_label": "awake"}])
    plan["provenance"]["source_checksum"] = (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )
    plan["checksum"] = _mod.canonical_hash(
        {key: value for key, value in plan.items() if key != "checksum"}
    )
    _write_json(metadata_root, "preregistered_plan.json", plan)

    audit = _mod._metadata_reconciliation(str(metadata_root))

    assert audit["preregistration"]["plan_integrity_verified"] is True
    assert audit["preregistration"]["status"] != "verified"
    assert "empty_bytes_sha256_is_not_plan_provenance" in audit["preregistration"]["errors"]
    assert audit["expected_task_set"] is None


def test_license_conflict_blocks_data_use_readiness(tmp_path):
    metadata_root = _setup_metadata_inputs(tmp_path)

    audit = _mod._metadata_reconciliation(str(metadata_root))

    assert audit["license_declarations"] == {
        "dataset_description": "CC0",
        "readme": "CC-BY-4.0",
        "nemar": "CC0",
    }
    assert audit["license_conflict"] is True
    assert audit["license_resolved"] is False
    assert audit["data_use_ready"] is False
    assert "license_conflict" in audit["data_use_readiness_blockers"]


def test_count_discrepancy_does_not_assign_excluded_id_to_published_cohort(tmp_path):
    participant_rows = "participant_id\texcluded\n" + "".join(
        f"sub-{index:02d}\t{'True' if index == 21 else 'False'}\n"
        for index in range(1, 22)
    )
    metadata_root = _setup_metadata_inputs(
        tmp_path,
        participant_rows=participant_rows,
        published_counts={
            "bids_subjects": 21,
            "analyzed_participants": 20,
            "attempted_awakenings": 52,
        },
    )

    audit = _mod._metadata_reconciliation(str(metadata_root))

    assert audit["participants_tsv_count"] == 21
    assert audit["published_counts"]["analyzed_participants"] == 20
    assert audit["participant_count_difference"] == 1
    assert audit["declared_excluded_ids"] == ["sub-21"]
    assert audit["subject_level_analysis_ids_supplied"] is False
    assert audit["cohort_reconciled"] is False
    assert audit["cohort_reconciliation_status"] == "unresolved_count_discrepancy_without_subject_mapping"


def test_subject_id_list_must_match_explicit_exclusion_flags(tmp_path):
    metadata_root = _setup_metadata_inputs(
        tmp_path,
        participant_rows=(
            "participant_id\texcluded\n"
            "sub-01\tFalse\n"
            "sub-02\tFalse\n"
            "sub-03\tFalse\n"
        ),
        published_counts={
            "analyzed_participants": 2,
            "analyzed_subject_ids": ["sub-01", "sub-02"],
            "attempted_awakenings": 52,
        },
    )

    audit = _mod._metadata_reconciliation(str(metadata_root))

    assert audit["subject_level_analysis_ids_supplied"] is True
    assert audit["cohort_reconciled"] is False
    assert audit["cohort_reconciliation_status"] == "unresolved"


def test_matching_inventory_requires_a_verified_nonempty_plan_and_is_deterministic(tmp_path):
    metadata_root = _setup_metadata_inputs(tmp_path)
    _write_preregistered_plan(
        metadata_root,
        [{"task_label": "awake"}, {"task_label": "sed"}],
    )
    _write_inventory(metadata_root, ["awake", "sed"])

    first = _mod._metadata_reconciliation(str(metadata_root))
    second = _mod._metadata_reconciliation(str(metadata_root))

    assert first == second
    assert first["preregistration"]["plan_integrity_verified"] is True
    assert first["preregistration"]["status"] == "verified"
    assert first["file_inventory_complete_against_declared_requirements"] is True
    assert first["task_session_run_coverage"]["observed_task_session_run_coverage"] == [
        {"task_label": "awake", "session_id": "01", "run_id": "01"},
        {"task_label": "sed", "session_id": "01", "run_id": "01"},
    ]


def test_complete_metadata_packet_is_not_empirical_evidence_or_data_permission(tmp_path):
    manifest_path = _setup_manifest(tmp_path)
    metadata_root = _setup_metadata_inputs(
        tmp_path,
        published_counts={
            "bids_subjects": 3,
            "analyzed_participants": 2,
            "analyzed_subject_ids": ["sub-01", "sub-02"],
            "attempted_awakenings": 52,
        },
    )
    (metadata_root / "README.txt").write_text(
        "This dataset is licensed under CC0.\n", encoding="utf-8"
    )
    _write_preregistered_plan(metadata_root, [{"task_label": "awake"}])
    _write_inventory(metadata_root, ["awake"])

    artifacts = build_evidence_packet(
        str(manifest_path), str(tmp_path / "out"), metadata_root=str(metadata_root)
    )
    packet = json.loads(Path(artifacts["evidence_packet.json"]).read_text(encoding="utf-8"))
    audit = packet["metadata_reconciliation"]

    assert audit["metadata_parsed"] is True
    assert audit["cohort_reconciled"] is True
    assert audit["license_resolved"] is True
    assert audit["file_inventory_complete_against_declared_requirements"] is True
    assert audit["data_use_ready"] is False
    assert packet["metadata_is_empirical_evidence"] is False
    assert packet["participant_eeg_data_downloaded_or_analyzed"] is False


def test_metadata_snapshot_keeps_published_and_source_counts_separate():
    fixture_root = Path(__file__).parent.parent / "fixtures" / "ds005620_metadata_snapshot"

    audit = _mod._metadata_reconciliation(str(fixture_root))

    assert audit["metadata_parsed"] is True
    assert audit["participants_tsv_count"] == 21
    assert audit["participant_ids"][0] == "sub-SD_1010"
    assert audit["participant_ids"][-1] == "sub-SD_1074"
    assert len(audit["participant_ids"]) == 21
    assert audit["declared_excluded_ids"] == ["sub-SD_1037"]
    assert audit["source_metadata"]["nemar"]["participants"] == 21
    assert audit["source_metadata"]["nemar"]["reported_tasks"] == ["awake", "sed", "sed2"]
    assert audit["published_counts"]["bids_subjects"] == 21
    assert audit["bids_subject_count_match"] is True
    assert audit["nemar_participant_count_match"] is True
    assert audit["published_counts"]["analyzed_participants"] == 20
    assert audit["published_counts"]["attempted_awakenings"] == 52
    assert audit["participant_count_difference"] == 1
    assert audit["published_count_source_claims"] == {
        "proposal": {
            "bids_subjects": 21,
            "analyzed_participants": 20,
            "awakening_trials": 52,
        },
        "primary_paper": {
            "recorded_participants": 20,
            "attempted_awakenings": 52,
        },
    }
    assert audit["cohort_reconciled"] is False
    assert audit["subject_level_analysis_ids_supplied"] is False
    assert audit["license_conflict"] is True
    assert audit["license_resolved"] is False
    assert audit["data_use_ready"] is False
    assert audit["task_session_run_coverage"]["status"] == "not_supplied"
    assert audit["expected_task_set"] is None
