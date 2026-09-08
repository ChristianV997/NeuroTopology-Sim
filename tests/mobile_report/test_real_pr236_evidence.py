"""Local report compilation against this repository's own real evidence.

``docs/release/agent_contribution_matrix.yaml`` is a real, hand-maintained
inventory already on ``main`` (not a fixture built for this test). Its
``baseline_commit`` (62637a4b...) predates PR #236's integration head
(be277ecd...), which is exactly the "outdated intermediate commit"
situation docs/reporting/mobile_report_contract.md's guardrail exists for
-- so this test doubles as the required "local report compilation using
PR #236 evidence" smoke test and a real-world exercise of that guardrail.

No network access: the file is read from the local working tree only.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.mobile_report.compiler import compile_report
from tools.mobile_report.render_csv import render_csv_tables
from tools.mobile_report.render_markdown import render_markdown

NOW = "2026-01-01T00:00:00+00:00"
PR_236_INTEGRATION_COMMIT = "be277ecdac301d49dca27ef9612ebe6c560245ad"

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REAL_AGENT_CONTRIBUTIONS = _REPO_ROOT / "docs" / "release" / "agent_contribution_matrix.yaml"


@pytest.mark.skipif(not _REAL_AGENT_CONTRIBUTIONS.is_file(), reason="docs/release/agent_contribution_matrix.yaml not present in this checkout")
def test_compiles_against_the_real_agent_contribution_matrix(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps({"agent_contributions": str(_REAL_AGENT_CONTRIBUTIONS)}),
        encoding="utf-8",
    )

    report = compile_report(
        manifest_path,
        now=NOW,
        repo="NeuroTopology-Sim",
        integration_ref="codex/integration-all-open-prs",
        integration_commit=PR_236_INTEGRATION_COMMIT,
    )

    # Loads and normalizes without raising, over real-world-shaped data.
    assert report["completeness"]["agent_contributions"]["available"] is True
    contributions = report["agent_contribution_table"]["contributions"]
    assert len(contributions) > 10
    assert all(isinstance(c["id"], str) and c["id"] for c in contributions)

    # The real inventory's own authored warnings are surfaced, attributed.
    limitations_text = " ".join(report["scientific_limitations"])
    assert "Synthetic data cannot establish" in limitations_text

    # The real baseline_commit (62637a4b...) is older than PR #236's head
    # -- this must be caught, not silently treated as current.
    outdated = [c for c in report["conflicts"] if c["kind"] == "outdated_intermediate_commit"]
    assert len(outdated) == 1
    assert PR_236_INTEGRATION_COMMIT in outdated[0]["detail"]

    # Output renders and is JSON-serializable/deterministic against this
    # same real input.
    markdown = render_markdown(report)
    assert "## Agent Contribution Table" in markdown
    csv_tables = render_csv_tables(report)
    assert "agent_contributions.csv" in csv_tables

    report_again = compile_report(
        manifest_path, now=NOW, repo="NeuroTopology-Sim", integration_ref="codex/integration-all-open-prs", integration_commit=PR_236_INTEGRATION_COMMIT
    )
    assert json.dumps(report, sort_keys=True) == json.dumps(report_again, sort_keys=True)
