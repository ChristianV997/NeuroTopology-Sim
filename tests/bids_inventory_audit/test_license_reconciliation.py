"""License evidence: agreement, conflict, and unknown values stay unresolved. Nothing is adjudicated."""
from __future__ import annotations

import pytest

from shared.bids_inventory_audit import license_report, metadata_evidence, readme_evidence, reconcile_license


def _codes(report):
    return [f["code"] for f in report["findings"]]


def _assert_open(report):
    assert report["resolved"] is False
    assert report["adjudicated"] is False
    assert report["selected_license"] is None
    assert report["legal_adjudication"] == "NOT_PERFORMED"


def test_fixture_readme_and_metadata_conflict_remains_unresolved(synthetic_readme, synthetic_nemar):
    report = license_report(synthetic_readme, synthetic_nemar)
    assert report["state"] == "CONFLICT_UNRESOLVED"
    assert report["tokens"] == ["CC-BY-4.0", "CC0-1.0"]
    assert "LICENSE_CONFLICT_UNRESOLVED" in _codes(report)
    _assert_open(report)


def test_single_recognized_source_is_not_adjudicated():
    report = license_report("License: CC-BY-4.0", None)
    assert report["state"] == "SINGLE_SOURCE_NOT_ADJUDICATED"
    assert report["tokens"] == ["CC-BY-4.0"]
    _assert_open(report)


def test_agreement_between_sources_is_recorded_but_not_adjudicated():
    report = license_report("License: CC0-1.0", {"License": "CC0"})
    assert report["state"] == "AGREEMENT_NOT_ADJUDICATED"
    assert "LICENSE_NOT_ADJUDICATED" in _codes(report)
    _assert_open(report)


def test_missing_source_is_not_counted_as_corroboration():
    report = license_report("License: CC0", None)
    assert report["state"] == "SINGLE_SOURCE_NOT_ADJUDICATED"


def test_no_evidence_at_all_is_unknown_with_a_warning():
    report = license_report(None, None)
    assert report["state"] == "UNKNOWN"
    assert "LICENSE_UNKNOWN" in _codes(report)
    _assert_open(report)


def test_stray_token_on_a_non_license_line_does_not_create_a_conflict():
    readme = "Data were contributed by CC0 projects.\nLicense: CC-BY-4.0\n"
    report = license_report(readme, None)
    assert report["tokens"] == ["CC-BY-4.0"]
    assert report["state"] == "SINGLE_SOURCE_NOT_ADJUDICATED"


def test_two_tokens_on_license_lines_of_one_source_is_a_within_source_conflict():
    readme = "License: CC0 for the code, CC-BY-4.0 for the data\n"
    report = license_report(readme, None)
    assert readme_evidence(readme)["status"] == "CONFLICT_WITHIN_SOURCE"
    assert report["state"] == "CONFLICT_UNRESOLVED"
    _assert_open(report)


def test_license_line_with_no_recognized_token_is_unresolved_not_guessed():
    report = license_report("License: see the LICENSE file in the archive", None)
    assert readme_evidence("License: see the LICENSE file in the archive")["status"] == "UNRECOGNIZED_LICENSE_TEXT"
    assert report["state"] == "UNRESOLVED"
    assert "LICENSE_UNRESOLVED" in _codes(report)


def test_custom_license_name_is_never_mapped_to_a_known_token():
    assert metadata_evidence({"License": "Custom-Research-1.0"})["status"] == "UNRECOGNIZED_LICENSE_TEXT"


def test_readme_without_a_license_statement_does_not_infer_one():
    evidence = readme_evidence("Mentions CC-BY-4.0 in a citation only.\nData were collected in 2020.\n")
    assert evidence["status"] == "NO_LICENSE_STATEMENT"
    assert evidence["tokens"] == []


def test_metadata_without_any_license_field_is_unresolved_alongside_a_readme_token():
    report = license_report("License: CC-BY-4.0", {"name": "SYNTHETIC"})
    assert metadata_evidence({"name": "SYNTHETIC"})["status"] == "NO_LICENSE_FIELD"
    assert report["state"] == "UNRESOLVED"


@pytest.mark.parametrize("value", [["CC0"], 0, None, {"nested": "CC0"}])
def test_non_text_license_value_is_unresolved(value):
    assert metadata_evidence({"License": value})["status"] == "NOT_TEXT"


def test_two_license_fields_naming_different_tokens_conflict_within_metadata():
    evidence = metadata_evidence({"License": "CC0", "license": "CC-BY-4.0"})
    assert evidence["status"] == "CONFLICT_WITHIN_SOURCE"


def test_share_alike_variant_is_a_distinct_token_not_agreement():
    report = license_report("License: CC-BY-SA-4.0", {"License": "CC-BY-4.0"})
    assert report["state"] == "CONFLICT_UNRESOLVED"
    assert report["tokens"] == ["CC-BY-4.0", "CC-BY-SA-4.0"]


@pytest.mark.parametrize("statement, token", [
    ("License: cc by 4.0", "CC-BY-4.0"),
    ("License: CC BY 4.0", "CC-BY-4.0"),
    ("License: CC-BY-4.0", "CC-BY-4.0"),
    ("License: CCBY4.0", "CC-BY-4.0"),
    ("License: CC0", "CC0-1.0"),
    ("License: CC0 1.0", "CC0-1.0"),
    ("License: cc-by-sa 4.0", "CC-BY-SA-4.0"),
])
def test_common_spellings_map_to_one_closed_token(statement, token):
    evidence = readme_evidence(statement)
    assert evidence["status"] == "RECOGNIZED"
    assert evidence["tokens"] == [token]


def test_reconciliation_never_selects_a_license_even_when_one_source_seems_authoritative():
    report = reconcile_license([
        {"source": "readme", "status": "RECOGNIZED", "tokens": ["CC-BY-4.0"]},
        {"source": "metadata", "status": "RECOGNIZED", "tokens": ["CC0-1.0"]},
    ])
    assert report["state"] == "CONFLICT_UNRESOLVED"
    assert report["selected_license"] is None
    _assert_open(report)


@pytest.mark.parametrize("readme, metadata", [
    ("License: CC-BY-4.0", {"License": "CC0"}),
    (None, {"License": "CC0"}),
    ("License: nonsense", None),
    ("nothing", {"name": "x"}),
    (None, None),
])
def test_every_license_outcome_is_open(readme, metadata):
    _assert_open(license_report(readme, metadata))
