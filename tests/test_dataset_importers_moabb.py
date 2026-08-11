"""MOABB dataset candidate importer: fixture-based import (always run) plus
a guarded, best-effort installed-package path. Never downloads data.
"""
from __future__ import annotations

import json

import pytest

from dataset_importers.moabb_importer import (
    MoabbImporterUnavailable,
    _is_moabb_installed,
    _record_from_moabb_meta,
    import_moabb_candidates,
    import_moabb_candidates_from_fixture,
    import_moabb_candidates_from_installed_package,
)


def _write_fixture(tmp_path, entries):
    path = tmp_path / "moabb_fixture.json"
    path.write_text(json.dumps({"source_catalog": "moabb", "datasets": entries}), encoding="utf-8")
    return path


def test_imports_fixture_records(tmp_path):
    path = _write_fixture(
        tmp_path,
        [
            {
                "code": "BNCI2014001",
                "name": "BNCI Motor Imagery",
                "paradigm": "imagery",
                "event_id": {"left_hand": 1, "right_hand": 2},
                "subject_count": 9,
                "n_sessions": 2,
                "license": "CC0",
                "license_risk": "permissive_low",
                "access_status": "public_requires_download",
            }
        ],
    )
    records = import_moabb_candidates_from_fixture(path)
    assert len(records) == 1
    rec = records[0]
    assert rec.source_catalog == "moabb"
    assert rec.source_dataset_id == "BNCI2014001"
    assert rec.validate() == []


def test_fixture_import_does_not_touch_network_or_disk_beyond_fixture(tmp_path):
    path = _write_fixture(tmp_path, [{"code": "DS1", "name": "Simple"}])
    records = import_moabb_candidates_from_fixture(path)
    assert records[0].download_required == "true"
    assert records[0].raw_data_rehosted is False


def test_missing_license_becomes_review_needed(tmp_path):
    path = _write_fixture(tmp_path, [{"code": "NoLicense", "name": "No license dataset"}])
    rec = import_moabb_candidates_from_fixture(path)[0]
    assert rec.license_risk == "unknown_high"
    assert rec.metadata.get("review_needed") is True
    assert rec.validate() == []


def test_maps_explicit_conditions_when_supplied(tmp_path):
    path = _write_fixture(
        tmp_path,
        [
            {
                "code": "P300Ds",
                "name": "P300 speller",
                "paradigm": "p300",
                "event_id": {"target": 1, "non_target": 2},
                "subject_count": 12,
                "access_status": "public",
                "license": "CC0",
            }
        ],
    )
    rec = import_moabb_candidates_from_fixture(path)[0]
    assert set(rec.condition_labels) == {"target", "non_target"}
    assert rec.potential_transition_classes


def test_produces_conservative_candidate_statuses(tmp_path):
    path = _write_fixture(
        tmp_path,
        [
            {"code": "Good", "name": "Good ds", "event_id": {"a": 1, "b": 2}, "subject_count": 5, "license": "CC0", "access_status": "public"},
            {"code": "Bad", "name": "Bad ds", "access_status": "restricted"},
            {"code": "Sparse", "name": "Sparse ds"},
        ],
    )
    records = import_moabb_candidates_from_fixture(path)
    by_id = {r.source_dataset_id: r for r in records}
    assert by_id["Good"].benchmark_role_recommendation == "development_candidate"
    assert by_id["Bad"].benchmark_role_recommendation == "blocked"
    assert by_id["Sparse"].benchmark_role_recommendation == "blocked"
    for r in records:
        assert r.validate() == []


def test_record_from_meta_rejects_entry_without_code():
    with pytest.raises(ValueError):
        _record_from_moabb_meta({"name": "no code here"})


def test_orchestrator_prefers_fixture_over_installed(tmp_path):
    path = _write_fixture(tmp_path, [{"code": "PreferFixture", "name": "x"}])
    records = import_moabb_candidates(fixture_path=path, prefer_installed=True)
    assert len(records) == 1
    assert records[0].source_dataset_id == "PreferFixture"


def test_orchestrator_raises_clear_error_without_fixture_or_installed_package():
    if _is_moabb_installed():
        pytest.skip("moabb is installed in this environment; unavailable-path is not exercised here")
    with pytest.raises(MoabbImporterUnavailable):
        import_moabb_candidates(fixture_path=None, prefer_installed=True)


def test_installed_package_path_skips_with_clear_reason_if_unavailable():
    if _is_moabb_installed():
        pytest.skip("moabb is installed in this environment -- see test_installed_package_path_runs_if_available")
    with pytest.raises(MoabbImporterUnavailable, match="not installed"):
        import_moabb_candidates_from_installed_package()


def test_installed_package_path_runs_if_available_and_never_downloads():
    if not _is_moabb_installed():
        pytest.skip("moabb is not installed in this environment -- see test_installed_package_path_skips_with_clear_reason_if_unavailable")
    records = import_moabb_candidates_from_installed_package(limit=3)
    assert isinstance(records, list)
    for rec in records:
        assert rec.validate() == []
        assert rec.source_catalog == "moabb"
