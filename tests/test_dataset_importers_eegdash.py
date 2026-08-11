"""EEGDash dataset candidate importer: fixture-based import (always run)
plus a guarded, best-effort installed-package path. The live-query branch
is exercised only via monkeypatching `eegdash.EEGDash.find_datasets` --
this test suite never makes a real network call.
"""
from __future__ import annotations

import json

import pytest

from dataset_importers.eegdash_importer import (
    EegdashImporterUnavailable,
    _is_eegdash_installed,
    _record_from_eegdash_meta,
    import_eegdash_candidates,
    import_eegdash_candidates_from_fixture,
    import_eegdash_candidates_from_installed_package,
)


def _write_fixture(tmp_path, entries):
    path = tmp_path / "eegdash_fixture.json"
    path.write_text(json.dumps({"source_catalog": "eegdash", "datasets": entries}), encoding="utf-8")
    return path


def test_imports_fixture_records(tmp_path):
    path = _write_fixture(
        tmp_path,
        [
            {
                "dataset_id": "ds002718",
                "name": "Rest/Task EEG",
                "source": "openneuro",
                "recording_modality": ["eeg"],
                "tasks": ["rest", "task"],
                "license": "CC0",
                "demographics": {"subjects_count": 20},
                "sessions": ["1"],
                "dataset_doi": "10.18112/example",
            }
        ],
    )
    records = import_eegdash_candidates_from_fixture(path)
    assert len(records) == 1
    rec = records[0]
    assert rec.source_catalog == "eegdash"
    assert rec.source_dataset_id == "ds002718"
    assert rec.access_status == "public"
    assert rec.validate() == []


def test_fixture_import_does_not_touch_network(tmp_path):
    path = _write_fixture(tmp_path, [{"dataset_id": "dsX", "name": "x"}])
    records = import_eegdash_candidates_from_fixture(path)
    assert records[0].download_required == "true"


def test_preserves_source_archive_license_and_task_metadata(tmp_path):
    path = _write_fixture(
        tmp_path,
        [
            {
                "dataset_id": "ds777",
                "name": "Sleep study",
                "source": "nemar",
                "recording_modality": ["eeg"],
                "tasks": ["wake", "sleep"],
                "license": "CC-BY-4.0",
                "demographics": {"subjects_count": 15},
                "dataset_doi": "10.1/xyz",
            }
        ],
    )
    rec = import_eegdash_candidates_from_fixture(path)[0]
    assert rec.access_status == "public"
    assert rec.license == "CC-BY-4.0"
    assert set(rec.task_labels) == {"wake", "sleep"}
    assert set(rec.condition_labels) == {"wake", "sleep"}
    assert rec.metadata["eegdash_dataset_doi"] == "10.1/xyz"


def test_handles_missing_loadability_metadata_conservatively(tmp_path):
    path = _write_fixture(tmp_path, [{"dataset_id": "dsSparse", "name": "sparse"}])
    rec = import_eegdash_candidates_from_fixture(path)[0]
    assert rec.access_status == "unknown"
    assert rec.license_risk == "unknown_high"
    # No recording_modality at all is conservatively treated as unsupported
    # rather than assumed to be EEG -- never guess a modality.
    assert rec.transition_readiness == "blocked_unsupported_modality"
    assert rec.benchmark_role_recommendation == "blocked"
    assert rec.validate() == []


def test_handles_missing_conditions_and_subjects_conservatively(tmp_path):
    path = _write_fixture(tmp_path, [{"dataset_id": "dsSparseModality", "name": "sparse but eeg", "recording_modality": ["eeg"]}])
    rec = import_eegdash_candidates_from_fixture(path)[0]
    assert rec.access_status == "unknown"
    assert rec.license_risk == "unknown_high"
    assert rec.transition_readiness == "blocked_missing_metadata"
    assert rec.benchmark_role_recommendation == "blocked"
    assert rec.validate() == []


def test_record_from_meta_rejects_entry_without_dataset_id():
    with pytest.raises(ValueError):
        _record_from_eegdash_meta({"name": "no dataset_id here"})


def test_orchestrator_prefers_fixture_over_installed(tmp_path):
    path = _write_fixture(tmp_path, [{"dataset_id": "dsFixturePreferred", "name": "x"}])
    records = import_eegdash_candidates(fixture_path=path, prefer_installed=True)
    assert len(records) == 1
    assert records[0].source_dataset_id == "dsFixturePreferred"


def test_installed_package_default_never_queries_network():
    if not _is_eegdash_installed():
        pytest.skip("eegdash is not installed in this environment")
    records = import_eegdash_candidates_from_installed_package(live_query=False)
    assert records == []


def test_installed_package_live_query_uses_monkeypatched_client_never_real_network(monkeypatch):
    if not _is_eegdash_installed():
        pytest.skip("eegdash is not installed in this environment")
    import eegdash

    class _FakeClient:
        def find_datasets(self, query, limit=20):
            return [
                {
                    "dataset_id": "ds999",
                    "name": "Mocked catalog entry",
                    "source": "openneuro",
                    "recording_modality": ["eeg"],
                    "tasks": ["rest", "task"],
                    "license": "CC0",
                    "demographics": {"subjects_count": 8},
                }
            ]

    monkeypatch.setattr(eegdash, "EEGDash", lambda *a, **k: _FakeClient())
    records = import_eegdash_candidates_from_installed_package(live_query=True)
    assert len(records) == 1
    assert records[0].source_dataset_id == "ds999"
    assert records[0].validate() == []


def test_installed_package_live_query_failure_raises_clear_error_not_silent(monkeypatch):
    if not _is_eegdash_installed():
        pytest.skip("eegdash is not installed in this environment")
    import eegdash

    class _FailingClient:
        def find_datasets(self, query, limit=20):
            raise RuntimeError("simulated network failure")

    monkeypatch.setattr(eegdash, "EEGDash", lambda *a, **k: _FailingClient())
    with pytest.raises(EegdashImporterUnavailable, match="simulated network failure"):
        import_eegdash_candidates_from_installed_package(live_query=True)


def test_orchestrator_raises_clear_error_without_fixture_or_installed_package(monkeypatch):
    monkeypatch.setattr("dataset_importers.eegdash_importer._is_eegdash_installed", lambda: False)
    with pytest.raises(EegdashImporterUnavailable):
        import_eegdash_candidates(fixture_path=None, prefer_installed=True)
