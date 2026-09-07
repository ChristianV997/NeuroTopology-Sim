from __future__ import annotations

from tools.research_record.compiler import compile_record

NOW = "2026-01-01T00:00:00+00:00"


def test_stale_agent_contributions_baseline_commit_is_flagged(manifest_factory):
    # Modeled on the real docs/release/agent_contribution_matrix.yaml, whose
    # baseline_commit (62637a4b...) predates PR #236's integration head
    # (be277ecd...) -- exactly the situation this guardrail exists for.
    manifest = manifest_factory(
        {
            "agent_contributions": {
                "repository": "https://github.com/ChristianV997/NeuroTopology-Sim",
                "baseline_commit": "62637a4b9c82c0c258bfc49e28dee1af757b1c25",
                "evidence_source": "github_api",
                "inventory_is_not_evidence": True,
                "required_warnings": [],
                "contributions": [],
            }
        }
    )

    record = compile_record(manifest, now=NOW, integration_commit="be277ecdac301d49dca27ef9612ebe6c560245ad")

    conflicts = [c for c in record["conflicts"] if c["kind"] == "stale_integration_commit"]
    assert len(conflicts) == 1
    assert "62637a4b9c82c0c258bfc49e28dee1af757b1c25" in conflicts[0]["detail"]
    assert "be277ecdac301d49dca27ef9612ebe6c560245ad" in conflicts[0]["detail"]

    # A stale/mismatched commit must not be reported as "verified" either.
    assert record["integration_branch_and_verified_head"]["verified"] is False


def test_matching_baseline_commit_is_verified_and_not_flagged(manifest_factory):
    commit = "be277ecdac301d49dca27ef9612ebe6c560245ad"
    manifest = manifest_factory(
        {
            "agent_contributions": {
                "repository": None,
                "baseline_commit": commit,
                "evidence_source": "github_api",
                "inventory_is_not_evidence": True,
                "required_warnings": [],
                "contributions": [],
            }
        }
    )

    record = compile_record(manifest, now=NOW, integration_commit=commit)
    assert not [c for c in record["conflicts"] if c["kind"] == "stale_integration_commit"]
    assert record["integration_branch_and_verified_head"]["verified"] is True


def test_no_integration_commit_given_means_no_comparison_and_not_verified(manifest_factory):
    manifest = manifest_factory(
        {
            "agent_contributions": {
                "repository": None,
                "baseline_commit": "62637a4b9c82c0c258bfc49e28dee1af757b1c25",
                "evidence_source": None,
                "inventory_is_not_evidence": True,
                "required_warnings": [],
                "contributions": [],
            }
        }
    )

    record = compile_record(manifest, now=NOW, integration_commit=None)
    assert not [c for c in record["conflicts"] if c["kind"] == "stale_integration_commit"]
    assert record["integration_branch_and_verified_head"]["verified"] is False


def test_matching_commit_without_github_api_evidence_source_is_not_verified(manifest_factory):
    # Rule 1/2: a matching commit alone is not proof -- it must be
    # corroborated by an independently-sourced document.
    commit = "be277ecdac301d49dca27ef9612ebe6c560245ad"
    manifest = manifest_factory(
        {
            "agent_contributions": {
                "repository": None,
                "baseline_commit": commit,
                "evidence_source": "manual_note",
                "inventory_is_not_evidence": True,
                "required_warnings": [],
                "contributions": [],
            }
        }
    )

    record = compile_record(manifest, now=NOW, integration_commit=commit)
    assert record["integration_branch_and_verified_head"]["verified"] is False
