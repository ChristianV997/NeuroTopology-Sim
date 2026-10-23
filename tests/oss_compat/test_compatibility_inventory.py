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
    assert data["schema_version"] == "2"
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


def test_revalidated_release_tags_match_primary_upstream_records():
    candidates = {c["id"]: c for c in _load()["candidates"]}
    expected_releases = {
        "openresearch": ("v0.2.20", "2026-10-21", "37a367bcdbc26ba2a492bccf12b85bddc5852567"),
        "rea": ("rea-agents-6.7.0", "2026-10-18", "27dc42d10249f0410904a75c0997842eb03b931c"),
        "persim": ("v0.4.1", "2026-10-18", "00144a82949c214283655f68d1985725882eea59"),
        "gudhi": ("tags/gudhi-release-3.13.0", "2026-07-02", "5dbe510bed5d8d700ec7243fd915769fb67964a2"),
    }
    for candidate_id, (tag, published, commit) in expected_releases.items():
        release = candidates[candidate_id]["latest_release"]
        assert release["tag"] == tag
        assert release["published_utc"] == published
        assert release["commit_sha"] == commit
        assert re.fullmatch(r"[0-9a-f]{40}", release["commit_sha"])
        assert release["release_api_url"].startswith("https://api.github.com/repos/")
        assert release["tag_ref_api_url"].startswith("https://api.github.com/repos/")


def test_inventory_distinguishes_historical_snapshot_from_revalidated_releases():
    data = _load()
    assert data["retrieval_date_utc"] == "2026-10-17"
    assert data["release_revalidated_at_utc"] == "2026-10-22"
    assert "not install pins" in data["release_revalidation_method"]
    assert "not imply compatibility" in data["release_scope_note"]


def test_gudhi_repository_license_is_not_presented_as_package_or_component_clearance():
    gudhi = next(c for c in _load()["candidates"] if c["id"] == "gudhi")
    assert gudhi["github_license_label"] == "MIT"
    assert gudhi["package_version"] == "3.13.0"
    assert gudhi["package_license_metadata_status"] == "not_declared"
    assert gudhi["package_license_declaration"] is None
    assert gudhi["license_status"] == "permissive_custom_review_required"
    assert "license_review" in gudhi["adoption_prerequisites"]
    assert "module_specific_dependency_scope_review" in gudhi["adoption_prerequisites"]
    caveat = gudhi["component_license_caveat"]
    assert "GPLv3" in caveat and "LGPL" in caveat
    assert "repository-level" in _load()["license_scope_note"]
    assert "transitive-dependency" in _load()["license_scope_note"]
    assert "https://gudhi.inria.fr/licensing/" in gudhi["evidence_urls"]
    assert "https://pypi.org/pypi/gudhi/3.13.0/json" in gudhi["evidence_urls"]
    assert gudhi["latest_release"]["release_api_url"].endswith("/releases/tags/tags/gudhi-release-3.13.0")
    assert gudhi["latest_release"]["tag_ref_api_url"].endswith("/git/ref/tags/tags/gudhi-release-3.13.0")


def test_persim_package_license_evidence_is_separate_from_repository_license_label():
    persim = next(c for c in _load()["candidates"] if c["id"] == "persim")
    assert persim["github_license_label"] == "MIT"
    assert persim["package_version"] == "0.4.1"
    assert persim["package_license_metadata_status"] == "declared_by_pypi_classifier"
    assert "OSI Approved :: MIT License" in persim["package_license_declaration"]
    assert persim["package_license_evidence_url"] == "https://pypi.org/project/persim/0.4.1/"


# --- source-backed field checks (package/version/license/overlap) -------------

_PACKAGE_FIELDS = {
    "package_version",
    "package_license_declaration",
    "package_license_metadata_status",
    "package_license_evidence_url",
}
_PACKAGE_METADATA_STATUSES = {
    "declared_by_pypi_classifier",
    "declared_by_pypi_license_expression",
    "declared_by_pypi_license_field",
    "conflicting_pypi_metadata",
    "not_declared",
}
_IMPORT_NAMES = {"persim": "persim", "ripser.py": "ripser", "gudhi": "gudhi", "nibabel": "nibabel"}


def _candidate(candidate_id: str) -> dict:
    return next(c for c in _load()["candidates"] if c["id"] == candidate_id)


def _cited_repo_paths(candidate: dict) -> list[str]:
    paths = []
    for entry in candidate["existing_overlap"]:
        for token in re.findall(r"[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)+\.py", entry):
            paths.append(token)
    return paths


def test_every_license_claim_has_an_evidence_url():
    for candidate in _load()["candidates"]:
        url = candidate["license_evidence_url"]
        if candidate["license_status"] == "missing":
            assert url is None, f"{candidate['id']}: a missing license has no license file to cite"
            continue
        assert isinstance(url, str) and url.startswith("https://"), candidate["id"]


def test_package_fields_are_all_or_nothing_and_use_known_statuses():
    for candidate in _load()["candidates"]:
        present = _PACKAGE_FIELDS & set(candidate)
        if not present:
            continue
        cid = candidate["id"]
        assert present == _PACKAGE_FIELDS, f"{cid}: partial package metadata {sorted(present)}"
        assert candidate["package_license_metadata_status"] in _PACKAGE_METADATA_STATUSES, cid
        assert candidate["package_license_evidence_url"].startswith("https://pypi.org/"), cid
        if candidate["package_license_metadata_status"] == "not_declared":
            assert candidate["package_license_declaration"] is None, cid
        else:
            assert candidate["package_license_declaration"], cid


def test_overlap_paths_cited_for_a_library_actually_mention_that_library():
    for candidate_id, module_name in _IMPORT_NAMES.items():
        for relative in _cited_repo_paths(_candidate(candidate_id)):
            source = _ROOT / relative
            assert source.is_file(), f"{candidate_id}: cited path {relative} does not exist"
            text = source.read_text(encoding="utf-8")
            uses_module = re.search(
                rf"^\s*(?:import|from)\s+{module_name}\b|available\(\s*[\"']{module_name}[\"']",
                text,
                re.MULTILINE,
            )
            assert uses_module, f"{candidate_id}: cited path {relative} never imports {module_name}"


def test_persim_maintenance_signal_matches_its_latest_release():
    persim = _candidate("persim")
    assert persim["latest_release"]["tag"] == "v0.4.1"
    assert "2025-03-12" not in persim["maintenance_signal"]
    assert "v0.4.1" in persim["maintenance_signal"]
    assert "2026-10-18" in persim["maintenance_signal"]
    assert persim["license_evidence_url"].endswith("/LICENSE.txt")


def test_bundled_third_party_terms_are_not_collapsed_into_a_single_mit_label():
    nibabel = _candidate("nibabel")
    assert nibabel["license_status"] == "permissive"
    caveat = nibabel["component_license_caveat"]
    assert "3rd party" in caveat and "PDDL" in caveat and "template" in caveat
    assert "not been reviewed" in caveat or "not reviewed" in caveat
    datalad = _candidate("datalad")
    caveat = datalad["component_license_caveat"]
    assert "BSD" in caveat and "git-annex" in caveat
    assert "not been reviewed" in caveat or "not reviewed" in caveat


def test_nibabel_package_and_release_channels_are_distinguished():
    nibabel = _candidate("nibabel")
    assert nibabel["package_version"] == "5.4.2"
    assert nibabel["latest_release"]["tag"] == "5.4.1"
    assert "5.4.2" in nibabel["maintenance_signal"]
    assert nibabel["package_license_metadata_status"] == "declared_by_pypi_license_expression"
    assert not any("10 Python modules" in entry for entry in nibabel["existing_overlap"])


def test_conflicting_package_metadata_is_recorded_not_resolved():
    neuromaps = _candidate("neuromaps")
    assert neuromaps["package_license_metadata_status"] == "conflicting_pypi_metadata"
    assert "NonCommercial" in neuromaps["package_license_declaration"]
    assert "BSD" in neuromaps["package_license_declaration"]
    assert neuromaps["license_status"] == "non_commercial_conflict"
    assert neuromaps["disposition"] == "reference_only"


def test_non_pypi_release_channels_do_not_masquerade_as_package_versions():
    neurolib = _candidate("neurolib")
    assert neurolib["latest_release"]["tag"] == "v0.7.0"
    assert neurolib["package_version"] == "0.6.2"
    assert "no PyPI release" in neurolib["package_channel_note"]
    validator = _candidate("bids-validator")
    assert "package_version" not in validator
    assert "different artifact" in validator["package_channel_note"]


def test_giotto_and_pyspi_license_text_match_primary_declarations():
    giotto = _candidate("giotto-tda")
    assert giotto["package_version"] == "0.6.2"
    assert "AGPL" in giotto["package_license_declaration"]
    pyspi = _candidate("pyspi")
    assert "README and API" not in pyspi["license_spdx_or_text"]
    assert "GPL" in pyspi["license_spdx_or_text"]
    assert pyspi["license_status"] == "copyleft_strong"


def test_scope_note_keeps_security_maintenance_legal_and_science_separate():
    note = _load()["license_scope_note"]
    for phrase in ("security posture", "maintenance quality", "compatibility", "legal clearance", "scientific validity"):
        assert phrase in note
