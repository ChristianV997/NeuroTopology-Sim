from __future__ import annotations

from oss_opportunities.license_review import RepositoryLicenseReviewV1, classify_license_risk, compute_license_review_id


def _make(license_spdx: str = "MIT", **overrides):
    kwargs = dict(
        repo_full_name="a/b", license_spdx=license_spdx, license_name=license_spdx,
        provenance="synthetic fixture", limitations=["synthetic fixture only"],
    )
    kwargs.update(overrides)
    return RepositoryLicenseReviewV1.make(**kwargs)


def test_permissive_license_allows_adapter_and_reference_modes():
    r = _make("MIT")
    assert r.license_risk == "permissive_low"
    assert r.commercial_core_policy == "allowed_with_attribution"
    assert "adapter_only" in r.allowed_use_modes
    assert r.validate() == []


def test_agpl_blocks_commercial_core_copy():
    r = _make("AGPL-3.0")
    assert r.license_risk == "strong_copyleft_high"
    assert r.commercial_core_policy != "allowed_with_attribution"
    assert "commercial_core_copy" in r.blocked_use_modes
    assert r.validate() == []


def test_gpl_blocks_commercial_core_copy():
    r = _make("GPL-3.0")
    assert r.license_risk == "strong_copyleft_high"
    assert r.commercial_core_policy != "allowed_with_attribution"


def test_fair_code_source_available_blocks_commercial_core_copy():
    r = _make("BSL-1.1")
    assert r.license_risk == "source_available_or_fair_code_high"
    assert r.commercial_core_policy != "allowed_with_attribution"
    assert "commercial_core_copy" in r.blocked_use_modes


def test_unknown_license_blocks_copy():
    r = _make("unknown")
    assert r.license_risk == "missing_high"
    assert r.commercial_core_policy == "blocked_pending_review"


def test_missing_license_blocks_copy():
    r = _make("")
    assert r.license_risk == "missing_high"


def test_attribution_requirement_recorded():
    r = _make("MIT")
    assert r.attribution_required is True


def test_license_review_id_deterministic():
    id1 = compute_license_review_id(repo_full_name="a/b", license_spdx="MIT")
    id2 = compute_license_review_id(repo_full_name="a/b", license_spdx="MIT")
    assert id1 == id2
    id3 = compute_license_review_id(repo_full_name="a/b", license_spdx="AGPL-3.0")
    assert id1 != id3


def test_classify_license_risk_direct():
    assert classify_license_risk("MIT") == "permissive_low"
    assert classify_license_risk("Apache-2.0") == "permissive_low"
    assert classify_license_risk("LGPL-2.1") == "weak_copyleft_medium"
    assert classify_license_risk("GPL-2.0") == "strong_copyleft_high"
    assert classify_license_risk("AGPL-3.0") == "strong_copyleft_high"
    assert classify_license_risk("SSPL-1.0") == "source_available_or_fair_code_high"
    assert classify_license_risk("proprietary") == "proprietary_or_unknown_high"
    assert classify_license_risk("") == "missing_high"
    assert classify_license_risk(None) == "missing_high"


def test_dict_roundtrip():
    r = _make("MIT")
    d = r.to_dict()
    r2 = RepositoryLicenseReviewV1.from_dict(d)
    assert r2.to_dict() == d


def test_tampered_agpl_with_copy_permitting_policy_fails_validation():
    r = _make("AGPL-3.0")
    r.commercial_core_policy = "allowed_with_attribution"
    errs = r.validate()
    assert any("rule 8" in e for e in errs)


def test_missing_limitations_fails():
    r = _make("MIT")
    r.limitations = []
    assert any("limitations" in e for e in r.validate())


def test_missing_provenance_fails():
    r = _make("MIT")
    r.provenance = ""
    assert any("provenance" in e for e in r.validate())
