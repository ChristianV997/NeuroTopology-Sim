from __future__ import annotations

import json
from pathlib import Path

from scripts.run_awareness_research_cycle import main
from tests.awareness_studio_research_loop.fixtures_data import complete_cycle_overrides

NOW = "2026-01-01T00:00:00+00:00"


def test_cli_writes_json_markdown_and_csv(manifest_factory, tmp_path: Path):
    manifest = manifest_factory(complete_cycle_overrides())
    out_dir = tmp_path / "out"

    exit_code = main(["--manifest", str(manifest), "--output-dir", str(out_dir), "--formats", "json,markdown,csv", "--now", NOW])

    assert exit_code == 0
    report = json.loads((out_dir / "research_cycle_report.json").read_text(encoding="utf-8"))
    assert report["generated_at"] == NOW
    assert report["cycle_states"]["H1"]["state"] == "PAPER_DRAFT_READY"
    assert (out_dir / "paper_draft.md").exists()
    assert (out_dir / "csv" / "artifact_ledger.csv").exists()


def test_cli_rejects_unknown_format(manifest_factory, tmp_path: Path):
    manifest = manifest_factory(complete_cycle_overrides())
    exit_code = main(["--manifest", str(manifest), "--output-dir", str(tmp_path / "out"), "--formats", "xml"])
    assert exit_code == 2
