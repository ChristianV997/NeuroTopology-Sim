"""Incompatible versions, preserved labels, and blocked invalid claims."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.integration.research_cycle.contracts import declared_version
from tests.integration.research_cycle.fixtures import happy_chain, write_chain
from tests.integration.research_cycle.inspector import (
    ContractError,
    inspect_directory,
    parse_stage_document,
    stamp_checksum,
    write_document,
)
from tests.integration.research_cycle.producers import probe_release_evidence, probe_research_cycle


def test_consumer_rejects_incompatible_schema_version(tmp_path: Path) -> None:
    docs = happy_chain()
    lit = dict(docs[0])
    lit["schema_version"] = "NeuroTopologySim.EmpiricalSourceManifest.v0"
    write_document(tmp_path / "01_literature_source_manifest.json", lit)
    with pytest.raises(ContractError, match="incompatible schema_version"):
        parse_stage_document(tmp_path / "01_literature_source_manifest.json")
    report = inspect_directory(tmp_path)
    assert report.status == "BLOCKED"
    assert report.incompatible_versions


def test_consumer_rejects_missing_schema_version(tmp_path: Path) -> None:
    docs = happy_chain()
    lit = dict(docs[0])
    lit.pop("schema_version")
    path = tmp_path / "01_literature_source_manifest.json"
    path.write_text(json.dumps(lit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(ContractError, match="missing envelope field 'schema_version'"):
        parse_stage_document(path)


def test_consumer_rejects_incompatible_pipeline_contract(tmp_path: Path) -> None:
    docs = happy_chain()
    lit = dict(docs[0])
    lit["pipeline_contract"] = "NeuroTopologySim.ResearchCyclePipeline.v9"
    write_document(tmp_path / "01_literature_source_manifest.json", lit)
    with pytest.raises(ContractError, match="incompatible pipeline_contract"):
        parse_stage_document(tmp_path / "01_literature_source_manifest.json")


def test_release_evidence_gate_rejects_incompatible_normalization_schema() -> None:
    payload = happy_chain()[-1]["payload"]
    baseline = dict(payload["baseline"])
    candidate = dict(payload["candidate"])
    baseline["schema_version"] = "9.9"
    report = probe_release_evidence(baseline, candidate)
    assert report["decision"] == "NOT_COMPARABLE"
    assert any("schema" in code for code in report["reason_codes"])
    assert report["evidence_class"] == "performance_only"
    assert report["synthetic"] is True


def test_synthetic_proxy_empirical_labels_are_not_silently_changed(tmp_path: Path) -> None:
    docs = happy_chain()
    mutated = dict(docs[3])
    mutated["data_mode"] = "empirical"
    mutated["evidence_class"] = "preregistered_empirical"
    write_chain(tmp_path, docs[:3] + [stamp_checksum(mutated)] + docs[4:])
    report = inspect_directory(tmp_path)
    assert report.label_mutations
    assert any("data_mode mutated" in item for item in report.label_mutations)
    assert report.status != "COMPLETE"


def test_invalid_scientific_pass_from_synthetic_is_blocked(tmp_path: Path) -> None:
    docs = happy_chain()
    validation = dict(docs[5])
    validation["scientific_verdict"] = "PASS"
    write_chain(tmp_path, docs[:5] + [stamp_checksum(validation)] + docs[6:])
    report = inspect_directory(tmp_path)
    assert report.blocked_claims
    assert any("scientific PASS is forbidden" in item for item in report.blocked_claims)
    assert report.status == "BLOCKED"


def test_proxy_bayes_cannot_become_formal_support(tmp_path: Path) -> None:
    docs = happy_chain()
    hyp = dict(docs[2])
    hyp["payload"] = dict(hyp["payload"])
    evidence = {
        "schema_version": "EvidenceUpdate.v1",
        "evidence_id": "ev_proxy_001",
        "hypothesis_id": hyp["record_id"],
        "experiment_id": "plan_synthetic_001",
        "source_checksum": "b" * 64,
        "experiment_checksum": "c" * 64,
        "data_type": "proxy_bayes_factor",
        "is_synthetic": True,
        "is_out_of_sample": False,
        "metrics_observed": {"proxy_k": 1.2},
        "observed_effect_size": None,
        "observed_p_value": None,
        "provenance": {"kind": "proxy"},
        "notes": "proxy K is not formal Bayes",
    }
    hyp["payload"]["evidence"] = {evidence["evidence_id"]: evidence}
    hyp["scientific_verdict"] = "PASS"
    hyp["payload"]["data_type"] = "proxy_bayes_factor"
    write_chain(tmp_path, docs[:2] + [stamp_checksum(hyp)] + docs[3:])
    report = inspect_directory(tmp_path)
    assert any("proxy K" in item or "scientific PASS" in item for item in report.blocked_claims)


def test_research_cycle_gates_block_synthetic_biological_promotion() -> None:
    payload = happy_chain()[2]["payload"]
    exported = probe_research_cycle(payload)
    assert exported["promotion_blocked"]
    assert "Rule" in exported["promotion_blocked"]
    hypothesis = next(iter(exported["hypotheses"].values()))
    assert hypothesis["epistemic_label"] == "speculative_hypothesis"
    assert hypothesis["schema_version"] == "HypothesisRecord.v1"


def test_declared_versions_match_envelope(tmp_path: Path) -> None:
    write_chain(tmp_path, happy_chain())
    for path in sorted(tmp_path.glob("*.json")):
        document = json.loads(path.read_text(encoding="utf-8"))
        assert document["schema_version"] == declared_version(document["stage"]) or document[
            "schema_version"
        ] in {"1.0", declared_version(document["stage"])}
