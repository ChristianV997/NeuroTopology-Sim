"""Consistency checks for docs/oss_compat/compatibility_inventory_20261017.json.

Offline and read-only: loads one JSON file and checks it against the audit's
own rules. Nothing here clones, installs, imports, or executes a candidate.
These are artifact-consistency checks, not scientific validation.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
_INVENTORY = _ROOT / "docs" / "oss_compat" / "compatibility_inventory_20261017.json"

_DISPOSITIONS = {
    "integrate_behind_bounded_adapter",
    "emulate_narrow_pattern",
    "copy_pattern_after_review",
    "reference_only",
    "reject_or_defer",
}
_LICENSE_STATUSES = {
    "permissive",
    "permissive_custom_review_required",
    "copyleft_strong",
    "copyleft_weak",
    "dual_licensed_copyleft",
    "non_commercial_conflict",
    "missing",
}
_RESTRICTED_LICENSES = {"missing", "copyleft_strong", "non_commercial_conflict", "dual_licensed_copyleft"}
_NEED_AREAS = {
    "eeg_bids_handling",
    "signal_processing_forward_model",
    "synthetic_validation_surrogates",
    "topology_geometry",
    "research_agent_reproducibility",
    "out_of_scope",
}
_ROLE_CLASSES = {
    "research_workflow_tool",
    "scientific_runtime_dependency",
    "scientific_data_standard_tool",
    "reference_method_or_pattern",
    "out_of_domain_tool",
}
_SOURCE_CATEGORIES = {"named_lead", "existing_repo_dependency", "scientific_candidate"}
_REQUIRED_FIELDS = {
    "id",
    "canonical_repo",
    "canonical_url",
    "source_category",
    "role_class",
    "need_area",
    "default_branch",
    "head_sha",
    "last_commit_utc",
    "latest_release",
    "archived",
    "github_license_label",
    "license_spdx_or_text",
    "license_status",
    "license_evidence_level",
    "license_evidence_url",
    "capability_evidence",
    "maintenance_signal",
    "runtime_requirements",
    "security_privacy_notes",
    "existing_overlap",
    "disposition",
    "disposition_rationale",
    "adoption_prerequisites",
    "evidence_urls",
    "proof_test",
}
_NAMED_LEADS = {"openmed", "papergym", "openresearch", "rea", "autoresearch"}
_STALE_BEFORE = "2025-01-01"


def _load() -> dict:
    return json.loads(_INVENTORY.read_text(encoding="utf-8"))


def test_inventory_is_valid_json_with_hold_status():
    data = _load()
    assert data["project_status"] == "HOLD / SYNTHETIC_ONLY"
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", data["retrieval_date_utc"])
    assert set(data["allowed_dispositions"]) == _DISPOSITIONS


def test_every_candidate_has_required_fields_and_unique_ids():
    candidates = _load()["candidates"]
    ids = [c["id"] for c in candidates]
    assert len(ids) == len(set(ids)), "candidate ids must be unique"
    for candidate in candidates:
        missing = _REQUIRED_FIELDS - set(candidate)
        assert not missing, f"{candidate.get('id')}: missing {sorted(missing)}"


def test_head_sha_is_full_hex_and_url_matches_repo():
    for candidate in _load()["candidates"]:
        assert re.fullmatch(r"[0-9a-f]{40}", candidate["head_sha"]), candidate["id"]
        assert candidate["canonical_url"] == f"https://github.com/{candidate['canonical_repo']}", candidate["id"]


def test_vocabularies_are_allowed_values():
    for candidate in _load()["candidates"]:
        cid = candidate["id"]
        assert candidate["disposition"] in _DISPOSITIONS, cid
        assert candidate["license_status"] in _LICENSE_STATUSES, cid
        assert candidate["need_area"] in _NEED_AREAS, cid
        assert candidate["role_class"] in _ROLE_CLASSES, cid
        assert candidate["source_category"] in _SOURCE_CATEGORIES, cid
        assert candidate["evidence_urls"], f"{cid}: needs at least one evidence URL"


def test_integrate_requires_permissive_license_or_explicit_license_review():
    for candidate in _load()["candidates"]:
        if candidate["disposition"] != "integrate_behind_bounded_adapter":
            continue
        cid = candidate["id"]
        permissive = candidate["license_status"] == "permissive"
        reviewed = (
            candidate["license_status"] == "permissive_custom_review_required"
            and "license_review" in candidate["adoption_prerequisites"]
        )
        assert permissive or reviewed, f"{cid}: integrate without permissive license or license_review"


def test_restricted_licenses_never_recommend_code_copy():
    for candidate in _load()["candidates"]:
        if candidate["license_status"] in _RESTRICTED_LICENSES:
            assert candidate["disposition"] in {"reference_only", "reject_or_defer", "emulate_narrow_pattern"}, candidate["id"]


def test_integrate_excludes_stale_and_workflow_tools():
    for candidate in _load()["candidates"]:
        if candidate["disposition"] != "integrate_behind_bounded_adapter":
            continue
        cid = candidate["id"]
        assert candidate["last_commit_utc"] >= _STALE_BEFORE, f"{cid}: integrate on a stale repository"
        assert candidate["role_class"] != "research_workflow_tool", f"{cid}: workflow tool as runtime dependency"


def test_research_workflow_tools_stay_in_reproducibility_need():
    for candidate in _load()["candidates"]:
        if candidate["role_class"] == "research_workflow_tool":
            assert candidate["need_area"] == "research_agent_reproducibility", candidate["id"]


def test_existing_dependencies_cite_in_repo_overlap():
    for candidate in _load()["candidates"]:
        if candidate["source_category"] == "existing_repo_dependency":
            assert candidate["existing_overlap"], f"{candidate['id']}: existing dependency without overlap evidence"


def test_out_of_scope_candidates_are_rejected_or_referenced_only():
    for candidate in _load()["candidates"]:
        if candidate["need_area"] == "out_of_scope":
            assert candidate["disposition"] in {"reject_or_defer", "reference_only"}, candidate["id"]


def test_all_named_leads_are_present():
    ids = {c["id"] for c in _load()["candidates"]}
    assert _NAMED_LEADS <= ids
