from __future__ import annotations

from tools.research_report.compiler import compile_report

NOW = "2026-01-01T00:00:00+00:00"


def test_missing_dataset_provenance_is_explicit_not_fabricated(manifest_factory):
    manifest = manifest_factory(omit=["dataset_provenance"])

    report = compile_report(manifest, now=NOW)

    assert report["dataset_provenance"]["available"] is False
    assert report["dataset_provenance"]["error"] == "not_provided"
    assert report["dataset_provenance"]["datasets"] == []
    assert report["status"] == "partial"
    assert report["completeness"]["dataset_provenance"] == {"available": False, "error": "not_provided"}

    # Guardrail: no dataset is fabricated into the synthetic/empirical tally.
    sve = report["synthetic_versus_empirical_distinction"]
    assert sve["datasets"] == {"synthetic": [], "empirical": [], "unknown": []}
