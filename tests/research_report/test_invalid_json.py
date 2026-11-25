from __future__ import annotations

from tools.research_report.compiler import compile_report

NOW = "2026-01-01T00:00:00+00:00"


def test_malformed_json_does_not_crash_the_compiler(manifest_factory):
    manifest = manifest_factory({"reconciliation": "{this is not valid json"})

    report = compile_report(manifest, now=NOW)

    assert report["completeness"]["reconciliation"]["available"] is False
    assert "invalid_json" in report["completeness"]["reconciliation"]["error"]
    assert report["pull_requests"]["pull_requests"] == []
    assert report["status"] == "partial"

    # Every other section still compiled normally.
    assert report["completeness"]["capability_snapshot"]["available"] is True


def test_missing_manifest_file_does_not_crash(tmp_path):
    report = compile_report(tmp_path / "does_not_exist.json", now=NOW)
    assert report["status"] == "partial"
    for section in report["completeness"].values():
        assert section["available"] is False
        assert "manifest_load_failed" in section["error"]
