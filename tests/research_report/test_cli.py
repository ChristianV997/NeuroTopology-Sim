from __future__ import annotations

import json
from pathlib import Path

from scripts.compile_research_state import main

NOW = "2026-01-01T00:00:00+00:00"


def test_cli_writes_json_markdown_and_csv(manifest_factory, tmp_path: Path):
    manifest = manifest_factory(
        {"reconciliation": {"pull_requests": [{"pr_number": 1, "branch": "a", "base_branch": "main", "state": "open", "mergeable": True, "ci_status": "passed"}]}}
    )
    out_dir = tmp_path / "out"

    exit_code = main(["--manifest", str(manifest), "--output-dir", str(out_dir), "--formats", "json,markdown,csv", "--now", NOW])

    assert exit_code == 0
    report = json.loads((out_dir / "research_state_report.json").read_text(encoding="utf-8"))
    assert report["generated_at"] == NOW
    assert (out_dir / "research_state_report.md").exists()
    assert (out_dir / "csv" / "pull_requests.csv").exists()


def test_cli_rejects_unknown_format(manifest_factory, tmp_path: Path):
    manifest = manifest_factory({})
    exit_code = main(["--manifest", str(manifest), "--output-dir", str(tmp_path / "out"), "--formats", "yaml"])
    assert exit_code == 2
