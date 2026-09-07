from __future__ import annotations

from tools.research_record.compiler import compile_record

NOW = "2026-01-01T00:00:00+00:00"


def test_missing_dataset_provenance_is_explicit_not_fabricated(manifest_factory):
    manifest = manifest_factory(omit=["dataset_provenance"])

    record = compile_record(manifest, now=NOW)

    assert record["provenance"]["available"] is False
    assert record["provenance"]["error"] == "not_provided"
    assert record["provenance"]["datasets"] == []
    assert record["status"] == "partial"


def test_checksum_source_defaults_to_unknown_not_independent(manifest_factory):
    manifest = manifest_factory(
        {"dataset_provenance": {"datasets": [{"dataset_id": "ds1", "data_mode": "empirical", "source": "local", "checksum": "abc", "n_subjects": None}]}}
    )

    record = compile_record(manifest, now=NOW)
    dataset = record["provenance"]["datasets"][0]
    assert dataset["checksum_source"] == "unknown"


def test_every_provenance_record_retains_its_source_path_and_checksum(manifest_factory):
    manifest = manifest_factory({"dataset_provenance": {"datasets": [{"dataset_id": "ds1", "data_mode": "empirical"}]}})

    record = compile_record(manifest, now=NOW)
    section_provenance = record["record_provenance"]["source_checksums"]["dataset_provenance"]
    assert section_provenance["path"] is not None
    assert section_provenance["sha256"] is not None
    assert section_provenance["checksum_scope"] == "local"
