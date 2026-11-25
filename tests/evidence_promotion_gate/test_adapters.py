"""Read-only adapters for local promotion-gate inputs."""

from __future__ import annotations

from pathlib import Path

from tools.evidence_promotion_gate.adapters import (
    classify_payload,
    discover_cases,
    parse_markdown_frontmatter,
    parse_artifact,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def test_discover_cases_uses_subdirectories():
    cases = discover_cases(FIXTURES)
    assert len(cases) >= 15
    assert {case.case_id for case in cases} >= {"synthetic_run", "proxy_k", "literature_hypothesis"}


def test_run_record_and_literature_classification():
    run = parse_artifact(FIXTURES / "synthetic_run" / "RunRecord.json")
    assert run.kind == "run_record"
    assert run.data_mode == "synthetic"
    lit = parse_artifact(FIXTURES / "literature_hypothesis" / "literature.json")
    assert lit.kind == "literature"
    assert lit.claim_kind == "hypothesis"


def test_rag_markdown_frontmatter_and_pass_verdict():
    artifact = parse_artifact(FIXTURES / "downstream_pass_rag" / "export.md")
    assert artifact.kind == "rag_markdown"
    assert artifact.verdict == "PASS"
    fields = parse_markdown_frontmatter((FIXTURES / "downstream_pass_rag" / "export.md").read_text(encoding="utf-8"))
    assert fields["verdict"] == "PASS"


def test_airtable_and_command_center_kinds():
    card = parse_artifact(FIXTURES / "airtable_empirical_pass" / "airtable_card.json")
    assert card.kind == "airtable_card"
    assert card.verdict == "PASS"
    assert card.evidence_class == "EMPIRICAL"
    cc = parse_artifact(FIXTURES / "downstream_empirical_cc" / "command_center.json")
    assert cc.kind == "command_center"


def test_classify_payload_claim_gate_shape():
    kind = classify_payload(
        {"schema_version": "NeuroTopology.ResearchClaimGate.v1", "decision": "CLAIM_ADMISSIBLE"},
        filename="gate.json",
    )
    assert kind == "claim_gate_result"
