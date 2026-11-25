from __future__ import annotations

from tools.mobile_report.compiler import compile_report

NOW = "2026-01-01T00:00:00+00:00"


def test_missing_dataset_provenance_is_explicit_not_fabricated(manifest_factory):
    manifest = manifest_factory(omit=["dataset_provenance"])

    report = compile_report(manifest, now=NOW)

    assert report["provenance_status"]["available"] is False
    assert report["provenance_status"]["error"] == "not_provided"
    assert report["provenance_status"]["datasets"] == []
    assert report["status"] == "partial"


def test_checksum_source_defaults_to_unknown_not_independent(manifest_factory):
    manifest = manifest_factory(
        {"dataset_provenance": {"datasets": [{"dataset_id": "ds1", "data_mode": "empirical", "source": "local", "checksum": "abc", "n_subjects": None}]}}
    )

    report = compile_report(manifest, now=NOW)
    dataset = report["provenance_status"]["datasets"][0]
    # checksum_source was not supplied, so it must not be silently upgraded
    # to "independent" just because a checksum string is present.
    assert dataset["checksum_source"] == "unknown"
