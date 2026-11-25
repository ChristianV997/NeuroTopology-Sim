"""Four license sources are reconciled without preferring any. Each disagreement stays traceable to its source."""
from __future__ import annotations

import pytest

from shared.bids_inventory_audit import audit_inventory, license_report


def _codes(report):
    return [f["code"] for f in report["findings"]]


def _assert_open(report):
    assert report["resolved"] is False
    assert report["adjudicated"] is False
    assert report["selected_license"] is None
    assert report["legal_adjudication"] == "NOT_PERFORMED"


def test_four_source_fixture_keeps_every_disagreement_by_source(synthetic_readme, synthetic_nemar,
                                                                synthetic_dataset_description, synthetic_catalog):
    report = license_report(synthetic_readme, synthetic_nemar,
                            dataset_description=synthetic_dataset_description,
                            catalog_metadata=synthetic_catalog)
    assert report["state"] == "CONFLICT_UNRESOLVED"
    assert report["tokens"] == ["CC-BY-4.0", "CC-BY-SA-4.0", "CC0-1.0"]
    assert report["sources_by_token"] == {
        "CC-BY-4.0": ["dataset_description", "readme"],
        "CC-BY-SA-4.0": ["catalog_metadata"],
        "CC0-1.0": ["nemar_metadata"],
    }
    assert "LICENSE_CONFLICT_UNRESOLVED" in _codes(report)
    _assert_open(report)


def test_dataset_description_agreeing_with_readme_is_recorded_not_adjudicated(synthetic_readme,
                                                                              synthetic_dataset_description):
    report = license_report(synthetic_readme, None, dataset_description=synthetic_dataset_description)
    assert report["state"] == "AGREEMENT_NOT_ADJUDICATED"
    assert report["sources_by_token"] == {"CC-BY-4.0": ["dataset_description", "readme"]}
    assert "LICENSE_NOT_ADJUDICATED" in _codes(report)
    _assert_open(report)


def test_dataset_description_without_a_license_field_is_unresolved_not_a_conflict(synthetic_readme):
    report = license_report(synthetic_readme, None, dataset_description={"Name": "SYNTHETIC"})
    assert report["state"] == "UNRESOLVED"
    assert "LICENSE_CONFLICT_UNRESOLVED" not in _codes(report)
    _assert_open(report)


@pytest.mark.parametrize("value", [["CC0"], 4.0, None])
def test_catalog_with_a_non_text_license_is_unresolved(synthetic_readme, value):
    report = license_report(synthetic_readme, None, catalog_metadata={"license": value})
    assert report["state"] == "UNRESOLVED"
    _assert_open(report)


def test_catalog_alone_with_a_recognized_license_is_a_single_unadjudicated_source():
    report = license_report(None, None, catalog_metadata={"license": "CC0"})
    assert report["state"] == "SINGLE_SOURCE_NOT_ADJUDICATED"
    assert report["sources_by_token"] == {"CC0-1.0": ["catalog_metadata"]}
    _assert_open(report)


def test_absent_sources_do_not_appear_in_the_token_map():
    report = license_report("License: CC-BY-4.0", None, catalog_metadata={"license": "CC-BY-SA-4.0"})
    assert report["state"] == "CONFLICT_UNRESOLVED"
    assert report["sources_by_token"] == {"CC-BY-4.0": ["readme"], "CC-BY-SA-4.0": ["catalog_metadata"]}


def test_two_tokens_inside_one_dataset_description_stay_a_conflict_with_the_source_named():
    report = license_report(None, None, dataset_description={"License": "CC0 and CC-BY-4.0"})
    assert report["state"] == "CONFLICT_UNRESOLVED"
    assert report["sources_by_token"] == {"CC-BY-4.0": ["dataset_description"], "CC0-1.0": ["dataset_description"]}
    _assert_open(report)


def test_audit_inventory_carries_all_four_license_sources(synthetic_tsv, synthetic_listing, synthetic_readme,
                                                          synthetic_nemar, synthetic_dataset_description,
                                                          synthetic_catalog):
    report = audit_inventory(participants_tsv=synthetic_tsv, file_paths=synthetic_listing,
                             readme_text=synthetic_readme, nemar_metadata=synthetic_nemar,
                             dataset_description=synthetic_dataset_description,
                             catalog_metadata=synthetic_catalog)
    license_state = report["license"]
    assert license_state["state"] == "CONFLICT_UNRESOLVED"
    assert {source["source"] for source in license_state["sources"]} == {
        "readme", "nemar_metadata", "dataset_description", "catalog_metadata"}
    assert "LICENSE_CONFLICT_UNRESOLVED" in [f["code"] for f in report["findings"] if f["severity"] == "error"]
    assert report["scientific_pass"] is False


def test_audit_inventory_without_new_sources_matches_the_two_source_behaviour(synthetic_readme, synthetic_nemar):
    report = audit_inventory(participants_tsv=None, file_paths=[], readme_text=synthetic_readme,
                             nemar_metadata=synthetic_nemar)
    assert report["license"]["state"] == "CONFLICT_UNRESOLVED"
    assert len(report["license"]["sources"]) == 4
    assert [s["status"] for s in report["license"]["sources"][2:]] == ["NOT_PROVIDED", "NOT_PROVIDED"]
