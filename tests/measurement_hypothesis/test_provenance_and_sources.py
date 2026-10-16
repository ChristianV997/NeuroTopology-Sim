"""Source references must carry an exact version, an https URL, and an access date."""
from __future__ import annotations

import pytest


def _codes(report):
    return {error["code"] for error in report["errors"]}


def _source(mapping, source_id):
    return next(item for item in mapping["sources"] if item["source_id"] == source_id)


def test_missing_provenance_fixture_is_rejected(load_fixture, check):
    report = check(load_fixture("missing_provenance"))
    assert report["contract_status"] == "REJECTED"
    assert {"SOURCE_FIELD_MISSING", "SOURCE_URI_NOT_HTTPS"} <= _codes(report)
    paths = {error["path"] for error in report["errors"]}
    assert "$.sources[0].accessed" in paths
    assert "$.sources[0].uri" in paths


def test_missing_access_date_is_rejected(valid_mapping, check):
    del _source(valid_mapping, "stam2007")["accessed"]
    report = check(valid_mapping)
    assert {"code": "SOURCE_FIELD_MISSING", "path": "$.sources[3].accessed",
            "message": "source reference lacks accessed"} in report["errors"]


def test_missing_version_is_rejected(valid_mapping, check):
    _source(valid_mapping, "nolte2004")["version"] = "  "
    assert "SOURCE_FIELD_MISSING" in _codes(check(valid_mapping))


def test_mapping_without_any_source_is_rejected(valid_mapping, check):
    valid_mapping["sources"] = []
    report = check(valid_mapping)
    assert "SOURCE_REFERENCES_MISSING" in _codes(report)


def test_interpretation_citing_an_undeclared_source_is_rejected(valid_mapping, check):
    valid_mapping["interpretation"]["source_ids"].append("ghost_source")
    report = check(valid_mapping)
    assert "SOURCE_UNRESOLVED" in _codes(report)


@pytest.mark.parametrize("uri", ["http://doi.org/10.1002/hbm.20346", "doi:10.1002/hbm.20346", "ftp://example.org/x"])
def test_non_https_source_uri_is_rejected(valid_mapping, check, uri):
    _source(valid_mapping, "stam2007")["uri"] = uri
    assert "SOURCE_URI_NOT_HTTPS" in _codes(check(valid_mapping))


def test_access_date_after_validation_date_is_rejected(valid_mapping, check):
    _source(valid_mapping, "stam2007")["accessed"] = "2099-01-01"
    assert "SOURCE_ACCESS_IN_FUTURE" in _codes(check(valid_mapping))


def test_unparseable_access_date_is_rejected(valid_mapping, check):
    _source(valid_mapping, "stam2007")["accessed"] = "16/10/2026"
    assert "SOURCE_DATE_INVALID" in _codes(check(valid_mapping))


def test_unparseable_publication_date_is_rejected(valid_mapping, check):
    _source(valid_mapping, "stam2007")["published"] = "autumn 2007"
    assert "SOURCE_DATE_INVALID" in _codes(check(valid_mapping))


def test_unknown_verification_level_is_rejected(valid_mapping, check):
    _source(valid_mapping, "stam2007")["verification"] = "trust_me"
    assert "SOURCE_VERIFICATION_UNKNOWN" in _codes(check(valid_mapping))


def test_duplicate_source_identifier_is_rejected(valid_mapping, check):
    valid_mapping["sources"].append(dict(_source(valid_mapping, "stam2007")))
    assert "SOURCE_ID_DUPLICATE" in _codes(check(valid_mapping))


def test_theory_term_without_a_source_is_rejected(valid_mapping, check):
    valid_mapping["interpretation"]["theory_term"] = "UTTL.phase_circulation"
    valid_mapping["interpretation"]["source_ids"] = []
    assert "THEORY_TERM_WITHOUT_SOURCE" in _codes(check(valid_mapping))
