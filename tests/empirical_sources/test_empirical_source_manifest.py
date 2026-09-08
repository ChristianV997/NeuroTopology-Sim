"""Offline tests for empirical-source preregistration manifests."""
from __future__ import annotations

import json
import socket
from pathlib import Path

from configs.empirical_sources.manifest import (
    SCHEMA,
    serialize_report,
    validate_manifest,
)

TEMPLATE = Path(__file__).resolve().parents[2] / "configs" / "empirical_sources" / "preregistration.template.yaml"


def _valid(**overrides):
    document = {
        "dataset_identifier": "operator-local-cohort-001",
        "source_url": "https://example.invalid/local-only",
        "local_root": "/tmp/nts-prereg-local",
        "subject_identifiers": ["sub-01", "sub-02", "sub-03", "sub-04", "sub-05", "sub-06", "sub-07", "sub-08"],
        "condition_labels": ["condition_a", "condition_b"],
        "pairing_key": "subject_id",
        "expected_sampling_rate_hz": {"min": 200.0, "max": 1000.0},
        "channel_count_range": {"min": 8, "max": 256},
        "montage_requirement": "operator_supplied_10-20",
        "minimum_paired_subject_count": 8,
        "exclusion_rules": ["exclude sessions without both conditions"],
        "primary_outcome_metrics": ["paired_condition_difference"],
        "secondary_outcomes": ["channel_count_completeness"],
        "null_models": ["label_permutation", "phase_shuffle"],
        "multiplicity_correction": "holm",
        "stopping_rule": "fixed_n_equals_minimum_paired_subject_count",
        "missing_data_rule": "exclude_incomplete_pairs",
        "synthetic_data_policy": {"policy": "synthetic_never_empirical", "treat_as_empirical": False},
        "provenance_requirements": {"checksum": "required", "origin_label": "required"},
        "origin": "empirical_local",
    }
    document.update(overrides)
    return document


def test_valid_source_manifest():
    report = validate_manifest(_valid())
    assert report.status == "VALID_PREREGISTRATION"
    assert report.evidence_claim_allowed is False
    assert report.scientific_status == "preregistration_only"
    assert "not empirical evidence" in " ".join(report.reasons)


def test_missing_subject():
    report = validate_manifest(_valid(subject_identifiers=[]))
    assert report.status == "INCOMPLETE_PREREGISTRATION"
    assert any("subject" in reason for reason in report.reasons)


def test_ambiguous_labels():
    report = validate_manifest(
        _valid(
            condition_labels=["condition_a"],
            inferred_condition_mapping={"*med*.edf": "meditation"},
        )
    )
    assert report.status == "AMBIGUOUS_CONDITIONS"


def test_insufficient_pairing_metadata():
    report = validate_manifest(_valid(pairing_key=""))
    assert report.status == "INCOMPLETE_PREREGISTRATION"
    assert any("pairing" in reason for reason in report.reasons)


def test_missing_multiple_comparison_correction():
    document = _valid()
    document["multiplicity_correction"] = None
    report = validate_manifest(document)
    assert report.status == "INCOMPLETE_PREREGISTRATION"
    assert any("multiplic" in reason for reason in report.reasons)


def test_synthetic_source():
    report = validate_manifest(_valid(origin="synthetic_demo"))
    assert report.status == "SYNTHETIC_DEMO_ONLY"
    marked = validate_manifest(
        _valid(synthetic_data_policy={"policy": "allow_synthetic_pass", "treat_as_empirical": True})
    )
    assert marked.status == "INVALID_PROVENANCE"


def test_deterministic_serialization():
    first = serialize_report(validate_manifest(_valid()))
    second = serialize_report(validate_manifest(_valid()))
    assert first == second
    loaded = json.loads(first)
    assert loaded["schema"] == SCHEMA
    assert loaded["data_downloaded"] is False
    assert loaded["statistics_computed"] is False


def test_no_network_execution(monkeypatch):
    def blocked(*args, **kwargs):
        raise AssertionError("network call attempted")

    monkeypatch.setattr(socket, "create_connection", blocked)
    monkeypatch.setattr(socket, "socket", blocked)
    report = validate_manifest(_valid())
    assert report.status == "VALID_PREREGISTRATION"
    template = validate_manifest(TEMPLATE)
    assert template.status == "UNAVAILABLE_SOURCE"
    assert template.evidence_claim_allowed is False
