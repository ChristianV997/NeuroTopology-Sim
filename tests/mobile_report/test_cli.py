from __future__ import annotations

import json
from pathlib import Path

from scripts.compile_mobile_research_report import main

NOW = "2026-01-01T00:00:00+00:00"


def test_cli_writes_markdown_json_and_csv(manifest_factory, tmp_path: Path):
    manifest = manifest_factory(
        {"reconciliation": {"pull_requests": [{"pr_number": 1, "branch": "a", "base_branch": "main", "merge_status": "open", "mergeable": True, "ci_status": "passed"}]}}
    )
    out_dir = tmp_path / "out"

    exit_code = main(["--manifest", str(manifest), "--output-dir", str(out_dir), "--formats", "markdown,json,csv", "--now", NOW])

    assert exit_code == 0
    report = json.loads((out_dir / "mobile_research_report.json").read_text(encoding="utf-8"))
    assert report["generated_at"] == NOW
    assert (out_dir / "mobile_research_report.md").exists()
    assert (out_dir / "csv" / "pr_state.csv").exists()


def test_cli_rejects_unknown_format(manifest_factory, tmp_path: Path):
    manifest = manifest_factory({})
    exit_code = main(["--manifest", str(manifest), "--output-dir", str(tmp_path / "out"), "--formats", "xml"])
    assert exit_code == 2


def test_cli_accepts_yaml_manifest(tmp_path: Path):
    import yaml

    section_path = tmp_path / "reconciliation.json"
    section_path.write_text(json.dumps({"pull_requests": []}), encoding="utf-8")
    manifest_path = tmp_path / "manifest.yaml"
    manifest_path.write_text(yaml.safe_dump({"reconciliation": "reconciliation.json"}), encoding="utf-8")

    out_dir = tmp_path / "out"
    exit_code = main(["--manifest", str(manifest_path), "--output-dir", str(out_dir), "--formats", "json", "--now", NOW])
    assert exit_code == 0
    report = json.loads((out_dir / "mobile_research_report.json").read_text(encoding="utf-8"))
    assert report["completeness"]["reconciliation"]["available"] is True
