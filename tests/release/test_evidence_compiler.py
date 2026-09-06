"""Schema + fail-closed validator tests for the release evidence bundle.

The Release compiler (scripts/compile_repository_evidence.py) is not in this
write set. These tests lock the contract that compiler must obey.

This file is not compiled scientific evidence. Synthetic fixtures cannot
establish scientific PASS.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from .evidence_validate import (
    MATRIX_PATH,
    SCHEMA_PATH,
    WATCHED_PRS,
    EvidenceValidationError,
    clone_doc,
    load_inventory,
    load_schema,
    load_yaml,
    validate,
    validate_compiled_report,
    validate_inventory,
)

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"


def _malformed_paths() -> list[Path]:
    return sorted(FIXTURE_DIR.glob("malformed_*.yaml"))


def test_schema_file_defines_required_contract():
    schema = load_schema()
    assert schema["schema_version"] == "1.0.0"
    assert schema["inventory_is_not_evidence"] is True
    assert schema["empirical_pass_from_this_pack_default"] is False
    assert "merge_status" in schema["enums"]
    assert set(schema["enums"]["merge_status"]) == {
        "merged",
        "open",
        "draft",
        "branch_only",
        "blocked",
        "unverified",
        "closed",
        "unknown",
    }
    assert schema["enums"]["status_category"] == [
        "VERIFIED_MERGED",
        "OPEN_REVIEW",
        "DRAFT_REVIEW",
        "BRANCH_ONLY",
        "CI_BLOCKED",
        "BILLING_BLOCKED",
        "SUPERSEDED",
        "DUPLICATE",
        "SCIENTIFIC_REVIEW_REQUIRED",
        "UNVERIFIED",
    ]
    assert "verified_pass" in schema["enums"]["author_test_results"]
    assert schema["enums"]["claim_class"] == [
        "none",
        "synthetic",
        "proxy",
        "unsupported",
        "empirical",
        "unavailable",
    ]
    assert schema["enums"]["value_class"] == [
        "scientific",
        "engineering",
        "governance",
        "tooling",
        "performance",
        "interoperability",
    ]
    assert schema["enums"]["release_recommendation"] == [
        "READY_FOR_REVIEW",
        "BLOCKED_BY_CI",
        "BLOCKED_BY_MISSING_BRANCHES",
        "BLOCKED_BY_SCIENTIFIC_VALIDATION",
        "READY_FOR_MERGE_REVIEW",
    ]
    inventory_keys = schema["inventory"]["required_envelope_keys"]
    for key in (
        "repository",
        "baseline_commit",
        "evidence_source",
        "inventory_is_not_evidence",
        "required_warnings",
        "contributions",
    ):
        assert key in inventory_keys
    report_fields = schema["compiled_report"]["required_contribution_fields"]
    for key in (
        "repository",
        "baseline_commit",
        "branch",
        "agent",
        "work_order",
        "final_commit",
        "pr",
        "changed_files",
        "tests",
        "test_results",
        "artifacts",
        "scientific_assertions",
        "limitations",
        "open_questions",
        "next_action",
        "verification_status",
        "merge_status",
        "evidence_source",
    ):
        assert key in report_fields
    rule_ids = {rule["id"] for rule in schema["hard_rules"]}
    assert "synthetic_not_scientific_pass" in rule_ids
    assert "unverified_author_tests_not_compiled_pass" in rule_ids
    assert "open_or_draft_not_merged" in rule_ids
    assert "prs_210_211_212_not_merged_unless_verified" in rule_ids
    assert "inventory_is_not_evidence_required" in rule_ids
    assert "empirical_pass_false_for_weak_claims" in rule_ids
    assert "billing_not_started_not_pass" in rule_ids
    assert "stacked_parent_required" in rule_ids
    assert "stacked_merged_parent_open_contradiction" in rule_ids
    assert "process_memory_kind_or_unavailable" in rule_ids
    assert "adapters_supported_false_not_described_supported" in rule_ids
    assert SCHEMA_PATH.is_file()


def test_real_matrix_passes_structural_validation():
    doc = load_inventory()
    errors = validate_inventory(doc)
    assert errors == [], errors
    assert MATRIX_PATH.is_file()
    assert len(doc["contributions"]) == 19
    assert doc["inventory_is_not_evidence"] is True
    assert doc["research_phase"]["empirical_pass_from_this_pack"] is False
    assert doc["research_phase"]["inventory_is_not_evidence"] is True
    for row in doc["contributions"]:
        classified = row["research_classification"]
        assert classified["empirical_pass_allowed"] is False
        assert classified["claim_class"] in {
            "none",
            "synthetic",
            "proxy",
            "unsupported",
            "empirical",
            "unavailable",
        }
        assert row["verification_status"]["scientific_pass"] == "not_claimed"
        assert row["verification_status"]["author_test_results"] == "unverified"


def test_malformed_report_fixtures_fail():
    paths = _malformed_paths()
    assert paths, "expected malformed_*.yaml fixtures"
    for path in paths:
        errors = validate_compiled_report(path)
        assert errors, f"fixture {path.name} must fail closed, got empty error list"


def test_duplicate_id_fails():
    errors = validate_compiled_report(FIXTURE_DIR / "malformed_duplicate_ids.yaml")
    assert any(item.startswith("duplicate_id:") for item in errors), errors


def test_duplicate_branch_fails():
    errors = validate_compiled_report(FIXTURE_DIR / "malformed_duplicate_branches.yaml")
    assert any(item.startswith("duplicate_branch:") for item in errors), errors


def test_duplicate_work_order_fails():
    doc = load_inventory()
    mutated = clone_doc(doc)
    mutated["contributions"][0]["work_order"] = "NTS-SLICE-A-RUNRECORD-SIDECAR-01"
    errors = validate_inventory(mutated)
    assert "duplicate_work_order:NTS-SLICE-A-RUNRECORD-SIDECAR-01" in errors


def test_inventory_reused_branches_are_not_duplicate_failures():
    """Lead inventory may repeat a reused lane or leftover remote tip."""
    doc = load_inventory()
    branches = [row.get("branch") for row in doc["contributions"] if row.get("branch")]
    assert len(branches) != len(set(branches))
    assert validate_inventory(doc) == []


def test_open_versus_merged_contradiction_fails():
    errors = validate_compiled_report(FIXTURE_DIR / "malformed_open_vs_merged.yaml")
    assert any("merged_and_is_draft" in item for item in errors), errors
    assert any("merged_and_pr_state_open" in item for item in errors), errors


def test_matrix_open_row_flipped_to_merged_fails():
    doc = load_inventory()
    mutated = clone_doc(doc)
    row = next(item for item in mutated["contributions"] if item.get("pr_number") == 212)
    row["merge_status"] = "merged"
    row["is_draft"] = True
    errors = validate_inventory(mutated)
    assert any("merged_and_is_draft" in item for item in errors), errors
    assert any("watched_pr" in item for item in errors), errors


def test_synthetic_labeled_empirical_pass_fails():
    errors = validate_compiled_report(FIXTURE_DIR / "malformed_synthetic_pass.yaml")
    assert any(item.startswith("synthetic_scientific_pass:") for item in errors), errors
    assert any(item.startswith("synthetic_empirical_pass_allowed:") for item in errors), errors
    assert any("synthetic_test_results_pass:" in item for item in errors), errors


def test_synthetic_data_mode_cannot_claim_scientific_pass():
    doc = load_inventory()
    mutated = clone_doc(doc)
    row = next(
        item
        for item in mutated["contributions"]
        if item["research_classification"]["data_mode"] == "synthetic"
    )
    row["verification_status"]["scientific_pass"] = "pass"
    row["research_classification"]["empirical_pass_allowed"] = True
    errors = validate_inventory(mutated)
    assert any(item.startswith("synthetic_scientific_pass:") for item in errors), errors
    assert any(
        item.startswith("synthetic_empirical_pass_allowed:") for item in errors
    ), errors


def test_unverified_author_test_results_used_as_pass_fails():
    errors = validate_compiled_report(FIXTURE_DIR / "malformed_unverified_pass.yaml")
    assert any(
        item.startswith("unverified_author_tests_as_scientific_pass:") for item in errors
    ), errors
    assert any(
        item.startswith("unverified_author_tests_as_test_results_pass:") for item in errors
    ), errors
    assert any(
        item.startswith("unverified_author_tests_as_compiled_evidence:") for item in errors
    ), errors


def test_matrix_unverified_author_results_flipped_to_pass_fails():
    doc = load_inventory()
    mutated = clone_doc(doc)
    row = mutated["contributions"][0]
    assert row["verification_status"]["author_test_results"] == "unverified"
    row["verification_status"]["scientific_pass"] = "pass"
    row["test_results"] = "PASS"
    row["compiled_from_author_test_results"] = True
    errors = validate_inventory(mutated)
    assert any("unverified_author_tests" in item for item in errors), errors


def test_no_secret_patterns_in_real_matrix():
    errors = validate_inventory(load_inventory())
    assert errors == []
    secret_hits = [item for item in errors if item.startswith("secret:")]
    assert secret_hits == []


def test_secret_pattern_fails_closed():
    errors = validate_compiled_report(FIXTURE_DIR / "malformed_secrets.yaml")
    assert any(item.startswith("secret:openai_or_anthropic_key:") for item in errors), errors


def test_nan_and_infinity_rejected():
    errors = validate_compiled_report(FIXTURE_DIR / "malformed_nan.yaml")
    finite_errors = [item for item in errors if item.startswith("non_finite_number:")]
    assert finite_errors, errors
    assert any("changed_file_count" in item for item in finite_errors)
    assert any("additions" in item for item in finite_errors)
    assert any("deletions" in item for item in finite_errors)


def test_in_memory_nan_and_infinity_rejected():
    doc = load_inventory()
    mutated = clone_doc(doc)
    mutated["contributions"][0]["additions"] = float("nan")
    mutated["contributions"][1]["deletions"] = float("inf")
    mutated["contributions"][2]["changed_file_count"] = float("-inf")
    errors = validate_inventory(mutated)
    assert any("additions" in item for item in errors if item.startswith("non_finite_number:"))
    assert any("deletions" in item for item in errors if item.startswith("non_finite_number:"))
    assert any(
        "changed_file_count" in item for item in errors if item.startswith("non_finite_number:")
    )


def test_deterministic_repeat():
    inventory = load_inventory()
    first = validate_inventory(inventory)
    second = validate_inventory(inventory)
    assert first == second
    assert first == []

    fixture = FIXTURE_DIR / "malformed_synthetic_pass.yaml"
    a = validate_compiled_report(fixture)
    b = validate_compiled_report(fixture)
    assert a == b
    assert a  # fail-closed, not an empty success

    mutated = clone_doc(inventory)
    mutated["contributions"][0]["id"] = mutated["contributions"][1]["id"]
    mutated["inventory_is_not_evidence"] = False
    run_one = validate_inventory(mutated)
    run_two = validate_inventory(mutated)
    assert run_one == run_two
    assert run_one


def test_required_warnings_present_for_210_211_212_not_merged():
    doc = load_inventory()
    errors = validate_inventory(doc)
    assert errors == [], errors
    blob = "\n".join(doc["required_warnings"] + doc["research_phase"]["required_warnings"])
    for prn in WATCHED_PRS:
        assert str(prn) in blob
    assert "not merged" in blob.lower()
    by_pr = {
        row["pr_number"]: row
        for row in doc["contributions"]
        if row.get("pr_number") in WATCHED_PRS
    }
    assert set(by_pr) == set(WATCHED_PRS)
    for prn, row in by_pr.items():
        assert row["merge_status"] != "merged", prn
        assert row["merge_status"] in {"open", "draft"}


def test_dropping_required_warning_fails():
    doc = load_inventory()
    mutated = clone_doc(doc)
    mutated["required_warnings"] = ["synthetic data cannot establish scientific PASS"]
    mutated["research_phase"]["required_warnings"] = list(mutated["required_warnings"])
    errors = validate_inventory(mutated)
    assert "required_warning_missing:prs_210_211_212_not_merged" in errors


def test_inventory_is_not_evidence_must_be_true():
    doc = load_inventory()
    mutated = clone_doc(doc)
    mutated["inventory_is_not_evidence"] = False
    errors = validate_inventory(mutated)
    assert "inventory_is_not_evidence_must_be_true" in errors


def test_proxy_and_unsupported_cannot_set_empirical_pass_allowed():
    doc = load_inventory()
    mutated = clone_doc(doc)
    proxy = next(
        item
        for item in mutated["contributions"]
        if item["research_classification"]["claim_class"] == "proxy"
    )
    unsupported = next(
        item
        for item in mutated["contributions"]
        if item["research_classification"]["claim_class"] == "unsupported"
    )
    proxy["research_classification"]["empirical_pass_allowed"] = True
    unsupported["research_classification"]["empirical_pass_allowed"] = True
    mutated["empirical_pass_from_this_pack"] = True
    errors = validate_inventory(mutated)
    assert any(item.startswith("empirical_pass_allowed_for_non_empirical:") for item in errors)
    assert "empirical_pass_from_this_pack_must_be_false" in errors


def test_missing_required_inventory_field_fails():
    doc = load_inventory()
    mutated = clone_doc(doc)
    del mutated["contributions"][0]["id"]
    del mutated["evidence_source"]
    errors = validate_inventory(mutated)
    assert "missing_field:evidence_source" in errors
    assert any(item.endswith(".id") and item.startswith("missing_field:") for item in errors)


def test_raise_on_error_is_fail_closed():
    with pytest.raises(EvidenceValidationError) as caught:
        validate_compiled_report(
            FIXTURE_DIR / "malformed_missing_fields.yaml",
            raise_on_error=True,
        )
    assert caught.value.errors
    assert validate_inventory(load_inventory(), raise_on_error=True) == []


def test_schema_and_matrix_yaml_roundtrip_is_stable():
    schema_text = SCHEMA_PATH.read_text(encoding="utf-8")
    matrix_text = MATRIX_PATH.read_text(encoding="utf-8")
    schema_a = yaml.safe_load(schema_text)
    schema_b = yaml.safe_load(schema_text)
    matrix_a = yaml.safe_load(matrix_text)
    matrix_b = yaml.safe_load(matrix_text)
    assert schema_a == schema_b
    assert matrix_a == matrix_b
    assert validate(schema_a, kind="inventory") != [] or schema_a.get("kind") == "evidence_bundle_contract"
    assert validate_inventory(matrix_a) == validate_inventory(matrix_b)


def test_validate_accepts_path_and_mapping():
    from_path = validate(MATRIX_PATH, kind="inventory")
    from_doc = validate(load_inventory(), kind="inventory")
    assert from_path == from_doc == []


def test_billing_not_started_cannot_be_verified_pass():
    errors = validate_compiled_report(FIXTURE_DIR / "malformed_billing_as_pass.yaml")
    assert any(
        item.startswith("billing_not_started_as_verified_pass:") for item in errors
    ), errors
    assert any(
        item.startswith("billing_not_started_as_test_results_pass:") for item in errors
    ), errors


def test_matrix_billing_annotation_flipped_to_pass_fails():
    doc = load_inventory()
    mutated = clone_doc(doc)
    row = mutated["contributions"][0]
    row["status"] = ["OPEN_REVIEW", "BILLING_BLOCKED"]
    row["github_checks"] = {
        "billing_not_started": True,
        "log_note": "job was not started because payments failed / spending limit",
    }
    row["verification_status"]["author_test_results"] = "verified_pass"
    row["test_results"] = "PASS"
    errors = validate_inventory(mutated)
    assert any("billing_not_started" in item for item in errors), errors


def test_stacked_canonical_pairs_pass():
    errors = validate_inventory(FIXTURE_DIR / "wellformed_stacked_pairs.yaml")
    assert errors == [], errors


def test_stacked_missing_parent_fails():
    errors = validate_compiled_report(FIXTURE_DIR / "malformed_stacked_missing_parent.yaml")
    assert any(item.startswith("stacked_parent_missing:") for item in errors), errors


def test_stacked_merged_while_parent_open_fails():
    errors = validate_inventory(FIXTURE_DIR / "malformed_stacked_merged_parent_open.yaml")
    assert any(
        item.startswith("stacked_merged_while_parent_open:") for item in errors
    ), errors


def test_stacked_pairs_child_flipped_to_merged_fails():
    doc = load_yaml(FIXTURE_DIR / "wellformed_stacked_pairs.yaml")
    mutated = clone_doc(doc)
    child = next(item for item in mutated["contributions"] if item.get("pr_number") == 215)
    child["merge_status"] = "merged"
    child["is_draft"] = False
    child["section"] = "MERGED"
    child["status"] = ["VERIFIED_MERGED"]
    errors = validate_inventory(mutated)
    assert any(
        item.startswith("stacked_merged_while_parent_open:") for item in errors
    ), errors


def test_adapters_supported_false_cannot_claim_supported():
    errors = validate_compiled_report(
        FIXTURE_DIR / "malformed_adapters_supported_claim.yaml"
    )
    assert any(
        item.startswith("adapters_supported_false_described_as_supported:")
        for item in errors
    ), errors


def test_stacked_220_adapters_false_flipped_to_supported_claim_fails():
    doc = load_yaml(FIXTURE_DIR / "wellformed_stacked_pairs.yaml")
    mutated = clone_doc(doc)
    row = next(item for item in mutated["contributions"] if item.get("pr_number") == 220)
    assert row["research_classification"]["adapters_supported"] is False
    row["research_classification"]["research_notes"] = (
        "Native signal adapters are supported."
    )
    row["adapters_claim"] = "supported"
    errors = validate_inventory(mutated)
    assert any(
        item.startswith("adapters_supported_false_described_as_supported:")
        for item in errors
    ), errors


def test_unlabeled_memory_as_verified_fails():
    errors = validate_compiled_report(FIXTURE_DIR / "malformed_unlabeled_memory.yaml")
    assert any(item.startswith("unlabeled_memory_as_verified:") for item in errors), errors
    assert any(
        item.startswith("memory_kind_or_unavailable_required:") for item in errors
    ), errors


def test_labeled_or_unavailable_memory_passes():
    doc = load_yaml(FIXTURE_DIR / "wellformed_stacked_pairs.yaml")
    errors = validate_inventory(doc)
    assert errors == [], errors
    row = next(item for item in doc["contributions"] if item.get("pr_number") == 215)
    assert row["process_memory"]["independently_verified"] == "unavailable"


def test_pr225_inventory_fixture_does_not_invent_pass():
    path = FIXTURE_DIR / "inventory_pr225_head.yaml"
    doc = load_yaml(path)
    errors = validate_inventory(doc)
    assert errors == [], errors
    assert doc.get("empirical_pass_from_this_pack") is not True
    assert doc["research_phase"]["empirical_pass_from_this_pack"] is False
    assert doc["inventory_is_not_evidence"] is True
    scientific_pass_values = {
        row["verification_status"]["scientific_pass"] for row in doc["contributions"]
    }
    assert "pass" not in scientific_pass_values
    assert "claimed" not in scientific_pass_values
    for row in doc["contributions"]:
        classified = row["research_classification"]
        assert classified["empirical_pass_allowed"] is False
        assert row["verification_status"]["author_test_results"] != "verified_pass"
        assert row["verification_status"]["author_test_results"] != "pass"
        assert row["verification_status"]["scientific_pass"] == "not_claimed"
    by_pr = {
        row["pr_number"]: row
        for row in doc["contributions"]
        if row.get("pr_number") in {211, 212, 215, 220}
    }
    assert by_pr[215]["stacked_base"]["parent_pr"] == 211
    assert by_pr[220]["stacked_base"]["parent_pr"] == 212
    assert by_pr[220]["research_classification"]["adapters_supported"] is False
    assert by_pr[215]["merge_status"] != "merged"
    assert by_pr[220]["merge_status"] != "merged"


def test_open_status_category_cannot_be_merged():
    doc = load_inventory()
    mutated = clone_doc(doc)
    row = mutated["contributions"][0]
    row["merge_status"] = "merged"
    row["status"] = ["OPEN_REVIEW"]
    row["is_draft"] = False
    errors = validate_inventory(mutated)
    assert any("merged_and_open_status_category" in item for item in errors), errors
