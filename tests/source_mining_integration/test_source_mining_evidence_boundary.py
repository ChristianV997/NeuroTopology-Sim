"""Offline integration checks for source-mining/evidence boundaries.

These tests deliberately exercise the current public-repo artifact vocabulary and
EvidencePromotionGate adapter/evaluator. A source pack is not scientific evidence.
No network, harvested code, or external datasets are used.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

# Keep this package runnable with --confcutdir in minimal offline environments.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(ROOT))

from tools.evidence_promotion_gate.adapters import load_case_dir
from tools.evidence_promotion_gate.evaluator import evaluate_case
from tools.public_repo_harvest.schema import CandidateRepo, LicenseCompatibilityRecord, SourceRepo, to_dict


def _dump_case(tmp_path: Path, name: str, payload: dict) -> Path:
    case = tmp_path / name
    case.mkdir()
    (case / "artifact.json").write_text(json.dumps(payload), encoding="utf-8")
    return case


def _source_pack(*, identity: str = "owner/project", license_status: str = "compatible", checksum: str | None = None) -> dict:
    body = b"fixture-only source metadata; no source code"
    return {
        "record_type": "source_pack",
        "schema_version": "source-pack-fixture-v1",
        "source_identity": identity,
        "repository_url": f"https://github.com/{identity}",
        "revision": "a" * 40,
        "license": {"spdx": "MIT", "status": license_status},
        "files": [{"path": "README.md", "sha256": checksum or hashlib.sha256(body).hexdigest()}],
        "provenance": {"integrity_only": True},
    }


def _promotion(case_path: Path):
    return evaluate_case(load_case_dir(case_path))


def test_complete_hashed_source_pack_is_not_biological_or_empirical_claim(tmp_path: Path):
    # Current harvest dataclasses carry identity/license fields but no hash contract;
    # the fixture extends them only as input metadata, not as an implementation claim.
    repo = to_dict(SourceRepo(id="fixture", repo_full_name="owner/project", repo_url="https://github.com/owner/project"))
    repo.update(_source_pack())
    validation = to_dict(CandidateRepo(id="fixture-candidate", repo_full_name="owner/project"))
    assert repo["source_identity"] == "owner/project"
    assert len(repo["files"][0]["sha256"]) == 64
    assert validation["repo_full_name"] == repo["repo_full_name"]
    result = _promotion(_dump_case(tmp_path, "source_pack", repo))
    assert result.promotion_decision in {"HOLD_INCONCLUSIVE", "HOLD_INCOMPLETE_PROVENANCE"}
    assert result.scientific_pass is False
    assert result.allowed_evidence_class != "empirical"
    assert result.scientific_eligibility is False


@pytest.mark.parametrize("overrides", [
    {"files": [{"path": "README.md"}]},
    {"license": {"spdx": "UNKNOWN", "status": "unknown"}},
    {"license": {"spdx": "MIT OR GPL-3.0", "status": "needs_manual_review"}},
    {"source_identity": ""},
    {"source_identity": "owner/one", "repo_full_name": "owner/two"},
])
def test_incomplete_or_conflicting_source_pack_never_adoption_ready(tmp_path: Path, overrides: dict):
    payload = _source_pack()
    payload.update(overrides)
    case = _dump_case(tmp_path, "source_not_ready", payload)
    result = _promotion(case)
    assert result.promotion_decision in {"HOLD_INCONCLUSIVE", "HOLD_INCOMPLETE_PROVENANCE"}
    assert result.scientific_pass is False
    assert result.allowed_evidence_class not in {"empirical", "descriptive_empirical"}


def test_current_harvest_license_contract_defaults_fail_closed():
    license_record = to_dict(LicenseCompatibilityRecord(id="unknown-license"))
    assert license_record["license_status"] == "unknown"
    assert license_record["compatibility_status"] == "manual_review_required"
    assert license_record["can_copy_code"] is False
    assert license_record["manual_review_required"] is True


@pytest.mark.parametrize("conflict", ["license_conflict", "cohort_discrepancy"])
def test_explicit_empirical_declaration_is_refused_when_dataset_metadata_conflicts(tmp_path: Path, conflict: str):
    # The BLOCK decision here comes from the explicit evidence_class="empirical" refusal.
    # It does not come from the conflict fields, which the gate ignores (see the xfail below).
    packet = {
        "record_type": "SourceSnapshot",
        "schema_version": "dataset-metadata-fixture-v1",
        "dataset_id": "ds-fixture-only",
        "license_status": "conflict" if conflict == "license_conflict" else "unknown",
        "cohort_status": "unresolved" if conflict == "cohort_discrepancy" else "consistent",
        "cohort_discrepancy": conflict == "cohort_discrepancy",
        "evidence_class": "empirical",
        "data_mode": "observational",
        "provenance": {"source_id": "ds-fixture-only", "checksum": "a" * 64,
                       "acquisition": "fixture", "dataset_version": "fixture-v1"},
    }
    result = _promotion(_dump_case(tmp_path, conflict, packet))
    assert result.promotion_decision == "BLOCK_PROMOTION"
    assert result.scientific_pass is False
    assert result.allowed_evidence_class != "empirical"


@pytest.mark.parametrize("data_mode,kind", [
    ("fixture", "run_record"),
    ("literature", "literature"),
    ("source_code_analysis", "research_cycle"),
    ("dry_run", "research_cycle"),
])
def test_nonempirical_artifact_classes_do_not_promote(tmp_path: Path, data_mode: str, kind: str):
    if kind == "run_record":
        payload = {"run_id": "fixture-run", "run_kind": "integration", "data_mode": data_mode,
                   "evidence_class": "synthetic_demonstration", "synthetic": True}
    elif kind == "literature":
        payload = {"source_id": "fixture-paper", "title": "Fixture only", "claim_kind": "hypothesis",
                   "evidence_class": "hypothesis", "data_mode": data_mode}
    else:
        payload = {"record_type": "research_cycle", "cycle_id": "fixture-cycle", "data_mode": data_mode,
                   "evidence_class": "engineering_fact"}
    result = _promotion(_dump_case(tmp_path, data_mode, payload))
    assert result.promotion_decision not in {"ADMISSIBLE_FOR_DESCRIPTIVE_REVIEW"}
    assert result.scientific_pass is False
    assert result.allowed_evidence_class != "empirical"


def test_malformed_and_tampered_artifact_rejected_by_loader_and_evaluator(tmp_path: Path):
    malformed = tmp_path / "malformed"
    malformed.mkdir()
    (malformed / "artifact.json").write_text('{"run_id":', encoding="utf-8")
    malformed_result = _promotion(malformed)
    assert malformed_result.promotion_decision == "HOLD_INCONCLUSIVE"
    assert "MALFORMED_INPUT" in malformed_result.reason_codes

    payload = _source_pack()
    payload["files"][0]["sha256"] = "not-a-sha256"
    tampered_result = _promotion(_dump_case(tmp_path, "tampered", payload))
    # Existing gate fingerprints the input, but does not validate this source-pack schema.
    # It must not turn an unrecognized/tampered source record into scientific support.
    assert tampered_result.promotion_decision in {"HOLD_INCONCLUSIVE", "HOLD_INCOMPLETE_PROVENANCE"}
    assert tampered_result.scientific_pass is False
    assert tampered_result.allowed_evidence_class != "empirical"


def test_integrity_and_hash_chain_are_not_scientific_truth(tmp_path: Path):
    payload = _source_pack()
    payload["hash_chain"] = ["b" * 64, "c" * 64]
    result = _promotion(_dump_case(tmp_path, "integrity_only", payload))
    assert result.input_fingerprints
    assert result.promotion_decision in {"HOLD_INCONCLUSIVE", "HOLD_INCOMPLETE_PROVENANCE"}
    assert result.scientific_pass is False
    assert result.scientific_eligibility is False


def _dataset_packet(evidence_class: str, *, conflict: bool) -> dict:
    return {
        "record_type": "SourceSnapshot",
        "schema_version": "dataset-metadata-fixture-v1",
        "dataset_id": "ds-fixture-only",
        "license_status": "conflict" if conflict else "compatible",
        "cohort_status": "unresolved" if conflict else "consistent",
        "cohort_discrepancy": conflict,
        "evidence_class": evidence_class,
        "data_mode": "observational",
        "provenance": {"source_id": "ds-fixture-only", "checksum": "a" * 64,
                       "acquisition": "fixture", "dataset_version": "fixture-v1"},
    }


@pytest.mark.xfail(
    strict=True,
    reason="Known gap: evaluate_case ignores license_status/cohort_status. Handoff to the evidence-gate owner; remove this marker when the gate reads them.",
)
@pytest.mark.parametrize("evidence_class", ["engineering_fact", "descriptive"])
def test_dataset_conflict_metadata_changes_gate_output(tmp_path: Path, evidence_class: str):
    # Regression for the metadata-conflict claim. The gate does not read license_status,
    # cohort_status or cohort_discrepancy (README, "Compatibility assumptions"), so this fails.
    clean = _promotion(_dump_case(tmp_path, "clean", _dataset_packet(evidence_class, conflict=False)))
    conflicted = _promotion(_dump_case(tmp_path, "conflicted", _dataset_packet(evidence_class, conflict=True)))
    assert (conflicted.promotion_decision, tuple(conflicted.reason_codes)) != (
        clean.promotion_decision, tuple(clean.reason_codes))
