"""Offline MOABB protocol-conformance: manifests, validation, leakage, checksums."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from dataset_importers.moabb_importer import import_moabb_candidates_from_fixture
from tools.moabb_protocol_conformance.leakage import assess_subject_leakage
from tools.moabb_protocol_conformance.manifest import (
    build_from_candidate_dict,
    build_protocol_manifest,
)
from tools.moabb_protocol_conformance.metadata import extract_dataset_fields, reject_fabricated_counts
from tools.moabb_protocol_conformance.schema import EVIDENCE_CLASS, PROTOCOL_SCHEMA_VERSION, ConformanceStatus
from tools.moabb_protocol_conformance.serialization import dumps, sha256_hex
from tools.moabb_protocol_conformance.upstream import UPSTREAM_REFERENCES
from tools.moabb_protocol_conformance.validation import validate_protocol_manifest

REPO = Path(__file__).resolve().parents[3]
FIXTURES = REPO / "tools" / "moabb_protocol_conformance" / "fixtures"
CREATED_AT = "2026-10-16T00:00:00Z"


def _protocol(**overrides):
    base = {
        "protocol_version": "moabb-protocol/v1-test",
        "unit_of_analysis": "subject",
        "split_policy": "cross_subject_leave_one_out",
        "evaluation_metric": "accuracy",
        "exclusions": [],
        "requires_labels": True,
        "notes": "hermetic test protocol",
        "created_at": CREATED_AT,
    }
    base.update(overrides)
    return base


def _bnci_candidate():
    records = import_moabb_candidates_from_fixture(FIXTURES / "moabb_metadata_fixture.json")
    by_id = {r.source_dataset_id: r for r in records}
    return by_id["BNCI2014-001"]


def _sparse_candidate():
    records = import_moabb_candidates_from_fixture(FIXTURES / "moabb_metadata_fixture.json")
    by_id = {r.source_dataset_id: r for r in records}
    return by_id["SparseMeta"]


def test_conforming_manifest_from_candidate_record():
    rec = _bnci_candidate()
    manifest = build_protocol_manifest(
        rec,
        protocol_version="moabb-protocol/v1-test",
        unit_of_analysis="subject",
        split_policy="cross_subject_leave_one_out",
        evaluation_metric="accuracy",
        exclusions=[],
        created_at=CREATED_AT,
    )
    payload = manifest.to_dict()
    assert payload["schema_version"] == PROTOCOL_SCHEMA_VERSION
    assert payload["evidence_class"] == EVIDENCE_CLASS
    assert payload["benchmark_executed"] is False
    assert payload["local_data_available"] is False
    assert payload["scientific_validation_claimed"] is False
    assert payload["network_accessed"] is False
    assert payload["conformance"]["ok"] is True
    assert payload["conformance"]["status"] == ConformanceStatus.CONFORMING.value
    assert payload["dataset"]["dataset_identifier"]["value"] == "BNCI2014-001"
    assert payload["dataset"]["task"]["value"] == "imagery"
    assert payload["dataset"]["modality"]["value"] == "EEG"
    assert payload["dataset"]["event_label_mapping"]["labels"] == ["left_hand", "right_hand"]
    assert payload["dataset"]["subjects"]["count"] == 9
    assert payload["dataset"]["sessions"]["count"] == 2
    assert payload["compatibility"]["candidate_record_schema"] == "DatasetCandidateRecordV1"
    assert payload["result_summary"]["result_is"] == "protocol_described_conformance_only"
    # License unknown from importer is preserved as warning, not invention.
    assert payload["dataset"]["license_access"]["license"] == "unknown"
    assert "license_unknown" in payload["conformance"]["warnings"]


def test_incomplete_when_labels_absent_and_required():
    rec = _sparse_candidate()
    manifest = build_protocol_manifest(
        rec,
        protocol_version="moabb-protocol/v1-test",
        unit_of_analysis="subject",
        split_policy="cross_subject_leave_one_out",
        evaluation_metric="accuracy",
        exclusions=[],
        requires_labels=True,
        created_at=CREATED_AT,
    )
    conf = manifest.to_dict()["conformance"]
    assert conf["ok"] is False
    assert conf["status"] == ConformanceStatus.INCOMPLETE.value
    assert "absent_labels_required_by_protocol" in conf["violations"]


def test_incomplete_missing_required_protocol_fields():
    candidate = {
        "source_catalog": "moabb",
        "source_dataset_id": "X",
        "condition_labels": ["a", "b"],
        "modalities": ["EEG"],
        "task_labels": ["imagery"],
    }
    manifest = build_from_candidate_dict(
        candidate,
        {
            "protocol_version": "v1",
            "unit_of_analysis": "not_a_unit",
            "split_policy": "bogus_split_policy",
            "evaluation_metric": "unspecified",
            "exclusions": [],
            "created_at": CREATED_AT,
        },
    )
    conf = manifest.to_dict()["conformance"]
    assert conf["status"] == ConformanceStatus.INCOMPLETE.value
    assert "missing_or_invalid_unit_of_analysis" in conf["violations"]
    assert "missing_or_invalid_split_policy" in conf["violations"]
    assert "missing_or_invalid_evaluation_metric" in conf["violations"]

    unspecified = build_from_candidate_dict(
        candidate,
        {
            "protocol_version": "v1",
            "unit_of_analysis": "subject",
            "split_policy": "unspecified",
            "evaluation_metric": "accuracy",
            "exclusions": [],
            "created_at": CREATED_AT,
        },
    )
    uconf = unspecified.to_dict()["conformance"]
    assert uconf["status"] == ConformanceStatus.INCOMPLETE.value
    assert "incomplete_split_declaration" in uconf["violations"]


def test_exclusions_must_be_explicit():
    with pytest.raises(ValueError, match="exclusions"):
        build_protocol_manifest(
            _bnci_candidate(),
            protocol_version="v1",
            unit_of_analysis="subject",
            split_policy="cross_subject_leave_one_out",
            evaluation_metric="accuracy",
            exclusions=None,
        )


def test_conflicting_license_access_blocks():
    # Raw fixture entry (not through importer) preserves conflicting license_risk.
    raw = {
        "code": "ConflictLicense",
        "paradigm": "imagery",
        "event_id": {"left_hand": 1, "right_hand": 2},
        "subject_count": 5,
        "license": "unknown",
        "license_risk": "permissive_low",
        "access_status": "public",
        "modalities": ["EEG"],
    }
    fields = extract_dataset_fields(raw)
    assert fields["license_access"]["trust"] == "conflicting"
    manifest = build_from_candidate_dict(raw, _protocol())
    conf = manifest.to_dict()["conformance"]
    assert conf["status"] == ConformanceStatus.BLOCKED.value
    assert "conflicting_license_or_access_metadata" in conf["violations"]


def test_unknown_license_preserved_not_invented():
    raw = {
        "source_dataset_id": "NoLicense",
        "task_labels": ["p300"],
        "modalities": ["EEG"],
        "condition_labels": ["target", "non_target"],
    }
    fields = extract_dataset_fields(raw)
    assert fields["license_access"]["license"] == "unknown"
    assert fields["license_access"]["trust"] == "unknown"
    assert fields["local_availability"]["value"] == "unknown"
    assert fields["local_availability"]["trust"] == "unknown"
    assert fields["subjects"]["count"] is None
    assert fields["subjects"]["trust"] == "unknown"


def test_fabricated_counts_and_labels_rejected():
    assert "sample_count_without_source" in reject_fabricated_counts(
        {"sample_count": 999, "sample_count_source": "invented"}
    )
    assert "fabricated_labels" in reject_fabricated_counts({"fabricated_labels": True})
    candidate = {
        "source_dataset_id": "Fab",
        "task_labels": ["imagery"],
        "modalities": ["EEG"],
        "condition_labels": ["a", "b"],
    }
    manifest = build_from_candidate_dict(
        candidate,
        _protocol(sample_count=42, sample_count_source="invented", fabricated_labels=True),
    )
    violations = manifest.to_dict()["conformance"]["violations"]
    assert "sample_count_without_source" in violations
    assert "fabricated_labels" in violations


def test_random_trial_split_fails_for_subject_leakage():
    assessment = assess_subject_leakage(
        split_policy="random_trial_split",
        unit_of_analysis="trial",
    )
    assert assessment["status"] == "failed"
    assert assessment["subject_leakage"] is True

    manifest = build_from_candidate_dict(
        _bnci_candidate().to_dict(),
        json.loads((FIXTURES / "protocol_leaky.json").read_text(encoding="utf-8"))
        | {"created_at": CREATED_AT},
    )
    conf = manifest.to_dict()["conformance"]
    assert conf["status"] == ConformanceStatus.FAILED.value
    assert "subject_leakage" in conf["violations"]


def test_custom_holdout_overlap_fails():
    assessment = assess_subject_leakage(
        split_policy="custom_subject_holdout",
        train_subject_ids=["1", "2", "3"],
        test_subject_ids=["3", "4"],
        unit_of_analysis="subject",
    )
    assert assessment["status"] == "failed"
    assert assessment["overlap_subject_ids"] == ["3"]

    manifest = build_from_candidate_dict(
        _bnci_candidate().to_dict(),
        _protocol(
            split_policy="custom_subject_holdout",
            train_subject_ids=["1", "2"],
            test_subject_ids=["2", "5"],
        ),
    )
    assert manifest.to_dict()["conformance"]["status"] == ConformanceStatus.FAILED.value


def test_custom_holdout_disjoint_ok():
    manifest = build_from_candidate_dict(
        _bnci_candidate().to_dict(),
        _protocol(
            split_policy="custom_subject_holdout",
            train_subject_ids=["1", "2", "3"],
            test_subject_ids=["4", "5"],
        ),
    )
    assert manifest.to_dict()["conformance"]["status"] == ConformanceStatus.CONFORMING.value


def test_within_subject_split_with_subject_unit_inconclusive():
    manifest = build_from_candidate_dict(
        _bnci_candidate().to_dict(),
        _protocol(
            unit_of_analysis="subject",
            split_policy="within_session_kfold",
        ),
    )
    conf = manifest.to_dict()["conformance"]
    assert conf["status"] == ConformanceStatus.INCONCLUSIVE.value
    assert "leakage_inconclusive" in conf["warnings"]


def test_deterministic_checksum_and_serialization():
    fields = _protocol()
    m1 = build_from_candidate_dict(_bnci_candidate().to_dict(), fields)
    m2 = build_from_candidate_dict(_bnci_candidate().to_dict(), fields)
    p1 = m1.to_dict()
    p2 = m2.to_dict()
    assert p1["manifest_checksum_sha256"] == p2["manifest_checksum_sha256"]
    assert dumps(p1) == dumps(p2)
    # Checksum excludes nested conformance (attached after hashing content).
    body = {k: v for k, v in p1.items() if k not in {"manifest_checksum_sha256", "conformance", "result_summary"}}
    # Recompute the same way as build: checksum of payload before conformance attach.
    # The stored checksum is over payload without conformance/result_summary.
    assert len(p1["manifest_checksum_sha256"]) == 64
    assert sha256_hex({"a": 1, "b": [2, 3]}) == sha256_hex({"b": [2, 3], "a": 1})


def test_manifest_is_deterministic_without_wall_clock_timestamp():
    fields = _protocol()
    fields.pop("created_at")
    first = build_from_candidate_dict(_bnci_candidate().to_dict(), fields).to_json()
    second = build_from_candidate_dict(_bnci_candidate().to_dict(), fields).to_json()
    assert first == second
    assert json.loads(first)["created_at"] is None


def test_forbidden_claim_phrases_fail_validation():
    candidate = {
        "source_dataset_id": "Claims",
        "task_labels": ["imagery"],
        "modalities": ["EEG"],
        "condition_labels": ["a", "b"],
    }
    manifest = build_from_candidate_dict(
        candidate,
        _protocol(notes="This benchmark ran and data are locally available."),
    )
    violations = manifest.to_dict()["conformance"]["violations"]
    assert any(v.startswith("forbidden_claim:") for v in violations)


def test_local_availability_fabricated_blocked():
    payload = build_from_candidate_dict(_bnci_candidate().to_dict(), _protocol()).to_dict()
    payload["local_data_available"] = True
    # dataset local_availability trust remains unknown from importer path
    verdict = validate_protocol_manifest(payload)
    assert "local_availability_fabricated" in verdict["violations"]
    assert verdict["status"] == ConformanceStatus.BLOCKED.value


def test_upstream_references_present_and_not_installed():
    refs = {r["name"]: r for r in UPSTREAM_REFERENCES}
    assert refs["moabb"]["license"] == "BSD-3-Clause"
    assert refs["moabb"]["installed"] is False
    assert refs["moabb"]["executed"] is False
    assert refs["moabb"]["cloned"] is False
    assert refs["mne"]["integration_mode"] == "reference_only"
    assert refs["mne"]["installed"] is False
    manifest = build_from_candidate_dict(_bnci_candidate().to_dict(), _protocol())
    names = [r["name"] for r in manifest.to_dict()["upstream_references"]]
    assert "moabb" in names
    assert "mne" in names


def test_raw_fixture_preserves_sampling_and_channels_when_supplied():
    raw = json.loads((FIXTURES / "moabb_metadata_fixture.json").read_text(encoding="utf-8"))["datasets"][0]
    fields = extract_dataset_fields(raw)
    assert fields["sampling"]["sampling_rate_hz"] == 250.0
    assert fields["sampling"]["trust"] == "verified"
    assert fields["channels"]["count"] == 22
    assert fields["channels"]["trust"] == "verified"
    assert fields["event_label_mapping"]["source"] == "fixture_event_id"


@pytest.mark.parametrize("value", [float("inf"), float("-inf")])
def test_infinite_sampling_rate_is_not_verified(value):
    fields = extract_dataset_fields({"source_dataset_id": "synthetic", "sampling_rate_hz": value})
    assert fields["sampling"]["sampling_rate_hz"] is None
    assert fields["sampling"]["trust"] == "unknown"


def test_fractional_count_is_not_silently_truncated():
    fields = extract_dataset_fields({"source_dataset_id": "synthetic", "subject_count": 2.5})
    assert fields["subjects"]["count"] is None
    assert fields["subjects"]["trust"] == "unknown"


def test_boolean_sampling_rate_is_not_coerced_to_one_hertz():
    fields = extract_dataset_fields({"source_dataset_id": "synthetic", "sampling_rate_hz": True})
    assert fields["sampling"]["sampling_rate_hz"] is None
    assert fields["sampling"]["trust"] == "unknown"


def test_cli_conforming_and_leaky_exit_codes(tmp_path):
    out_ok = tmp_path / "ok.json"
    out_bad = tmp_path / "bad.json"
    cmd_base = [
        sys.executable,
        "-m",
        "tools.moabb_protocol_conformance",
        "--moabb-fixture",
        str(FIXTURES / "moabb_metadata_fixture.json"),
    ]
    r_ok = subprocess.run(
        cmd_base
        + [
            "--protocol-json",
            str(FIXTURES / "protocol_conforming.json"),
            "--output",
            str(out_ok),
            "--limit",
            "1",
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    assert r_ok.returncode == 0, r_ok.stderr
    payload = json.loads(out_ok.read_text(encoding="utf-8"))
    assert payload["conformance"]["ok"] is True
    assert payload["benchmark_executed"] is False

    r_bad = subprocess.run(
        cmd_base
        + [
            "--protocol-json",
            str(FIXTURES / "protocol_leaky.json"),
            "--output",
            str(out_bad),
            "--limit",
            "1",
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    assert r_bad.returncode == 1
    bad = json.loads(out_bad.read_text(encoding="utf-8"))
    assert bad["conformance"]["status"] == "failed"


def test_cli_rejects_nonpositive_limit():
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "tools.moabb_protocol_conformance",
            "--moabb-fixture",
            str(FIXTURES / "moabb_metadata_fixture.json"),
            "--protocol-json",
            str(FIXTURES / "protocol_conforming.json"),
            "--limit",
            "0",
        ],
        cwd=str(REPO),
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "limit must be a positive integer" in result.stderr


def test_claims_block_never_asserts_benchmark_ran():
    conf = validate_protocol_manifest(
        build_from_candidate_dict(_bnci_candidate().to_dict(), _protocol()).to_dict()
    )
    assert conf["claims"]["benchmark_executed"] is False
    assert conf["claims"]["local_data_available_asserted"] is False
    assert conf["claims"]["scientific_validation_claimed"] is False
    assert conf["claims"]["result_is"] == "protocol_described_conformance_only"
