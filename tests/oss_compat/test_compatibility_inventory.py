"""Consistency checks for docs/oss_compat/compatibility_inventory_20261017.json.

Offline and read-only: loads one JSON file and checks it against the audit's
own rules. Nothing here clones, installs, imports, or executes a candidate.
These are artifact-consistency checks, not scientific validation.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlsplit

_ROOT = Path(__file__).resolve().parents[2]
_INVENTORY = _ROOT / "docs" / "oss_compat" / "compatibility_inventory_20261017.json"
_ALLOWED_EVIDENCE_HOSTS = {"api.github.com", "github.com", "gudhi.inria.fr", "pypi.org"}


def _is_allowed_evidence_url(url: object) -> bool:
    if not isinstance(url, str):
        return False
    try:
        parsed = urlsplit(url)
        return (
            parsed.scheme == "https"
            and parsed.hostname in _ALLOWED_EVIDENCE_HOSTS
            and parsed.username is None
            and parsed.password is None
            and parsed.port is None
            and not parsed.fragment
        )
    except ValueError:
        return False

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
        "openresearch": ("v0.2.21", "2026-10-23", "5af82bb531a731698afc6e8e46f3e5157e20210b"),
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
    assert data["release_revalidated_at_utc"] == "2026-10-23"
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
    # The PyPI project named bids-validator (1.14.x) is a different artifact; the
    # package that tracks tag 3.0.2 is the separate bids-validator-deno wrapper.
    assert "different artifact" in validator["package_channel_note"]
    assert "bids-validator-deno" in validator["package_channel_note"]
    assert validator["package_version"] == "3.0.2"
    assert validator["package_license_evidence_url"] == "https://pypi.org/pypi/bids-validator-deno/3.0.2/json"
    assert validator["package_license_metadata_status"] == "declared_by_pypi_license_expression"
    assert "1.14" not in validator["package_license_declaration"]


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


# --- provenance / schema regressions (2026-10-23 adversarial pass) ------------

_STABLE_ROW_IDS = {
    "openmed",
    "papergym",
    "openresearch",
    "rea",
    "autoresearch",
    "mne-python",
    "mne-bids",
    "moabb",
    "bids-validator",
    "openmeeg",
    "simnibs",
    "neuromaps",
    "netneurotools",
    "neurolib",
    "mne-connectivity",
    "nibabel",
    "datalad",
    "dvc",
    "pyspi",
    "persim",
    "ripser.py",
    "gudhi",
    "giotto-tda",
}
_ADOPTION_GATE_STABLE_IDS = {"openmed", "papergym", "openresearch", "rea", "autoresearch", "gudhi"}
_OVERCLAIM_PHRASES = (
    "legal clearance",
    "legally cleared",
    "blanket package clearance",
    "component clearance",
    "scientifically validated",
    "security cleared",
)


def test_evidence_urls_are_nonempty_https_strings():
    """Empty lists, nulls, or non-HTTPS evidence URLs are schema defects."""
    for candidate in _load()["candidates"]:
        cid = candidate["id"]
        urls = candidate["evidence_urls"]
        assert isinstance(urls, list) and urls, f"{cid}: evidence_urls must be a non-empty list"
        for url in urls:
            assert isinstance(url, str) and url.startswith("https://"), f"{cid}: bad evidence URL {url!r}"
            assert url.strip() == url and " " not in url, f"{cid}: whitespace in evidence URL"


def test_stable_row_ids_are_preserved_for_downstream_gates():
    """#386 documents named-lead IDs plus gudhi; the full 23-row set must stay stable."""
    ids = {c["id"] for c in _load()["candidates"]}
    assert ids == _STABLE_ROW_IDS
    assert _ADOPTION_GATE_STABLE_IDS <= ids
    assert len(_load()["candidates"]) == 23


def test_gudhi_release_evidence_urls_use_literal_upstream_tag_name():
    """The upstream tag literal is tags/gudhi-release-3.13.0; bare gudhi-release-3.13.0 404s."""
    gudhi = _candidate("gudhi")
    release = gudhi["latest_release"]
    assert release["tag"] == "tags/gudhi-release-3.13.0"
    assert release["release_api_url"].endswith("/releases/tags/tags/gudhi-release-3.13.0")
    assert release["tag_ref_api_url"].endswith("/git/ref/tags/tags/gudhi-release-3.13.0")
    evidence = set(gudhi["evidence_urls"])
    assert release["release_api_url"] in evidence
    assert release["tag_ref_api_url"] in evidence
    assert not any(
        url.endswith("/releases/tags/gudhi-release-3.13.0") or url.endswith("/git/ref/tags/gudhi-release-3.13.0")
        for url in evidence
    ), "evidence_urls must not cite the 404 bare-tag API paths"


def test_gudhi_component_licensing_remains_explicitly_unresolved():
    """Repository MIT must not be collapsed into package/component clearance (#375 alignment)."""
    gudhi = _candidate("gudhi")
    caveat = gudhi["component_license_caveat"].lower()
    spdx = gudhi["license_spdx_or_text"].lower()
    assert "unresolved" in caveat or "unresolved" in spdx
    assert "not assessed" in caveat or "not assessed" in spdx or "legal compatibility not assessed" in caveat
    assert gudhi["license_status"] == "permissive_custom_review_required"
    assert gudhi["disposition"] == "integrate_behind_bounded_adapter"
    assert "module_specific_dependency_scope_review" in gudhi["adoption_prerequisites"]
    joined = " ".join(
        str(gudhi.get(key, ""))
        for key in (
            "disposition_rationale",
            "license_spdx_or_text",
            "component_license_caveat",
            "security_privacy_notes",
            "maintenance_signal",
        )
    ).lower()
    for phrase in _OVERCLAIM_PHRASES:
        assert phrase not in joined, f"gudhi overclaims with {phrase!r}"


def test_gudhi_release_pin_matches_merged_batch3_registry_tag():
    """Keep the #375 pin (tags/gudhi-release-3.13.0 / 3.13.0); do not silently retarget."""
    gudhi = _candidate("gudhi")
    assert gudhi["package_version"] == "3.13.0"
    assert gudhi["latest_release"]["tag"] == "tags/gudhi-release-3.13.0"
    assert gudhi["latest_release"]["published_utc"] == "2026-07-02"
    assert gudhi["latest_release"]["commit_sha"] == "5dbe510bed5d8d700ec7243fd915769fb67964a2"


def test_inventory_base_and_current_main_shas_are_full_hex_and_cited_in_audit():
    data = _load()
    base_sha = data["base_main_sha"]
    current_sha = data["current_main_sha"]
    assert re.fullmatch(r"[0-9a-f]{40}", base_sha)
    assert re.fullmatch(r"[0-9a-f]{40}", current_sha)
    assert base_sha == "648e5e4fb67e9e7c399c78c00b1a139f83db2b36"
    assert current_sha == "6136cb3fe3bc97e811f494a853f471988ce976bb"
    audit = (_ROOT / "docs" / "oss_compat" / "batch1_compatibility_audit_20261017.md").read_text(encoding="utf-8")
    assert base_sha in audit
    assert current_sha in audit


def test_neuromaps_conflict_is_not_silently_cleared():
    neuromaps = _candidate("neuromaps")
    assert neuromaps["package_license_metadata_status"] == "conflicting_pypi_metadata"
    assert neuromaps["license_status"] == "non_commercial_conflict"
    assert neuromaps["disposition"] == "reference_only"
    declaration = neuromaps["package_license_declaration"].lower()
    assert "noncommercial" in declaration or "non-commercial" in declaration
    assert "bsd" in declaration
    joined = " ".join(
        str(neuromaps.get(key, ""))
        for key in ("disposition_rationale", "license_spdx_or_text", "package_license_declaration")
    ).lower()
    for phrase in ("legal clearance", "resolved in favor", "bsd-cleared", "scientifically validated"):
        assert phrase not in joined


def test_bids_validator_runtime_is_deno_not_node():
    """Tag 3.0.2 ships deno.json (@bids/validator) and a `deno run` README; it is not a Node package."""
    validator = _candidate("bids-validator")
    runtime = validator["runtime_requirements"]
    assert "Deno" in runtime
    assert "Node" not in runtime and "Node" not in validator["disposition_rationale"]
    assert "Node" not in validator["package_channel_note"]
    assert validator["disposition"] == "reference_only"
    assert "wrapper" in validator["package_channel_note"] and "not inspected" in validator["package_channel_note"]


def test_revalidated_openresearch_release_is_resolved_without_moving_head_snapshot():
    """Revalidation resolves the newer tag, without retargeting the historical head snapshot."""
    openresearch = _candidate("openresearch")
    release = openresearch["latest_release"]
    assert openresearch["head_sha"] == "6285fee7f42bc8ad21500b84278d38679f1ac01b"
    assert release["tag"] == "v0.2.21"
    assert release["published_utc"] == "2026-10-23"
    assert release["commit_sha"] == "5af82bb531a731698afc6e8e46f3e5157e20210b"
    assert release["release_api_url"] == "https://api.github.com/repos/alphaXiv/OpenResearch/releases/tags/v0.2.21"
    assert release["tag_ref_api_url"] == "https://api.github.com/repos/alphaXiv/OpenResearch/git/ref/tags/v0.2.21"
    assert openresearch["evidence_urls"]
    assert release["release_api_url"] in openresearch["evidence_urls"]
    assert release["tag_ref_api_url"] in openresearch["evidence_urls"]
    for candidate in _load()["candidates"]:
        assert "newer_release_observed" not in candidate, candidate["id"]


def test_evidence_urls_require_an_exact_allowed_https_authority():
    """An allowed hostname embedded in userinfo or a suffix is not the authority."""
    data = _load()
    for candidate in data["candidates"]:
        for url in candidate["evidence_urls"]:
            assert _is_allowed_evidence_url(url), f"{candidate['id']}: invalid evidence authority"
    assert not _is_allowed_evidence_url("https://github.com@evil.example/owner/repo")
    assert not _is_allowed_evidence_url("https://github.com.evil.example/owner/repo")
    assert not _is_allowed_evidence_url("http://github.com/owner/repo")
    assert not _is_allowed_evidence_url("https://github.com/owner/repo#fragment")
    assert not _is_allowed_evidence_url("https://github.com:443/owner/repo")
    assert not _is_allowed_evidence_url("https://github.com.unknown/owner/repo")


def test_cross_registry_notes_keep_conflicts_visible_without_copying_verdicts():
    data = _load()
    notes = data["cross_registry_notes"]
    ids = {c["id"] for c in data["candidates"]}
    assert notes, "cross-registry observations must be recorded"
    for note in notes:
        assert note["inventory_id"] in ids, note
        assert note["registry"] == "configs/research/batch3_source_registry.yaml (PR #375, merged)"
        assert note["registry_not_edited"] is True
        assert note["verdict_not_copied"] is True
    by_id = {n["inventory_id"]: n for n in notes}
    assert "rea-agents-6.5.0" in by_id["rea"]["observation"] and "rea-agents-6.7.0" in by_id["rea"]["observation"]
    assert "ripser-py" in by_id["ripser.py"]["observation"]
    assert "EMULATE" in by_id["gudhi"]["observation"] and "integrate_behind_bounded_adapter" in by_id["gudhi"]["observation"]


def test_gudhi_bare_tag_evidence_paths_are_absent_and_literal_tag_paths_present():
    gudhi = _candidate("gudhi")
    joined = " ".join(gudhi["evidence_urls"]) + " " + json.dumps(gudhi["latest_release"])
    assert "/tags/tags/gudhi-release-3.13.0" in joined
    assert not re.search(r"/(releases/tags|git/ref/tags)/gudhi-release-3\.13\.0", joined)


def test_inventory_declares_revalidated_and_unresolved_link_scopes():
    note = _load()["link_resolution_scope"]
    assert "HTTP 200" in note
    assert "GitHub REST latest-release and exact-tag-ref records were queried" in note
    assert "rather than by the file-resolution procedure" in note
    assert "does not establish" in note
