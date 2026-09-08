"""Local compilation against this repository's own real evidence.

``docs/release/agent_contribution_matrix.yaml`` is a real, hand-maintained
inventory already on ``main`` (not a fixture built for this test). Its
``baseline_commit`` (62637a4b...) predates PR #236's integration head
(be277ecd...), which is exactly the "stale integration commit" situation
docs/reporting/research_record_contract.md's guardrail exists for -- so
this test doubles as a real-world exercise of that guardrail and of
integration_branch_and_verified_head.

No network access: the file is read from the local working tree only.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.research_record.compiler import compile_record
from tools.research_record.render_csv import render_csv_tables
from tools.research_record.render_markdown import render_markdown

NOW = "2026-01-01T00:00:00+00:00"
PR_236_INTEGRATION_COMMIT = "be277ecdac301d49dca27ef9612ebe6c560245ad"

_REPO_ROOT = Path(__file__).resolve().parents[2]
_REAL_AGENT_CONTRIBUTIONS = _REPO_ROOT / "docs" / "release" / "agent_contribution_matrix.yaml"


@pytest.mark.skipif(not _REAL_AGENT_CONTRIBUTIONS.is_file(), reason="docs/release/agent_contribution_matrix.yaml not present in this checkout")
def test_compiles_against_the_real_agent_contribution_matrix(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps({"agent_contributions": str(_REAL_AGENT_CONTRIBUTIONS)}), encoding="utf-8")

    record = compile_record(
        manifest_path,
        now=NOW,
        repo="NeuroTopology-Sim",
        integration_ref="codex/integration-all-open-prs",
        integration_commit=PR_236_INTEGRATION_COMMIT,
    )

    assert record["completeness"]["agent_contributions"]["available"] is True
    contributions = record["agent_contribution_table"]["contributions"]
    assert len(contributions) > 10
    assert all(isinstance(c["id"], str) and c["id"] for c in contributions)

    limitations_text = " ".join(record["scientific_limitations"])
    assert "Synthetic data cannot establish" in limitations_text

    stale = [c for c in record["conflicts"] if c["kind"] == "stale_integration_commit"]
    assert len(stale) == 1
    assert PR_236_INTEGRATION_COMMIT in stale[0]["detail"]
    assert record["integration_branch_and_verified_head"]["verified"] is False

    markdown = render_markdown(record)
    assert "## Agent Contribution Table" in markdown
    csv_tables = render_csv_tables(record)
    assert "agent_contributions.csv" in csv_tables

    record_again = compile_record(
        manifest_path, now=NOW, repo="NeuroTopology-Sim", integration_ref="codex/integration-all-open-prs", integration_commit=PR_236_INTEGRATION_COMMIT
    )
    assert json.dumps(record, sort_keys=True) == json.dumps(record_again, sort_keys=True)
