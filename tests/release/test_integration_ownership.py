"""Fail-closed schema tests for the integration ownership inventory.

QA owns this module and tests/release/integration_ownership_validate.py.
Release may later wrap those helpers in scripts/validate_integration_ownership.py.
Do not invent that script here.

This file is not compiled scientific evidence. Synthetic fixtures cannot
establish scientific PASS. Live inventory is consumed read-only.
Alfred is noted in the ownership graph; Researchy NO ACT this wave.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from .integration_ownership_validate import (
    ALLOWED_STATUSES,
    AUTHOR_BODY_SHA,
    INVENTORY_PATH,
    REQUIRED_ENVELOPE_FIELDS,
    REQUIRED_WORK_ITEM_FIELDS,
    IntegrationOwnershipValidationError,
    clone_doc,
    collect_forbidden_imports,
    load_inventory,
    validate,
    validate_integration_ownership,
)

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "ownership"
OWNED_MODULES = (
    Path(__file__).resolve().parent / "integration_ownership_validate.py",
    Path(__file__).resolve(),
)
LIVE_HEAD = "af3ac584419148ddcfc57cb565c416eba6328725"
REQUIRED_MALFORMED = (
    "malformed_integrated_only_as_main.yaml",
    "malformed_invented_verified_on_open.yaml",
    "malformed_dual_owner.yaml",
    "malformed_researchy_as_research.yaml",
    "malformed_synthetic_pass.yaml",
    "malformed_empty_step_as_blocked_by_tests.yaml",
    "malformed_invented_isolated_verified.yaml",
    "malformed_body_sha_as_live_head.yaml",
    "malformed_competing_merger.yaml",
)


def _malformed_paths() -> list[Path]:
    return sorted(FIXTURE_DIR.glob("malformed_*.yaml"))


def test_live_inventory_validates_clean():
    assert INVENTORY_PATH.is_file()
    doc = load_inventory()
    errors = validate_integration_ownership(doc)
    assert errors == [], errors
    assert doc["kind"] == "integration_ownership_inventory"
    assert doc["inventory_is_not_evidence"] is True
    assert doc["empirical_pass_from_this_pack"] is False
    assert doc["scientific_pass_from_this_pack"] != "PASS"
    assert doc["sole_merger"] == "Codex_C"
    assert doc["CURRENT_INTEGRATION_HEAD"] == LIVE_HEAD
    assert doc["current_integration"]["head_ref_oid"] == LIVE_HEAD
    assert doc["current_integration"]["merged"] is False
    assert doc["current_integration"]["on_origin_main"] is False
    assert doc["current_integration"]["status"] == "OPEN_REVIEW"
    assert doc["current_integration"]["pr_number"] == 236
    assert len(doc["work_items"]) == 15


def test_live_required_envelope_and_status_enum():
    doc = load_inventory()
    for field in REQUIRED_ENVELOPE_FIELDS:
        assert field in doc, field
        assert doc.get(field) is not None, field
    assert tuple(doc["allowed_statuses"]) == ALLOWED_STATUSES
    assert set(doc["allowed_statuses"]) == set(ALLOWED_STATUSES)


def test_live_work_items_have_ids_statuses_and_labels():
    doc = load_inventory()
    assert doc["research_phase"]["phase"] == "RESEARCH"
    ids: list[str] = []
    for row in doc["work_items"]:
        for field in REQUIRED_WORK_ITEM_FIELDS:
            assert field in row, field
        assert row["status"] in ALLOWED_STATUSES
        assert row["research_claim_label"]["status"] == "labeled"
        ids.append(row["id"])
    assert len(ids) == len(set(ids))
    assert len(ids) == 15


def test_live_verified_requires_merged_and_on_main():
    doc = load_inventory()
    verified = [row for row in doc["work_items"] if row["status"] == "VERIFIED"]
    assert verified
    for row in verified:
        assert row["merged"] is True
        assert row["on_origin_main"] is True
        assert row.get("pr_number") != 236


def test_live_integrated_only_is_not_on_main():
    doc = load_inventory()
    integrated = [
        row for row in doc["work_items"] if row["status"] == "INTEGRATED_ONLY"
    ]
    assert integrated
    for row in integrated:
        assert row.get("on_origin_main") is not True
        assert row.get("base_ref_name") != "main"


def test_live_pr236_is_open_review_not_verified():
    doc = load_inventory()
    row = next(item for item in doc["work_items"] if item["id"] == "nts-io-pr-236")
    assert row["status"] == "OPEN_REVIEW"
    assert row["merged"] is False
    assert row["on_origin_main"] is False
    assert row["head_ref_oid"] == LIVE_HEAD
    assert row["ci_status"] == "BLOCKED_BY_CI"
    assert row["ci_status"] != "BLOCKED_BY_TESTS"


def test_live_body_sha_stays_unverified():
    doc = load_inventory()
    reported = doc["reported_vs_live_heads"]["reported"]
    body = next(item for item in reported if item.get("oid") == AUTHOR_BODY_SHA)
    assert body["status"] == "UNVERIFIED"
    assert body["on_origin_main"] is False
    assert doc["CURRENT_INTEGRATION_HEAD"] != AUTHOR_BODY_SHA
    assert doc["reported_vs_live_heads"]["live_oid"] == LIVE_HEAD


def test_live_be277ecd_is_intermediate_integrated_only():
    doc = load_inventory()
    row = next(
        item
        for item in doc["work_items"]
        if item["id"] == "nts-io-sha-be277ecd-intermediate"
    )
    assert row["status"] == "INTEGRATED_ONLY"
    assert row["on_origin_main"] is False
    assert row["merged"] is False
    assert row["role"] == "intermediate"


def test_live_alfred_graph_and_researchy_no_act():
    doc = load_inventory()
    graph = doc["alfred_ownership_graph"]
    assert graph["organization_auditor"] == "Alfred"
    assert graph["lead_developer"] == "Lead"
    assert graph["sole_merger"] == "Codex_C"
    assert graph["sole_evidence_authority"] == "Release"
    assert "Alfred" in doc["bots_used"]
    assert "Researchy" not in doc["bots_used"]
    assert doc["research_phase"]["researchy_acted"] is False
    researchy = next(
        item
        for item in doc["duplicate_decisions_this_wave"]["bots"]
        if item["id"] == "researchy"
    )
    assert researchy["act_this_wave"] is False
    assert doc["researchy_findings"] is None


def test_live_synthetic_not_supported_and_not_empirical_pass():
    doc = load_inventory()
    assert doc["research_phase"]["synthetic_status"] == "NOT_SUPPORTED"
    assert doc["research_phase"]["proxy_bayes_equals_formal"] is False
    assert doc["research_phase"]["empirical_pass_from_this_pack"] is False
    assert doc["scientific_standing_warnings"]["synthetic"] == "NOT_SUPPORTED"
    assert doc["scientific_standing_warnings"]["proxy_bayes_equals_formal"] is False


def test_malformed_fixtures_fail_closed():
    paths = _malformed_paths()
    assert paths, "expected fixtures/ownership/malformed_*.yaml"
    names = {path.name for path in paths}
    for required in REQUIRED_MALFORMED:
        assert required in names, required
    for path in paths:
        errors = validate_integration_ownership(path)
        assert errors, f"fixture {path.name} must fail closed, got empty error list"


def test_integrated_only_as_main_fixture_fails():
    errors = validate_integration_ownership(
        FIXTURE_DIR / "malformed_integrated_only_as_main.yaml"
    )
    assert any(item.startswith("integrated_only_as_main:") for item in errors), errors


def test_invented_verified_on_open_fixture_fails():
    errors = validate_integration_ownership(
        FIXTURE_DIR / "malformed_invented_verified_on_open.yaml"
    )
    assert any(item.startswith("invented_verified_on_open:") for item in errors), errors


def test_dual_owner_fixture_fails():
    errors = validate_integration_ownership(FIXTURE_DIR / "malformed_dual_owner.yaml")
    assert "dual_primary_owners" in errors, errors


def test_researchy_as_research_fixture_fails():
    errors = validate_integration_ownership(
        FIXTURE_DIR / "malformed_researchy_as_research.yaml"
    )
    assert "researchy_as_research" in errors, errors


def test_synthetic_pass_fixture_fails():
    errors = validate_integration_ownership(
        FIXTURE_DIR / "malformed_synthetic_pass.yaml"
    )
    assert any(item.startswith("invented_scientific_pass:") for item in errors), errors
    assert "empirical_pass_from_this_pack_must_be_false" in errors
    assert "synthetic_status_must_be_NOT_SUPPORTED" in errors
    assert "proxy_bayes_equals_formal_must_be_false" in errors


def test_empty_step_as_blocked_by_tests_fixture_fails():
    errors = validate_integration_ownership(
        FIXTURE_DIR / "malformed_empty_step_as_blocked_by_tests.yaml"
    )
    assert any(
        item.startswith("empty_step_as_blocked_by_tests:") for item in errors
    ), errors
    assert any(
        item.startswith("billing_unstarted_as_pytest_pass:") for item in errors
    ), errors


def test_invented_isolated_verified_fixture_fails():
    errors = validate_integration_ownership(
        FIXTURE_DIR / "malformed_invented_isolated_verified.yaml"
    )
    assert any(
        item.startswith("invented_isolated_verified:") for item in errors
    ), errors


def test_body_sha_as_live_head_fixture_fails():
    errors = validate_integration_ownership(
        FIXTURE_DIR / "malformed_body_sha_as_live_head.yaml"
    )
    assert any(item.startswith("body_sha_as_live_head:") for item in errors), errors


def test_competing_merger_fixture_fails():
    errors = validate_integration_ownership(
        FIXTURE_DIR / "malformed_competing_merger.yaml"
    )
    assert any(item.startswith("competing_merger:") for item in errors), errors


def test_nan_fixture_fails():
    errors = validate_integration_ownership(FIXTURE_DIR / "malformed_nan.yaml")
    finite = [item for item in errors if item.startswith("non_finite_number:")]
    assert finite, errors
    assert any("changed_files" in item for item in finite)
    assert any("additions" in item for item in finite)
    assert any("deletions" in item for item in finite)


def test_duplicate_id_fixture_fails():
    errors = validate_integration_ownership(
        FIXTURE_DIR / "malformed_duplicate_ids.yaml"
    )
    assert "duplicate_id:fixture-duplicate-id" in errors


def test_missing_required_fields_fixture_fails():
    errors = validate_integration_ownership(
        FIXTURE_DIR / "malformed_missing_fields.yaml"
    )
    assert "missing_field:CURRENT_INTEGRATION_HEAD" in errors
    assert any(
        item.endswith(".head_ref_oid") and item.startswith("missing_field:")
        for item in errors
    )
    assert any(item.endswith(".id") and item.startswith("missing_field:") for item in errors)
    assert any(
        item.endswith(".status") and item.startswith("missing_field:") for item in errors
    )


def test_integrated_only_flipped_to_on_main_fails():
    doc = load_inventory()
    mutated = clone_doc(doc)
    row = next(item for item in mutated["work_items"] if item["id"] == "nts-io-pr-220")
    assert row["status"] == "INTEGRATED_ONLY"
    row["on_origin_main"] = True
    row["base_ref_name"] = "main"
    errors = validate_integration_ownership(mutated)
    assert any(item.startswith("integrated_only_as_main:") for item in errors), errors


def test_open_236_flipped_to_verified_fails():
    doc = load_inventory()
    mutated = clone_doc(doc)
    mutated["current_integration"]["status"] = "VERIFIED"
    row = next(item for item in mutated["work_items"] if item["id"] == "nts-io-pr-236")
    row["status"] = "VERIFIED"
    errors = validate_integration_ownership(mutated)
    invented = [item for item in errors if item.startswith("invented_verified_on_open:")]
    assert invented, errors


def test_researchy_acted_on_live_clone_fails():
    doc = load_inventory()
    mutated = clone_doc(doc)
    mutated["research_phase"]["researchy_acted"] = True
    mutated["ownership_decisions"]["roles"]["research_and_tooling"]["name"] = "Researchy"
    errors = validate_integration_ownership(mutated)
    assert "researchy_as_research" in errors


def test_lingxi_nightly_chief_as_owners_fail():
    doc = load_inventory()
    mutated = clone_doc(doc)
    mutated["alfred_ownership_graph"]["lead_developer"] = "Lingxi"
    mutated["ownership_decisions"]["roles"]["qa"]["name"] = "Lingxi"
    mutated["ownership_decisions"]["roles"]["integration"]["name"] = "Nightly Audit Engineer"
    mutated["ownership_decisions"]["roles"]["lead_developer"]["name"] = "Chief of Staff"
    mutated["bots_used"] = ["Lead", "Alfred", "tinkabot"]
    errors = validate_integration_ownership(mutated)
    assert "lingxi_as_lead" in errors
    assert "lingxi_as_qa" in errors
    assert "nightly_as_integration" in errors
    assert "chief_of_staff_as_lead" in errors
    assert any(item.startswith("no_act_bot_as_owner:") for item in errors), errors


def test_second_evidence_authority_fails():
    doc = load_inventory()
    mutated = clone_doc(doc)
    mutated["ownership_decisions"]["roles"]["release"]["second_evidence_authority"] = True
    mutated["alfred_ownership_graph"]["sole_evidence_authority"] = "QA"
    errors = validate_integration_ownership(mutated)
    assert any(item.startswith("second_evidence_authority:") for item in errors), errors


def test_competing_merger_on_live_clone_fails():
    doc = load_inventory()
    mutated = clone_doc(doc)
    mutated["sole_merger"] = "Integration"
    mutated["ownership_decisions"]["roles"]["lead_developer"]["may_merge"] = True
    mutated["ownership_decisions"]["roles"]["codex_c"]["compete"] = True
    errors = validate_integration_ownership(mutated)
    assert any(item.startswith("competing_merger:") for item in errors), errors


def test_synthetic_pass_on_live_clone_fails():
    doc = load_inventory()
    mutated = clone_doc(doc)
    mutated["empirical_pass_from_this_pack"] = True
    mutated["scientific_pass_from_this_pack"] = "PASS"
    mutated["research_phase"]["synthetic_status"] = "PASS"
    mutated["research_phase"]["proxy_bayes_equals_formal"] = True
    errors = validate_integration_ownership(mutated)
    assert "empirical_pass_from_this_pack_must_be_false" in errors
    assert any(item.startswith("invented_scientific_pass:") for item in errors), errors
    assert "synthetic_status_must_be_NOT_SUPPORTED" in errors
    assert "proxy_bayes_equals_formal_must_be_false" in errors


def test_empty_step_ci_flipped_to_blocked_by_tests_fails():
    doc = load_inventory()
    mutated = clone_doc(doc)
    row = next(item for item in mutated["work_items"] if item["id"] == "nts-io-pr-236")
    row["status"] = "BLOCKED_BY_TESTS"
    row["ci_status"] = "BLOCKED_BY_TESTS"
    errors = validate_integration_ownership(mutated)
    assert any(
        item.startswith("empty_step_as_blocked_by_tests:") for item in errors
    ), errors


def test_invented_isolated_verified_on_live_clone_fails():
    doc = load_inventory()
    mutated = clone_doc(doc)
    mutated["author_claimed_isolated_run"] = {
        "independently_verified": True,
        "counts": "415 files / 75 batches / 64 passed / 8 failed / 3 timed out / exit 124",
        "test_results": "PASS",
    }
    row = next(item for item in mutated["work_items"] if item["id"] == "nts-io-pr-236")
    row["independently_verified"] = True
    errors = validate_integration_ownership(mutated)
    assert any(
        item.startswith("invented_isolated_verified:") for item in errors
    ), errors


def test_body_sha_as_current_head_on_live_clone_fails():
    doc = load_inventory()
    mutated = clone_doc(doc)
    mutated["CURRENT_INTEGRATION_HEAD"] = AUTHOR_BODY_SHA
    mutated["current_integration"]["head_ref_oid"] = AUTHOR_BODY_SHA
    mutated["reported_vs_live_heads"]["live_oid"] = AUTHOR_BODY_SHA
    errors = validate_integration_ownership(mutated)
    assert any(item.startswith("body_sha_as_live_head:") for item in errors), errors


def test_inventory_is_not_evidence_must_be_true():
    doc = load_inventory()
    mutated = clone_doc(doc)
    mutated["inventory_is_not_evidence"] = False
    errors = validate_integration_ownership(mutated)
    assert "inventory_is_not_evidence_must_be_true" in errors


def test_missing_research_claim_label_fails_when_research_labeled():
    doc = load_inventory()
    mutated = clone_doc(doc)
    del mutated["work_items"][0]["research_claim_label"]
    errors = validate_integration_ownership(mutated)
    assert any(
        item.endswith(".research_claim_label") and item.startswith("missing_field:")
        for item in errors
    )


def test_duplicate_work_item_id_on_live_clone_fails():
    doc = load_inventory()
    mutated = clone_doc(doc)
    mutated["work_items"][1]["id"] = mutated["work_items"][0]["id"]
    errors = validate_integration_ownership(mutated)
    assert any(item.startswith("duplicate_id:") for item in errors), errors


def test_in_memory_nan_and_infinity_rejected():
    doc = load_inventory()
    mutated = clone_doc(doc)
    mutated["current_integration"]["changed_files"] = float("nan")
    mutated["current_integration"]["additions"] = float("inf")
    mutated["work_items"][0]["deletions"] = float("-inf")
    errors = validate_integration_ownership(mutated)
    assert any(
        "changed_files" in item for item in errors if item.startswith("non_finite_number:")
    )
    assert any("additions" in item for item in errors if item.startswith("non_finite_number:"))
    assert any("deletions" in item for item in errors if item.startswith("non_finite_number:"))


def test_secret_pattern_fails_closed():
    doc = load_inventory()
    mutated = clone_doc(doc)
    mutated["work_items"][0]["notes"] = [
        "leaked placeholder sk-proj-FAKESECRET_a1b2c3d4e5f6g7h8i9j0"
    ]
    errors = validate_integration_ownership(mutated)
    assert any(item.startswith("secret:openai_or_anthropic_key:") for item in errors), errors


def test_no_secret_patterns_in_live_inventory():
    errors = validate_integration_ownership(load_inventory())
    assert errors == []
    secret_hits = [item for item in errors if item.startswith("secret:")]
    assert secret_hits == []


def test_deterministic_repeat():
    live = load_inventory()
    first = validate_integration_ownership(live)
    second = validate_integration_ownership(live)
    assert first == second
    assert first == []

    fixture = FIXTURE_DIR / "malformed_synthetic_pass.yaml"
    a = validate_integration_ownership(fixture)
    b = validate_integration_ownership(fixture)
    assert a == b
    assert a

    mutated = clone_doc(live)
    mutated["empirical_pass_from_this_pack"] = True
    mutated["work_items"][0]["id"] = mutated["work_items"][1]["id"]
    run_one = validate_integration_ownership(mutated)
    run_two = validate_integration_ownership(mutated)
    assert run_one == run_two
    assert run_one


def test_raise_on_error_is_fail_closed():
    with pytest.raises(IntegrationOwnershipValidationError) as caught:
        validate_integration_ownership(
            FIXTURE_DIR / "malformed_missing_fields.yaml",
            raise_on_error=True,
        )
    assert caught.value.errors
    assert validate_integration_ownership(load_inventory(), raise_on_error=True) == []


def test_validate_accepts_path_and_mapping():
    from_path = validate(INVENTORY_PATH)
    from_doc = validate(load_inventory())
    assert from_path == from_doc == []


def test_yaml_roundtrip_is_stable():
    text = INVENTORY_PATH.read_text(encoding="utf-8")
    first = yaml.safe_load(text)
    second = yaml.safe_load(text)
    assert first == second
    assert validate_integration_ownership(first) == validate_integration_ownership(second) == []


def test_owned_modules_have_no_network_imports():
    hits: list[str] = []
    for path in OWNED_MODULES:
        hits.extend(collect_forbidden_imports(path))
    assert hits == [], hits


def test_stacked_integrated_only_with_non_main_merge_stays_valid():
    """GitHub merged=true into a non-main base remains INTEGRATED_ONLY, not main."""
    doc = load_inventory()
    row = next(item for item in doc["work_items"] if item["id"] == "nts-io-pr-220")
    assert row["merged"] is True
    assert row["on_origin_main"] is False
    assert row["status"] == "INTEGRATED_ONLY"
    assert row["base_ref_name"] != "main"
    assert validate_integration_ownership(doc) == []
