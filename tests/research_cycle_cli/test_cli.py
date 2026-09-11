from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.inspect_research_cycle import main  # noqa: E402

NOW = "2026-01-01T00:00:00+00:00"


def test_cycle_mode_with_cycle_id_filters_to_one_cycle(build_ledger_db, capsys):
    db_path = build_ledger_db(
        [{"cycle_id": "CYC-A", "status": "IN_PROGRESS", "finalized": False, "metadata": {}}, {"cycle_id": "CYC-B", "status": "BLOCKED", "finalized": False, "metadata": {}}],
        [],
    )

    exit_code = main(["cycle", "--ledger-db", str(db_path), "--cycle-id", "CYC-B", "--now", NOW, "--format", "json"])

    payload = json.loads(capsys.readouterr().out)
    assert payload["cycle"]["cycle_id"] == "CYC-B"
    assert payload["groups_containing_cycle"]["blocked"] is True
    assert payload["groups_containing_cycle"]["active"] is False
    assert exit_code == 3


def test_each_mode_runs_without_error(build_ledger_db, capsys):
    db_path = build_ledger_db([{"cycle_id": "CYC-A", "status": "COMPLETED", "finalized": False, "metadata": {}}], [])
    for mode in ("summary", "cycle", "claims", "hypotheses", "artifacts", "graph", "blockers", "stale", "validate"):
        exit_code = main([mode, "--ledger-db", str(db_path), "--now", NOW, "--format", "json"])
        assert exit_code in (0, 1, 2, 3)
        out = capsys.readouterr().out
        json.loads(out)  # every mode must emit valid JSON under --format json


def test_markdown_format_renders_the_full_report(build_ledger_db, capsys):
    db_path = build_ledger_db([{"cycle_id": "CYC-A", "status": "COMPLETED", "finalized": False, "metadata": {}}], [])
    main(["summary", "--ledger-db", str(db_path), "--now", NOW, "--format", "markdown"])
    out = capsys.readouterr().out
    assert "# Research Cycle Inspection Report" in out
    assert "## Blockers" in out


def test_text_format_is_the_default(build_ledger_db, capsys):
    db_path = build_ledger_db([{"cycle_id": "CYC-A", "status": "COMPLETED", "finalized": False, "metadata": {}}], [])
    main(["summary", "--ledger-db", str(db_path), "--now", NOW])
    out = capsys.readouterr().out
    assert "research-cycle inspection --" in out
