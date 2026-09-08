"""Fail-closed schema tests for the release blocker registry.

QA owns this module and tests/release/blocker_registry_validate.py.
Release may later wrap those helpers in scripts/validate_release_blockers.py.
Do not invent that script here.

This file is not compiled scientific evidence. Synthetic fixtures cannot
establish scientific PASS. Live registry is consumed read-only.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from .blocker_registry_validate import (
    REGISTRY_PATH,
    REQUIRED_BLOCKER_FIELDS,
    BlockerRegistryValidationError,
    clone_doc,
    collect_forbidden_imports,
    load_registry,
    validate,
    validate_blocker_registry,
)

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "blockers"
OWNED_MODULES = (
    Path(__file__).resolve().parent / "blocker_registry_validate.py",
    Path(__file__).resolve(),
)


def _malformed_paths() -> list[Path]:
    return sorted(FIXTURE_DIR.glob("malformed_*.yaml"))


def test_live_registry_validates_clean():
    assert REGISTRY_PATH.is_file()
    doc = load_registry()
    errors = validate_blocker_registry(doc)
    assert errors == [], errors
    assert doc["kind"] == "blocker_registry"
    assert doc["inventory_is_not_evidence"] is True
    assert doc["empirical_pass_from_this_pack"] is False
    assert doc["scientific_pass_from_this_pack"] != "PASS"
    assert doc["current_integration"]["current_head_mismatch"] is False
    assert (
        doc["current_integration"]["head_ref_oid"]
        == doc["current_integration"]["expected_head_from_work_order"]
    )
    assert doc["current_integration"]["merged"] is False
    assert str(doc["current_integration"]["state"]).upper() == "OPEN"
    assert len(doc["blockers"]) == 14


def test_live_scientific_rows_are_not_supported():
    doc = load_registry()
    assert doc["research_phase"]["synthetic_status"] == "NOT_SUPPORTED"
    assert doc["research_phase"]["empirical_pass_from_this_pack"] is False
    scientific = [
        row
        for row in doc["blockers"]
        if row["category"] in {"SCIENTIFIC_REVIEW", "PROVENANCE_INCOMPLETE"}
        or row.get("research_classification", {}).get("class") == "scientific"
    ]
    assert scientific
    for row in scientific:
        classified = row["research_classification"]
        assert classified["scientific_claim_status"] == "NOT_SUPPORTED"
        assert classified["treats_unsupported_claim_as_evidence"] is False
        assert row["scientific_impact"] == "NOT_SUPPORTED"
        assert classified["scientific_claim_status"] != "PASS"


def test_live_treats_unsupported_claim_as_evidence_is_false():
    doc = load_registry()
    for row in doc["blockers"]:
        assert row["research_classification"]["treats_unsupported_claim_as_evidence"] is False


def test_live_required_blocker_fields_present():
    doc = load_registry()
    allowed = set(doc["allowed_categories"])
    for row in doc["blockers"]:
        for field in REQUIRED_BLOCKER_FIELDS:
            assert field in row, field
            assert row.get(field) is not None, field
        assert isinstance(row["exact_evidence"], list) and row["exact_evidence"]
        assert row["category"] in allowed


def test_live_billing_is_not_pytest_pass():
    doc = load_registry()
    billing = next(
        row for row in doc["blockers"] if row["category"] == "BILLING_OR_RUNNER_BLOCK"
    )
    assert billing["research_classification"]["billing_vs_true_ci"] == "billing_not_started"
    assert billing["research_classification"]["scientific_claim_status"] != "PASS"
    ci = next(
        row for row in doc["blockers"] if row["category"] == "CI_WORKFLOW_FAILURE"
    )
    assert ci["research_classification"]["billing_vs_true_ci"] == "true_ci_unread"
    test_fail = next(row for row in doc["blockers"] if row["category"] == "TEST_FAILURE")
    assert test_fail["research_classification"]["billing_vs_true_ci"] != "billing_not_started"
    assert test_fail["id"] == "nts-rb-isolated-test-failures-author-claim"


def test_live_isolated_run_not_independently_verified():
    doc = load_registry()
    isolated = doc["author_claimed_isolated_run"]
    assert isolated["independently_verified"] is False
    for row in doc["blockers"]:
        if row["category"] in {"TEST_FAILURE", "TIMEOUT"}:
            assert (
                row["research_classification"]["author_claim_independently_verified"]
                is False
            )


def test_live_dashboard_author_pass_stays_unverified():
    doc = load_registry()
    row = next(item for item in doc["blockers"] if item["category"] == "DASHBOARD_ISOLATION")
    assert row["author_documented_status"] == "PASS"
    assert row["independently_verified"] is False
    assert row["lead_verification_status"] == "unavailable"
    assert row["research_classification"]["author_claim_independently_verified"] is False


def test_live_memory_kind_unavailable():
    doc = load_registry()
    row = next(item for item in doc["blockers"] if item["category"] == "MEMORY_EVIDENCE")
    assert row["memory_kind"] == "unavailable"
    assert row["independently_verified"] is False


def test_live_no_invented_head_mismatch_blocker():
    doc = load_registry()
    mismatch = [
        row for row in doc["blockers"] if row["category"] == "CURRENT_HEAD_MISMATCH"
    ]
    assert mismatch == []


def test_malformed_fixtures_fail_closed():
    paths = _malformed_paths()
    assert paths, "expected fixtures/blockers/malformed_*.yaml"
    for path in paths:
        errors = validate_blocker_registry(path)
        assert errors, f"fixture {path.name} must fail closed, got empty error list"


def test_billing_as_pass_fixture_fails():
    errors = validate_blocker_registry(FIXTURE_DIR / "malformed_billing_as_pass.yaml")
    assert any("billing_not_started_as_pytest_pass:" in item for item in errors), errors


def test_synthetic_pass_fixture_fails():
    errors = validate_blocker_registry(FIXTURE_DIR / "malformed_synthetic_pass.yaml")
    assert any("invented_scientific_pass:" in item for item in errors), errors
    assert "empirical_pass_from_this_pack_must_be_false" in errors
    assert "synthetic_status_must_be_NOT_SUPPORTED" in errors


def test_missing_evidence_fixture_fails():
    errors = validate_blocker_registry(FIXTURE_DIR / "malformed_missing_evidence.yaml")
    assert any(item.startswith("empty_exact_evidence:") for item in errors), errors


def test_head_mismatch_invent_fixture_fails():
    errors = validate_blocker_registry(
        FIXTURE_DIR / "malformed_head_mismatch_invent.yaml"
    )
    invented = [item for item in errors if item.startswith("invented_current_head_mismatch:")]
    assert invented, errors


def test_unlabeled_memory_fixture_fails():
    errors = validate_blocker_registry(FIXTURE_DIR / "malformed_unlabeled_memory.yaml")
    assert any(item.startswith("unlabeled_memory_as_verified:") for item in errors), errors
    assert any(
        item.startswith("memory_kind_or_unavailable_required:") for item in errors
    ), errors


def test_dashboard_invent_pass_fixture_fails():
    errors = validate_blocker_registry(
        FIXTURE_DIR / "malformed_dashboard_invent_pass.yaml"
    )
    assert any(
        item.startswith("invented_dashboard_independently_verified:") for item in errors
    ), errors


def test_nan_fixture_fails():
    errors = validate_blocker_registry(FIXTURE_DIR / "malformed_nan.yaml")
    finite = [item for item in errors if item.startswith("non_finite_number:")]
    assert finite, errors
    assert any("changed_files" in item for item in finite)
    assert any("additions" in item for item in finite)
    assert any("deletions" in item for item in finite)
    assert any("peak" in item for item in finite)


def test_live_null_unavailable_fields_are_ok():
    doc = load_registry()
    billing = next(
        row for row in doc["blockers"] if row["id"] == "nts-rb-billing-236-current-head"
    )
    assert billing["prerequisite"] is None
    errors = validate_blocker_registry(doc)
    assert errors == [], errors


def test_missing_required_blocker_field_fails():
    doc = load_registry()
    mutated = clone_doc(doc)
    del mutated["blockers"][0]["id"]
    del mutated["blockers"][1]["recommended_action"]
    mutated["blockers"][2]["exact_evidence"] = []
    errors = validate_blocker_registry(mutated)
    assert any(item.endswith(".id") and item.startswith("missing_field:") for item in errors)
    assert any("recommended_action" in item for item in errors)
    assert any(item.startswith("empty_exact_evidence:") for item in errors)


def test_invalid_category_fails():
    doc = load_registry()
    mutated = clone_doc(doc)
    mutated["blockers"][0]["category"] = "NOT_A_REAL_CATEGORY"
    errors = validate_blocker_registry(mutated)
    assert any(item.startswith("invalid_category:") for item in errors), errors


def test_invented_head_mismatch_on_live_clone_fails():
    doc = load_registry()
    mutated = clone_doc(doc)
    mutated["current_integration"]["current_head_mismatch"] = True
    mutated["research_phase"]["current_head_mismatch"] = True
    mutated["blockers"][0]["category"] = "CURRENT_HEAD_MISMATCH"
    errors = validate_blocker_registry(mutated)
    invented = [item for item in errors if item.startswith("invented_current_head_mismatch:")]
    assert invented, errors


def test_billing_row_flipped_to_pytest_pass_fails():
    doc = load_registry()
    mutated = clone_doc(doc)
    row = next(
        item for item in mutated["blockers"] if item["category"] == "BILLING_OR_RUNNER_BLOCK"
    )
    row["test_results"] = "PASS"
    row["research_classification"]["scientific_claim_status"] = "PASS"
    errors = validate_blocker_registry(mutated)
    assert any("billing_not_started_as_pytest_pass:" in item for item in errors), errors


def test_empty_step_failure_as_test_failure_fails():
    doc = load_registry()
    mutated = clone_doc(doc)
    row = next(
        item for item in mutated["blockers"] if item["category"] == "CI_WORKFLOW_FAILURE"
    )
    row["category"] = "TEST_FAILURE"
    errors = validate_blocker_registry(mutated)
    assert any(
        item.startswith("empty_step_failure_as_test_failure:") for item in errors
    ), errors


def test_billing_vs_true_ci_inconsistent_fails():
    doc = load_registry()
    mutated = clone_doc(doc)
    test_fail = next(
        item for item in mutated["blockers"] if item["category"] == "TEST_FAILURE"
    )
    test_fail["research_classification"]["billing_vs_true_ci"] = "billing_not_started"
    billing = next(
        item for item in mutated["blockers"] if item["category"] == "BILLING_OR_RUNNER_BLOCK"
    )
    billing["research_classification"]["billing_vs_true_ci"] = "true_ci"
    errors = validate_blocker_registry(mutated)
    assert any("billing_as_test_failure:" in item for item in errors), errors
    assert any("billing_vs_true_ci_inconsistent:" in item for item in errors), errors


def test_scientific_row_flipped_to_pass_fails():
    doc = load_registry()
    mutated = clone_doc(doc)
    row = next(
        item
        for item in mutated["blockers"]
        if item["id"] == "nts-rb-scientific-review-synthetic-not-supported"
    )
    row["research_classification"]["scientific_claim_status"] = "PASS"
    row["scientific_impact"] = "PASS"
    mutated["empirical_pass_from_this_pack"] = True
    errors = validate_blocker_registry(mutated)
    assert any("invented_scientific_pass:" in item for item in errors), errors
    assert "empirical_pass_from_this_pack_must_be_false" in errors


def test_treats_unsupported_claim_as_evidence_true_fails():
    doc = load_registry()
    mutated = clone_doc(doc)
    mutated["blockers"][0]["research_classification"][
        "treats_unsupported_claim_as_evidence"
    ] = True
    errors = validate_blocker_registry(mutated)
    assert any(
        item.startswith("treats_unsupported_claim_as_evidence_must_be_false:")
        for item in errors
    ), errors


def test_unverified_isolated_counts_as_verified_pass_fails():
    doc = load_registry()
    mutated = clone_doc(doc)
    assert mutated["author_claimed_isolated_run"]["independently_verified"] is False
    row = next(
        item for item in mutated["blockers"] if item["category"] == "TEST_FAILURE"
    )
    row["research_classification"]["author_claim_independently_verified"] = True
    row["independently_verified"] = True
    row["test_results"] = "PASS"
    errors = validate_blocker_registry(mutated)
    assert any(
        item.startswith("unverified_isolated_counts_as_verified_pass:") for item in errors
    ), errors


def test_dashboard_invent_independently_verified_on_live_clone_fails():
    doc = load_registry()
    mutated = clone_doc(doc)
    row = next(
        item for item in mutated["blockers"] if item["category"] == "DASHBOARD_ISOLATION"
    )
    row["independently_verified"] = True
    errors = validate_blocker_registry(mutated)
    assert any(
        item.startswith("invented_dashboard_independently_verified:") for item in errors
    ), errors


def test_unlabeled_verified_memory_on_live_clone_fails():
    doc = load_registry()
    mutated = clone_doc(doc)
    row = next(
        item for item in mutated["blockers"] if item["category"] == "MEMORY_EVIDENCE"
    )
    row["independently_verified"] = True
    row["peak"] = 99.1
    del row["memory_kind"]
    errors = validate_blocker_registry(mutated)
    assert any(item.startswith("unlabeled_memory_as_verified:") for item in errors), errors


def test_in_memory_nan_and_infinity_rejected():
    doc = load_registry()
    mutated = clone_doc(doc)
    mutated["current_integration"]["changed_files"] = float("nan")
    mutated["current_integration"]["additions"] = float("inf")
    mutated["blockers"][0]["peak"] = float("-inf")
    errors = validate_blocker_registry(mutated)
    assert any("changed_files" in item for item in errors if item.startswith("non_finite_number:"))
    assert any("additions" in item for item in errors if item.startswith("non_finite_number:"))
    assert any("peak" in item for item in errors if item.startswith("non_finite_number:"))


def test_merged_true_on_open_pr_fails():
    doc = load_registry()
    mutated = clone_doc(doc)
    mutated["current_integration"]["merged"] = True
    mutated["current_integration"]["state"] = "OPEN"
    errors = validate_blocker_registry(mutated)
    assert "contradiction:current_integration:merged_and_state_open" in errors


def test_secret_pattern_fails_closed():
    doc = load_registry()
    mutated = clone_doc(doc)
    mutated["blockers"][0]["notes"] = (
        "leaked placeholder sk-proj-FAKESECRET_a1b2c3d4e5f6g7h8i9j0"
    )
    errors = validate_blocker_registry(mutated)
    assert any(item.startswith("secret:openai_or_anthropic_key:") for item in errors), errors


def test_no_secret_patterns_in_live_registry():
    errors = validate_blocker_registry(load_registry())
    assert errors == []
    secret_hits = [item for item in errors if item.startswith("secret:")]
    assert secret_hits == []


def test_deterministic_repeat():
    live = load_registry()
    first = validate_blocker_registry(live)
    second = validate_blocker_registry(live)
    assert first == second
    assert first == []

    fixture = FIXTURE_DIR / "malformed_synthetic_pass.yaml"
    a = validate_blocker_registry(fixture)
    b = validate_blocker_registry(fixture)
    assert a == b
    assert a

    mutated = clone_doc(live)
    mutated["empirical_pass_from_this_pack"] = True
    mutated["blockers"][0]["id"] = mutated["blockers"][1]["id"]
    run_one = validate_blocker_registry(mutated)
    run_two = validate_blocker_registry(mutated)
    assert run_one == run_two
    assert run_one


def test_raise_on_error_is_fail_closed():
    with pytest.raises(BlockerRegistryValidationError) as caught:
        validate_blocker_registry(
            FIXTURE_DIR / "malformed_missing_evidence.yaml",
            raise_on_error=True,
        )
    assert caught.value.errors
    assert validate_blocker_registry(load_registry(), raise_on_error=True) == []


def test_validate_accepts_path_and_mapping():
    from_path = validate(REGISTRY_PATH)
    from_doc = validate(load_registry())
    assert from_path == from_doc == []


def test_yaml_roundtrip_is_stable():
    text = REGISTRY_PATH.read_text(encoding="utf-8")
    first = yaml.safe_load(text)
    second = yaml.safe_load(text)
    assert first == second
    assert validate_blocker_registry(first) == validate_blocker_registry(second) == []


def test_owned_modules_have_no_network_imports():
    hits: list[str] = []
    for path in OWNED_MODULES:
        hits.extend(collect_forbidden_imports(path))
    assert hits == [], hits
