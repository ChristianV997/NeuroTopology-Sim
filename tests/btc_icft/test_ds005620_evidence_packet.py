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


def _artifact_path(output_dir: Path, artifacts: dict[str, str], name: str) -> Path:
    return Path(output_dir) / artifacts[name]


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
        "SYNTHETIC_PARTICIPANT_001\tFalse\n"
        "SYNTHETIC_PARTICIPANT_002\tFalse\n"
        "SYNTHETIC_PARTICIPANT_003\tTrue\n"
    ),
    published_counts: dict | None = None,
) -> Path:
    root = tmp_path / "metadata"
    root.mkdir()
    (root / "participants.tsv").write_text(participant_rows, encoding="utf-8")
    (root / "dataset_description.json").write_text(
        json.dumps({"Name": "fixture", "License": "TEST-LICENSE-A"}), encoding="utf-8"
    )
    (root / "README.txt").write_text(
        "This synthetic fixture is licensed under TEST-LICENSE-B.\n", encoding="utf-8"
    )
    (root / "nemar_metadata.json").write_text(
        json.dumps({
            "dataset_id": "synthetic-dataset",
            "license": "TEST-LICENSE-A",
            "participants": 3,
            "tasks": ["task_alpha", "task_beta", "task_gamma"],
        }),
        encoding="utf-8",
    )
    (root / "published_counts.json").write_text(
        json.dumps(published_counts or {"analyzed_participants": 2, "attempted_awakenings": 7}),
        encoding="utf-8",
    )
    return root


def _write_json(root: Path, filename: str, value: dict) -> None:
    (root / filename).write_text(json.dumps(value), encoding="utf-8")


def _write_preregistered_plan(root: Path, requirements=None, *, checksum=None) -> dict:
    variables = {"expected_task_requirements": requirements} if requirements is not None else {}
    plan = {
        "schema_version": "ExperimentPlan.v1",
        "plan_id": "plan-synthetic-fixture",
        "hypothesis_id": "hyp-synthetic-fixture",
        "domain": "synthetic_metadata_reconciliation",
        "design_type": "metadata_only",
        "variables": variables,
        "target_sample_size": 3,
        "power_analysis": {"method": "not_applicable_to_fixture"},
        "analysis_protocol": "synthetic fixture only; no EEG files are read",
        "data_source": "synthetic-fixture",
        "is_synthetic": True,
        "provenance": {
            "preregistration_reference": None,
            "registered_at": None,
            "authoritative_source_verified": False,
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
                    "subject_id": "SYNTHETIC_PARTICIPANT_001",
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
    assert _artifact_path(tmp_path / "out", artifacts, "evidence_packet.json").exists()
    assert _artifact_path(tmp_path / "out", artifacts, "evidence_packet.md").exists()
    assert _artifact_path(tmp_path / "out", artifacts, "notion_import_payload.json").exists()


def test_evidence_packet_payload_is_deterministic_except_generated_at(tmp_path):
    manifest_path = _setup_manifest(tmp_path)
    first_paths = build_evidence_packet(str(manifest_path), str(tmp_path / "out-first"))
    second_paths = build_evidence_packet(str(manifest_path), str(tmp_path / "out-second"))

    first_packet = json.loads(
        (tmp_path / "out-first" / first_paths["evidence_packet.json"]).read_text(encoding="utf-8")
    )
    second_packet = json.loads(
        (tmp_path / "out-second" / second_paths["evidence_packet.json"]).read_text(encoding="utf-8")
    )
    first_packet.pop("generated_at")
    second_packet.pop("generated_at")
    assert first_packet == second_packet
    for name in ("evidence_packet.md", "notion_import_payload.json"):
        first = (tmp_path / "out-first" / first_paths[name]).read_text(encoding="utf-8")
        second = (tmp_path / "out-second" / second_paths[name]).read_text(encoding="utf-8")
        assert first == second


def test_evidence_packet_promotion_decision(tmp_path):
    manifest_path = _setup_manifest(tmp_path)
    artifacts = build_evidence_packet(str(manifest_path), str(tmp_path / "out"))
    packet = json.loads(_artifact_path(tmp_path / "out", artifacts, "evidence_packet.json").read_text(encoding="utf-8"))
    assert packet["promotion_decision"] == "engineering_runtime_validated_only"


def test_evidence_packet_all_omega_false(tmp_path):
    manifest_path = _setup_manifest(tmp_path)
    artifacts = build_evidence_packet(str(manifest_path), str(tmp_path / "out"))
    packet = json.loads(_artifact_path(tmp_path / "out", artifacts, "evidence_packet.json").read_text(encoding="utf-8"))
    assert packet["all_omega_invariants_false"] is True


def test_evidence_packet_no_banned_phrases(tmp_path):
    manifest_path = _setup_manifest(tmp_path)
    artifacts = build_evidence_packet(str(manifest_path), str(tmp_path / "out"))
    md_text = _artifact_path(tmp_path / "out", artifacts, "evidence_packet.md").read_text(encoding="utf-8").lower()
    for phrase in _BANNED:
        assert phrase not in md_text, f"banned phrase found in evidence_packet.md: {phrase!r}"


# New O4 tests

def test_evidence_packet_includes_ontology_summary_when_present(tmp_path):
    manifest_path = _setup_manifest(tmp_path)
    ont = _setup_ontology_root(tmp_path)
    artifacts = build_evidence_packet(str(manifest_path), str(tmp_path / "out"), ontology_root=str(ont))
    packet = json.loads(_artifact_path(tmp_path / "out", artifacts, "evidence_packet.json").read_text(encoding="utf-8"))
    assert "ontology_summary" in packet
    assert packet["ontology_summary"]["ontology_available"] is True
    assert packet["ontology_summary"]["max_claim_scope"] == "engineering_runtime"


def test_evidence_packet_ontology_summary_not_available_when_missing(tmp_path):
    manifest_path = _setup_manifest(tmp_path)
    artifacts = build_evidence_packet(str(manifest_path), str(tmp_path / "out"),
                                      ontology_root=str(tmp_path / "missing"))
    packet = json.loads(_artifact_path(tmp_path / "out", artifacts, "evidence_packet.json").read_text(encoding="utf-8"))
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
    notion = json.loads(_artifact_path(tmp_path / "out", artifacts, "notion_import_payload.json").read_text(encoding="utf-8"))
    assert "ontology_claim_scope" in notion
    assert "ontology_promotion_state" in notion
    assert "ontology_status" in notion
    assert notion["ontology_status"] == "ontology_quarantined"


def test_evidence_markdown_includes_ontology_section(tmp_path):
    manifest_path = _setup_manifest(tmp_path)
    ont = _setup_ontology_root(tmp_path)
    artifacts = build_evidence_packet(str(manifest_path), str(tmp_path / "out"), ontology_root=str(ont))
    md = _artifact_path(tmp_path / "out", artifacts, "evidence_packet.md").read_text(encoding="utf-8")
    assert "## Ontology Claim Scope" in md


def test_mock_evidence_packet_does_not_promote_empirical_claims(tmp_path):
    manifest_path = _setup_manifest(tmp_path)
    ont = _setup_ontology_root(tmp_path)
    artifacts = build_evidence_packet(str(manifest_path), str(tmp_path / "out"), ontology_root=str(ont))
    packet = json.loads(_artifact_path(tmp_path / "out", artifacts, "evidence_packet.json").read_text(encoding="utf-8"))
    summary = packet["ontology_summary"]
    assert summary["empirical_marker_promotion"] is False
    assert summary["empirical_topology_promotion"] is False
    assert summary["mechanism_promotion"] is False
    assert summary["metaphysical_promotion"] is False
    assert summary["ontology_promotion"] is False


def test_claim_scope_dict_in_packet(tmp_path):
    manifest_path = _setup_manifest(tmp_path)
    artifacts = build_evidence_packet(str(manifest_path), str(tmp_path / "out"))
    packet = json.loads(_artifact_path(tmp_path / "out", artifacts, "evidence_packet.json").read_text(encoding="utf-8"))
    scope = packet.get("claim_scope", {})
    assert scope.get("engineering_runtime") is True
    assert scope.get("ontology_candidate") is False


def test_metadata_audit_keeps_cohort_license_and_task_authority_separate(tmp_path):
    manifest_path = _setup_manifest(tmp_path)
    metadata_root = _setup_metadata_inputs(tmp_path)
    artifacts = build_evidence_packet(
        str(manifest_path), str(tmp_path / "out"), metadata_root=str(metadata_root)
    )

    packet = json.loads(_artifact_path(tmp_path / "out", artifacts, "evidence_packet.json").read_text(encoding="utf-8"))
    audit = packet["metadata_reconciliation"]

    assert audit["metadata_parsed"] is True
    assert audit["participants_tsv_count"] == 3
    assert audit["excluded_participant_count"] == 1
    assert "participant_ids" not in audit
    assert "declared_excluded_ids" not in audit
    assert audit["published_counts"]["analyzed_participants"] == 2
    assert audit["cohort_count_consistent"] is True
    assert audit["cohort_reconciliation_status"] == "count_consistent_identity_unverified"
    assert audit["license_declarations_consistent"] is False
    assert audit["license_conflict"] is True
    assert audit["data_use_ready"] is False
    assert audit["file_inventory_complete_against_declared_requirements"] is None
    assert audit["expected_task_count"] is None


def test_metadata_audit_missing_root_keeps_source_claim_schema():
    audit = _mod._metadata_reconciliation(None)

    assert audit["metadata_parsed"] is False
    assert audit["published_count_source_claims_supplied"] is False
    assert audit["published_count_source_claim_count"] is None


def test_metadata_audit_rejects_malformed_participants_tsv(tmp_path):
    metadata_root = _setup_metadata_inputs(tmp_path)
    (metadata_root / "participants.tsv").write_text(
        'participant_id\texcluded\n"SYNTHETIC_PARTICIPANT_001\tFalse\n', encoding="utf-8"
    )

    audit = _mod._metadata_reconciliation(str(metadata_root))

    assert audit["metadata_parsed"] is False
    assert any(error.startswith("participants_tsv_invalid:") for error in audit["metadata_parse_errors"])


def test_metadata_audit_rejects_tsv_rows_with_missing_columns(tmp_path):
    metadata_root = _setup_metadata_inputs(tmp_path)
    (metadata_root / "participants.tsv").write_text(
        "participant_id\texcluded\nSYNTHETIC_PARTICIPANT_001\n", encoding="utf-8"
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
    marker = "SYNTHETIC_RAW_ID_LEAK_MARKER_JSON_KEY_4A7D"
    (metadata_root / "dataset_description.json").write_text(
        f'{{"{marker}":"one","padding":true,"{marker}":"two"}}', encoding="utf-8"
    )

    audit = _mod._metadata_reconciliation(str(metadata_root))

    assert audit["metadata_parsed"] is False
    assert "dataset_description_invalid_json:ValueError" in audit["metadata_parse_errors"]
    assert marker not in json.dumps(audit)


def test_duplicate_subjects_are_rejected_without_echoing_identifiers(tmp_path):
    metadata_root = _setup_metadata_inputs(
        tmp_path,
        participant_rows="participant_id\texcluded\nSYNTHETIC_PARTICIPANT_001\tFalse\nSYNTHETIC_PARTICIPANT_001\tFalse\n",
    )

    audit = _mod._metadata_reconciliation(str(metadata_root))

    assert audit["metadata_parsed"] is False
    assert audit["metadata_parse_errors"] == []
    assert audit["participants_tsv_count"] is None
    assert "participants_tsv_duplicate_subject:row:3" in audit["metadata_validation_errors"]
    assert "SYNTHETIC_PARTICIPANT_001" not in json.dumps(audit)
    assert audit["cohort_count_consistent"] is None


def test_inventory_missing_declared_task_is_incomplete(tmp_path):
    metadata_root = _setup_metadata_inputs(tmp_path)
    _write_preregistered_plan(
        metadata_root,
        [{"task_label": "task_alpha"}, {"task_label": "task_beta"}],
    )
    _write_inventory(metadata_root, ["task_alpha"])

    audit = _mod._metadata_reconciliation(str(metadata_root))

    assert audit["expected_task_count"] == 2
    assert audit["task_session_run_coverage"]["missing_task_requirement_count"] == 1
    assert audit["file_inventory_complete_against_declared_requirements"] is False


def test_inventory_task_absent_from_protocol_is_unexpected(tmp_path):
    metadata_root = _setup_metadata_inputs(tmp_path)
    _write_preregistered_plan(metadata_root, [{"task_label": "task_alpha"}])
    _write_inventory(metadata_root, ["task_alpha", "task_gamma"])

    audit = _mod._metadata_reconciliation(str(metadata_root))

    assert audit["expected_task_count"] == 1
    assert audit["task_session_run_coverage"]["unexpected_task_label_count"] == 1
    assert audit["file_inventory_complete_against_declared_requirements"] is False


def test_inventory_does_not_define_tasks_without_declared_protocol(tmp_path):
    metadata_root = _setup_metadata_inputs(tmp_path)
    _write_inventory(metadata_root, ["task_alpha", "task_beta", "task_gamma"])

    audit = _mod._metadata_reconciliation(str(metadata_root))

    assert audit["expected_task_count"] is None
    assert audit["task_session_run_coverage"]["status"] == "not_evaluable_without_verified_protocol"
    assert audit["file_inventory_complete_against_declared_requirements"] is None


def test_missing_task_requirements_in_plan_do_not_use_observed_tasks(tmp_path):
    metadata_root = _setup_metadata_inputs(tmp_path)
    _write_preregistered_plan(metadata_root)
    _write_inventory(metadata_root, ["task_alpha", "task_beta", "task_gamma"])

    audit = _mod._metadata_reconciliation(str(metadata_root))

    assert audit["preregistration"]["status"] == "requirements_missing_or_invalid"
    assert "expected_task_requirements_missing" in audit["preregistration"]["errors"]
    assert audit["expected_task_count"] is None
    assert audit["file_inventory_complete_against_declared_requirements"] is None


def test_empty_bytes_sha256_is_not_valid_preregistration_provenance(tmp_path):
    metadata_root = _setup_metadata_inputs(tmp_path)
    _write_preregistered_plan(
        metadata_root,
        [{"task_label": "task_alpha"}],
        checksum="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    )

    audit = _mod._metadata_reconciliation(str(metadata_root))

    assert audit["preregistration"]["plan_integrity_verified"] is False
    assert audit["preregistration"]["status"] == "invalid"
    assert "empty_bytes_sha256_is_not_plan_provenance" in audit["preregistration"]["errors"]
    assert audit["expected_task_count"] is None


def test_empty_source_checksum_cannot_authorize_task_requirements(tmp_path):
    metadata_root = _setup_metadata_inputs(tmp_path)
    plan = _write_preregistered_plan(metadata_root, [{"task_label": "task_alpha"}])
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
    assert audit["expected_task_count"] is None


def test_license_conflict_blocks_data_use_readiness(tmp_path):
    metadata_root = _setup_metadata_inputs(tmp_path)

    audit = _mod._metadata_reconciliation(str(metadata_root))

    assert audit["license_declarations"] == {
        "dataset_description_supplied": True,
        "readme_supplied": True,
        "nemar_supplied": True,
    }
    assert audit["license_conflict"] is True
    assert audit["license_declarations_consistent"] is False
    assert audit["data_use_ready"] is False
    assert "license_conflict" in audit["data_use_readiness_blockers"]


def test_count_discrepancy_does_not_claim_cohort_identity(tmp_path):
    participant_rows = "participant_id\texcluded\n" + "".join(
        f"SYNTHETIC_PARTICIPANT_{index:02d}\t{'True' if index == 4 else 'False'}\n"
        for index in range(1, 5)
    )
    metadata_root = _setup_metadata_inputs(
        tmp_path,
        participant_rows=participant_rows,
        published_counts={
            "bids_subjects": 4,
            "analyzed_participants": 2,
            "attempted_awakenings": 7,
        },
    )

    audit = _mod._metadata_reconciliation(str(metadata_root))

    assert audit["participants_tsv_count"] == 4
    assert audit["published_counts"]["analyzed_participants"] == 2
    assert audit["participant_count_difference"] == 2
    assert audit["excluded_participant_count"] == 1
    assert audit["analysis_identifier_list_supplied"] is False
    assert audit["cohort_count_consistent"] is False
    assert audit["cohort_reconciliation_status"] == "count_discrepancy_identity_unverified"


def test_subject_id_list_is_only_used_for_aggregate_count_check(tmp_path):
    metadata_root = _setup_metadata_inputs(
        tmp_path,
        participant_rows=(
            "participant_id\texcluded\n"
            "SYNTHETIC_PARTICIPANT_001\tFalse\n"
            "SYNTHETIC_PARTICIPANT_002\tFalse\n"
            "SYNTHETIC_PARTICIPANT_003\tFalse\n"
        ),
        published_counts={
            "analyzed_participants": 2,
            "analyzed_subject_ids": ["SYNTHETIC_PARTICIPANT_001", "SYNTHETIC_PARTICIPANT_002"],
            "attempted_awakenings": 7,
        },
    )

    audit = _mod._metadata_reconciliation(str(metadata_root))

    assert audit["analysis_identifier_list_supplied"] is True
    assert audit["analysis_identifier_count"] == 2
    assert audit["cohort_count_consistent"] is False
    assert audit["cohort_reconciliation_status"] == "count_discrepancy_identity_unverified"


def test_synthetic_inventory_check_is_demo_only_and_deterministic(tmp_path):
    metadata_root = _setup_metadata_inputs(tmp_path)
    _write_preregistered_plan(
        metadata_root,
        [{"task_label": "task_alpha"}, {"task_label": "task_beta"}],
    )
    _write_inventory(metadata_root, ["task_alpha", "task_beta"])

    first = _mod._metadata_reconciliation(str(metadata_root))
    second = _mod._metadata_reconciliation(str(metadata_root))

    assert first == second
    assert first["preregistration"]["plan_integrity_verified"] is True
    assert first["preregistration"]["status"] == "synthetic_demo_only"
    assert first["preregistration"]["authority_asserted"] is False
    assert first["file_inventory_complete_against_declared_requirements"] is True
    assert first["task_session_run_coverage"]["observed_task_session_run_coverage_count"] == 2
    assert first["task_session_run_coverage"]["status"] == "complete_against_declared_requirements_synthetic_demo_only"


def test_complete_metadata_packet_is_not_empirical_evidence_or_data_permission(tmp_path):
    manifest_path = _setup_manifest(tmp_path)
    metadata_root = _setup_metadata_inputs(
        tmp_path,
        published_counts={
            "bids_subjects": 3,
            "analyzed_participants": 2,
            "analyzed_subject_ids": ["SYNTHETIC_PARTICIPANT_001", "SYNTHETIC_PARTICIPANT_002"],
            "attempted_awakenings": 7,
        },
    )
    (metadata_root / "README.txt").write_text(
        "This synthetic fixture is licensed under TEST-LICENSE-A.\n", encoding="utf-8"
    )
    _write_preregistered_plan(metadata_root, [{"task_label": "task_alpha"}])
    _write_inventory(metadata_root, ["task_alpha"])

    artifacts = build_evidence_packet(
        str(manifest_path), str(tmp_path / "out"), metadata_root=str(metadata_root)
    )
    packet = json.loads(_artifact_path(tmp_path / "out", artifacts, "evidence_packet.json").read_text(encoding="utf-8"))
    audit = packet["metadata_reconciliation"]

    assert audit["metadata_parsed"] is True
    assert audit["cohort_count_consistent"] is True
    assert audit["license_declarations_consistent"] is True
    assert audit["file_inventory_complete_against_declared_requirements"] is True
    assert audit["data_use_ready"] is False
    assert packet["metadata_is_empirical_evidence"] is False
    assert packet["participant_eeg_data_downloaded_or_analyzed"] is False


def test_generated_metadata_fixture_keeps_aggregate_counts_only(tmp_path):
    marker_a = "SYNTHETIC_RAW_ID_LEAK_MARKER_ALPHA_5D2C"
    marker_b = "SYNTHETIC_RAW_ID_LEAK_MARKER_EXCLUDED_8A41"
    rows = (
        "participant_id\texcluded\n"
        f"{marker_a}\tFalse\n"
        f"{marker_b}\tTrue\n"
        "SYNTHETIC_PARTICIPANT_GAMMA\tFalse\n"
    )
    metadata_root = _setup_metadata_inputs(
        tmp_path,
        participant_rows=rows,
        published_counts={
            "bids_subjects": 3,
            "analyzed_participants": 2,
            "analyzed_subject_ids": [marker_a, "SYNTHETIC_PARTICIPANT_GAMMA"],
            "attempted_awakenings": 7,
            "source_claims": {marker_a: {"participant": marker_b}},
        },
    )
    _write_preregistered_plan(
        metadata_root,
        [{"task_label": "task_alpha", "subject_id": marker_a}],
    )
    _write_inventory(metadata_root, ["task_alpha"])

    first = _mod._metadata_reconciliation(str(metadata_root))
    second = _mod._metadata_reconciliation(str(metadata_root))
    serialized = json.dumps(first, sort_keys=True)

    assert first == second
    assert first["participants_tsv_count"] == 3
    assert first["excluded_participant_count"] == 1
    assert first["published_count_source_claim_count"] == 1
    assert first["cohort_reconciliation_status"] == "count_consistent_identity_unverified"
    assert first["data_use_ready"] is False
    assert "participant_ids" not in first
    assert "declared_excluded_ids" not in first
    assert "metadata_file_sha256" not in first
    assert marker_a not in serialized
    assert marker_b not in serialized


def test_identifier_markers_never_leak_to_packet_logs_or_errors(tmp_path, capsys):
    marker_a = "SYNTHETIC_RAW_ID_LEAK_MARKER_ALPHA_5D2C"
    marker_b = "SYNTHETIC_RAW_ID_LEAK_MARKER_EXCLUDED_8A41"
    manifest_path = _setup_manifest(tmp_path)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["nested_participant_metadata"] = {marker_a: marker_b}
    _write_json(manifest_path.parent, manifest_path.name, manifest)
    execution_path = manifest_path.parent / "ds005620_real_benchmark_execution.json"
    execution = json.loads(execution_path.read_text(encoding="utf-8"))
    execution["mode"] = marker_a
    execution["unrecognized_nested_metadata"] = [marker_b]
    execution_path.write_text(json.dumps(execution), encoding="utf-8")
    metadata_root = _setup_metadata_inputs(
        tmp_path,
        participant_rows=(
            "participant_id\texcluded\n"
            f"{marker_a}\tFalse\n"
            f"{marker_b}\tTrue\n"
            "SYNTHETIC_PARTICIPANT_GAMMA\tFalse\n"
        ),
        published_counts={
            "bids_subjects": 3,
            "analyzed_participants": 2,
            "analyzed_subject_ids": [marker_a, "SYNTHETIC_PARTICIPANT_GAMMA"],
            "attempted_awakenings": 7,
            "source_claims": {marker_a: {"nested": {"participant_id": marker_b}}},
        },
    )
    _write_json(metadata_root, "dataset_description.json", {"Name": marker_a, "License": marker_b})
    (metadata_root / "README.txt").write_text(
        f"This synthetic fixture is licensed under {marker_a}.\n", encoding="utf-8"
    )
    _write_json(
        metadata_root,
        "nemar_metadata.json",
        {"dataset_id": marker_a, "participants": 3, "tasks": [marker_b], "license": marker_b},
    )
    plan = _write_preregistered_plan(
        metadata_root,
        [{"task_label": marker_a, "session_id": marker_b, "run_id": marker_a, "subject_id": marker_b}],
    )
    plan["provenance"]["preregistration_reference"] = f"https://example.invalid/{marker_a}"
    plan["checksum"] = _mod.canonical_hash({key: value for key, value in plan.items() if key != "checksum"})
    _write_json(metadata_root, "preregistered_plan.json", plan)
    _write_json(
        metadata_root,
        "file_inventory.json",
        {"eeg_candidates": [{"subject_id": marker_a, "session_id": marker_b,
                             "task_label": marker_a, "run_id": marker_b,
                             "is_eeg_candidate": True}]},
    )
    ontology_root = _setup_ontology_root(tmp_path)
    _write_json(
        ontology_root,
        "ontology_claim_evaluation.json",
        {"max_claim_scope": marker_a, "promotion_state": marker_b,
         "ontology_claim_status": marker_a, "claims": [{"claim_id": marker_b, "allowed": False}],
         "blockers": [marker_a], "safe_claim": marker_b},
    )
    _write_json(
        ontology_root,
        "bridge_claim_status.json",
        {"bridge_statuses": [{"bridge_id": marker_a, "status": marker_b}]},
    )
    output_dir = tmp_path / marker_a / "out"
    packet_paths = build_evidence_packet(
        str(manifest_path), str(output_dir), ontology_root=str(ontology_root),
        metadata_root=str(metadata_root),
    )
    output_text = "\n".join(
        (output_dir / path).read_text(encoding="utf-8") for path in packet_paths.values()
    )
    assert all(Path(path).name == path for path in packet_paths.values())
    assert marker_a not in json.dumps(packet_paths)
    assert marker_a not in output_text
    assert marker_b not in output_text

    result = _mod.main([
        "--manifest", str(manifest_path), "--out", str(tmp_path / "cli-out"),
        "--ontology-root", str(ontology_root), "--metadata-root", str(metadata_root),
    ])
    captured = capsys.readouterr()
    assert result == 0
    assert marker_a not in captured.out + captured.err
    assert marker_b not in captured.out + captured.err


def test_duplicate_and_malformed_metadata_errors_omit_identifier_values(tmp_path):
    marker = "SYNTHETIC_RAW_ID_LEAK_MARKER_DUPLICATE_0C93"
    metadata_root = _setup_metadata_inputs(
        tmp_path,
        participant_rows=(
            "participant_id\texcluded\n"
            f"{marker}\tFalse\n"
            f"{marker}\tFalse\n"
        ),
    )
    audit = _mod._metadata_reconciliation(str(metadata_root))
    error_text = json.dumps(audit)
    assert "participants_tsv_duplicate_subject:row:3" in error_text
    assert marker not in error_text

    (metadata_root / "dataset_description.json").write_text(
        f'{{"{marker}":"first","padding":true,"{marker}":"second"}}',
        encoding="utf-8",
    )
    malformed = _mod._metadata_reconciliation(str(metadata_root))
    assert marker not in json.dumps(malformed)
    assert "dataset_description_invalid_json:ValueError" in malformed["metadata_parse_errors"]
