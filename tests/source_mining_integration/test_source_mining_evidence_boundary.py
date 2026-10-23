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
from tools.evidence_promotion_gate.evaluator import evaluate_case, evaluate_path
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


@pytest.mark.parametrize(
    "updates, removals, reason_codes",
    [
        ({}, ("license_status",), ("DATASET_LICENSE_EVIDENCE_MISSING",)),
        ({"license_status": "conflict"}, (), ("DATASET_LICENSE_EVIDENCE_CONFLICT",)),
        ({"license_status": "incompatible"}, (), ("DATASET_LICENSE_EVIDENCE_UNRESOLVED",)),
        ({}, ("cohort_status",), ("DATASET_COHORT_EVIDENCE_MISSING",)),
        ({}, ("cohort_discrepancy",), ("DATASET_COHORT_EVIDENCE_MISSING",)),
        ({"cohort_status": "conflict"}, (), ("DATASET_COHORT_EVIDENCE_CONFLICT",)),
        ({"cohort_discrepancy": True}, (), ("DATASET_COHORT_DISCREPANCY",)),
        ({"network_access_requested": True}, (), ("NETWORK_ACCESS_NOT_APPROVED",)),
    ],
    ids=[
        "license-missing",
        "license-conflicting",
        "license-incompatible",
        "cohort-status-missing",
        "cohort-discrepancy-missing",
        "cohort-conflicting",
        "cohort-discrepant",
        "network-unauthorized",
    ],
)
def test_explicit_empirical_declaration_fails_closed_on_missing_conflicting_or_unauthorized_evidence(
    tmp_path: Path, updates: dict, removals: tuple[str, ...], reason_codes: tuple[str, ...]
):
    packet = _dataset_packet("EMPIRICAL")
    for key in removals:
        packet.pop(key)
    packet.update(updates)
    result = _promotion(_dump_case(tmp_path, "empirical_not_authorized", packet))
    assert result.promotion_decision == "BLOCK_PROMOTION"
    assert result.scientific_pass is False
    assert result.allowed_evidence_class != "empirical"
    assert "EMPIRICAL_PROMOTION_REFUSED" in result.reason_codes
    for reason_code in reason_codes:
        assert reason_code in result.reason_codes


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


def _dataset_packet(
    evidence_class: str,
    *,
    conflict: bool = False,
    acquisition: str = "local_bundle",
    **metadata,
) -> dict:
    return {
        "record_type": "SourceSnapshot",
        "schema_version": "dataset-metadata-fixture-v1",
        "dataset_id": "ds-fixture-only",
        "license_status": "conflict" if conflict else "compatible",
        "cohort_status": "conflict" if conflict else "consistent",
        "cohort_discrepancy": conflict,
        "evidence_class": evidence_class,
        "data_mode": "observational",
        "n_tests": 3,
        "multiplicity_correction": "holm",
        "null_controls": ["phase_shuffle"],
        "provenance": {"source_id": "ds-fixture-only", "checksum": "a" * 64,
                       "acquisition": acquisition, "dataset_version": "fixture-v1"},
        **metadata,
    }


@pytest.mark.parametrize(
    "acquisition",
    ["fixture", "synthetic", "synthetic_demo", "synthetic_demonstration"],
)
def test_fixture_or_synthetic_acquisition_cannot_be_descriptive_eligible(
    tmp_path: Path, acquisition: str
):
    result = _promotion(
        _dump_case(
            tmp_path,
            acquisition,
            _dataset_packet("descriptive_empirical", acquisition=acquisition),
        )
    )
    assert result.promotion_decision == "HOLD_SYNTHETIC_ONLY"
    assert result.allowed_evidence_class == "synthetic_demonstration"
    assert result.synthetic_demo is True
    assert result.scientific_eligibility is False
    assert result.scientific_pass is False
    assert "SYNTHETIC_NOT_EMPIRICAL" in result.reason_codes
    if acquisition == "fixture":
        assert "FIXTURE_NOT_EMPIRICAL" in result.reason_codes


def test_consistent_dataset_declarations_only_allow_descriptive_review(tmp_path: Path):
    # The declarations permit only review here; they do not verify permissions or identity.
    result = _promotion(
        _dump_case(tmp_path, "resolved", _dataset_packet("descriptive_empirical"))
    )
    assert result.promotion_decision == "ADMISSIBLE_FOR_DESCRIPTIVE_REVIEW"
    assert result.allowed_evidence_class == "descriptive_empirical"
    assert result.scientific_eligibility is True
    assert result.scientific_pass is False


@pytest.mark.parametrize(
    "metadata,reason_code",
    [
        ({"license_status": "conflict"}, "DATASET_LICENSE_EVIDENCE_CONFLICT"),
        ({"license_status": "unknown"}, "DATASET_LICENSE_EVIDENCE_UNRESOLVED"),
        ({"license_status": "incompatible"}, "DATASET_LICENSE_EVIDENCE_UNRESOLVED"),
        ({"license_status": None}, "DATASET_LICENSE_EVIDENCE_MISSING"),
        ({"cohort_status": "conflict"}, "DATASET_COHORT_EVIDENCE_CONFLICT"),
        ({"cohort_status": "unknown"}, "DATASET_COHORT_EVIDENCE_UNRESOLVED"),
        ({"cohort_status": "unresolved"}, "DATASET_COHORT_EVIDENCE_UNRESOLVED"),
        ({"cohort_discrepancy": True}, "DATASET_COHORT_DISCREPANCY"),
        ({"cohort_discrepancy": None}, "DATASET_COHORT_EVIDENCE_MISSING"),
        ({"cohort_discrepancy": "false"}, "DATASET_COHORT_EVIDENCE_UNRESOLVED"),
    ],
    ids=[
        "license-conflict", "license-unknown", "license-incompatible", "license-missing",
        "cohort-conflict", "cohort-unknown", "cohort-unresolved", "cohort-discrepancy",
        "cohort-discrepancy-missing", "cohort-discrepancy-malformed",
    ],
)
def test_unresolved_dataset_metadata_blocks_descriptive_review(
    tmp_path: Path, metadata: dict, reason_code: str
):
    payload = _dataset_packet("descriptive_empirical")
    payload.update(metadata)
    result = _promotion(_dump_case(tmp_path, "unresolved", payload))
    assert result.promotion_decision == "HOLD_INCONCLUSIVE"
    assert result.allowed_evidence_class != "descriptive_empirical"
    assert result.scientific_eligibility is False
    assert result.scientific_pass is False
    assert reason_code in result.reason_codes


@pytest.mark.parametrize(
    "metadata,reason_code",
    [
        ({"license_status": "compatible"}, "DATASET_COHORT_EVIDENCE_MISSING"),
        ({"cohort_status": "consistent", "cohort_discrepancy": False}, "DATASET_LICENSE_EVIDENCE_MISSING"),
        ({"license_status": "compatible", "cohort_discrepancy": False}, "DATASET_COHORT_EVIDENCE_MISSING"),
        ({"license_status": "compatible", "cohort_status": "consistent"}, "DATASET_COHORT_EVIDENCE_MISSING"),
    ],
    ids=["missing-cohort", "missing-license", "missing-cohort-status", "missing-discrepancy-flag"],
)
def test_partial_dataset_metadata_is_not_inferred(
    tmp_path: Path, metadata: dict, reason_code: str
):
    payload = _dataset_packet("descriptive_empirical")
    for key in ("license_status", "cohort_status", "cohort_discrepancy"):
        if key not in metadata:
            payload.pop(key)
    payload.update(metadata)
    result = _promotion(_dump_case(tmp_path, "partial", payload))
    assert result.promotion_decision == "HOLD_INCONCLUSIVE"
    assert result.scientific_eligibility is False
    assert reason_code in result.reason_codes


@pytest.mark.parametrize(
    "metadata",
    [
        {"license_status": None, "cohort_status": None, "cohort_discrepancy": None},
        {"license_status": "conflict", "cohort_status": "conflict", "cohort_discrepancy": True},
    ],
    ids=["missing-dataset-readiness", "conflicting-dataset-readiness"],
)
def test_dataset_metadata_does_not_restrict_engineering_only_reporting(
    tmp_path: Path, metadata: dict
):
    result = _promotion(
        _dump_case(
            tmp_path,
            "metadata_only",
            _dataset_packet("engineering_fact", **metadata),
        )
    )
    assert result.promotion_decision == "ADMISSIBLE_FOR_ENGINEERING_REPORT"
    assert result.allowed_evidence_class == "engineering_fact"
    assert result.scientific_pass is False
    assert result.scientific_eligibility is False
    assert not any(code.startswith("DATASET_") for code in result.reason_codes)


def test_conflicting_metadata_across_sources_blocks_descriptive_review(tmp_path: Path):
    case = _dump_case(
        tmp_path,
        "multiple_metadata_sources",
        _dataset_packet("descriptive_empirical"),
    )
    path = case / "artifact.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["dataset_metadata"] = {
        "license_status": "conflict",
        "cohort_status": "consistent",
        "cohort_discrepancy": False,
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    result = _promotion(case)
    assert result.promotion_decision == "HOLD_INCONCLUSIVE"
    assert "DATASET_LICENSE_EVIDENCE_CONFLICT" in result.reason_codes
    assert result.scientific_eligibility is False


def test_metadata_readiness_is_preserved_by_public_path_and_json_serialization(tmp_path: Path):
    case = _dump_case(
        tmp_path,
        "serialized_conflict",
        _dataset_packet("descriptive_empirical", conflict=True),
    )
    result = evaluate_path(case)[0]
    payload = result.to_dict()
    assert payload["promotion_decision"] == "HOLD_INCONCLUSIVE"
    assert payload["scientific_eligibility"] is False
    assert payload["scientific_pass"] is False
    assert "DATASET_LICENSE_EVIDENCE_CONFLICT" in payload["reason_codes"]
    assert "DATASET_COHORT_EVIDENCE_CONFLICT" in payload["reason_codes"]
    encoded = json.dumps(payload, allow_nan=False)
    assert json.loads(encoded)["promotion_decision"] == "HOLD_INCONCLUSIVE"
