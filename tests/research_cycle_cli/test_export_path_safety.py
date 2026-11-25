"""Requirement 3: export writes only to an explicitly supplied output directory."""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.inspect_research_cycle import main  # noqa: E402

NOW = "2026-01-01T00:00:00+00:00"


def test_export_without_output_dir_is_rejected_and_writes_nothing(tmp_path, capsys, monkeypatch):
    monkeypatch.chdir(tmp_path)
    before = set(tmp_path.rglob("*"))

    exit_code = main(["export", "--now", NOW])

    assert exit_code == 2
    after = set(tmp_path.rglob("*"))
    assert after == before  # nothing was written anywhere


def test_export_with_output_dir_writes_only_inside_it(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    output_dir = tmp_path / "reports_out"

    exit_code = main(["export", "--output-dir", str(output_dir), "--now", NOW])

    assert exit_code == 1  # no sources supplied -> incomplete, but the export itself must still happen
    written = sorted(p.relative_to(tmp_path) for p in tmp_path.rglob("*") if p.is_file())
    assert all(str(p).startswith("reports_out" + os.sep) for p in written)
    assert (output_dir / "inspection_report.json").is_file()
    assert (output_dir / "inspection_report.md").is_file()
    assert (output_dir / "inspection_summary.txt").is_file()


def test_non_export_modes_never_write_files(tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    for mode in ("summary", "cycle", "claims", "hypotheses", "artifacts", "graph", "blockers", "stale", "validate"):
        before = set(tmp_path.rglob("*"))
        main([mode, "--now", NOW])
        after = set(tmp_path.rglob("*"))
        assert after == before, f"mode {mode!r} wrote a file"
