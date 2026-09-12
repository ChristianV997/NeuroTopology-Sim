"""Shared fixtures for the scientific-release conformance suite.

Every test here consumes the real, canonical, already-merged
``tools/research_claim_gate/gate.py`` and
``tools/simulation_artifacts/extractor.py`` as read-only dependencies --
this suite adds fixtures and assertions, it does not modify or duplicate
either implementation.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"

#: The claim gate's own eight decision states, generalized into the
#: four-way outcome taxonomy this task asks for. CLAIM_ADMISSIBLE is
#: deliberately absent -- it is the one decision an adversarial fixture
#: must never reach.
DECISION_BUCKET: dict[str, str] = {
    "CLAIM_REQUIRES_REVIEW": "REVIEW_REQUIRED",
    "CLAIM_DOWNGRADED": "DOWNGRADED",
    "CLAIM_REJECTED": "BLOCKED",
    "CLAIM_INCOMPLETE": "INCOMPLETE",
    "CLAIM_SYNTHETIC_ONLY": "BLOCKED",
    "CLAIM_PROVENANCE_INVALID": "BLOCKED",
    "CLAIM_NOT_COMPARABLE": "BLOCKED",
}

#: (fixture_name, expected_decision, expected_reason_code) for every
#: required adversarial scenario plus the bonus cases -- verified against
#: the real gate before being committed here (see
#: docs/release/scientific_conformance.md's "How these fixtures were
#: derived" section).
ADVERSARIAL_CASES: tuple[tuple[str, str, str], ...] = (
    ("synthetic_output_as_empirical", "CLAIM_SYNTHETIC_ONLY", "SYNTHETIC_NOT_EMPIRICAL"),
    ("proxy_dependence_as_causality", "CLAIM_DOWNGRADED", "PROXY_NOT_CAUSAL"),
    ("fabricated_provenance", "CLAIM_PROVENANCE_INVALID", "INVALID_PROVENANCE"),
    ("missing_checksum", "CLAIM_PROVENANCE_INVALID", "INCOMPLETE_PROVENANCE"),
    ("invalid_condition_labels", "CLAIM_REJECTED", "UNVERIFIED_LABELS"),
    ("train_test_subject_overlap", "CLAIM_REJECTED", "SUBJECT_SESSION_OVERLAP"),
    ("temporal_leakage", "CLAIM_REJECTED", "FUTURE_PAST_LEAKAGE"),
    ("future_sample_features", "CLAIM_REJECTED", "FUTURE_PAST_LEAKAGE"),
    ("missing_multiplicity_metadata", "CLAIM_REQUIRES_REVIEW", "MISSING_MULTIPLICITY_CORRECTION"),
    ("missing_null_model", "CLAIM_REQUIRES_REVIEW", "MISSING_NULL_CONTROLS"),
    ("full_dataset_download_request", "CLAIM_REJECTED", "NETWORK_ACCESS_NOT_APPROVED"),
    ("network_policy_violation", "CLAIM_REJECTED", "NETWORK_ACCESS_NOT_APPROVED"),
    ("dry_run_placeholder_metrics", "CLAIM_DOWNGRADED", "FORMAL_METHOD_NOT_VALIDATED"),
    ("topology_namespace_confusion", "CLAIM_REJECTED", "GRAPH_BETA1_NOT_SPATIAL_CHARGE"),
    ("physiology_namespace_confusion", "CLAIM_REJECTED", "PARASYMPATHETIC_NOT_EQUANIMITY"),
    # Bonus, strengthening coverage beyond the 15 required scenarios:
    ("triadic_dependence_as_causal", "CLAIM_REJECTED", "TRIADIC_NOT_CAUSAL"),
    ("unsupported_claim_class", "CLAIM_REJECTED", "UNSUPPORTED_CLAIM_CLASS"),
    ("unknown_claim_class", "CLAIM_REJECTED", "UNKNOWN_CLAIM_CLASS"),
)

ADVERSARIAL_FIXTURE_NAMES: tuple[str, ...] = tuple(name for name, _, _ in ADVERSARIAL_CASES)


def bucket_for_decision(decision: str) -> str:
    return DECISION_BUCKET.get(decision, "UNKNOWN")


@pytest.fixture
def load_fixture():
    def _load(name: str) -> dict[str, Any]:
        return json.loads((FIXTURES_DIR / f"{name}.json").read_text(encoding="utf-8"))

    return _load
