"""Identity contract (missing provenance) and metric admission (null, never zero)."""
from __future__ import annotations

import pytest

from awareness_studio.orchestrator.orchestrator import (
    EvidenceState,
    admit_metrics,
    classify_artifact,
    normalize_metric,
)
from tests.orchestrator.conftest import LEAK_SENTINEL, SHA, make_identified


@pytest.mark.parametrize(
    "field, mutate",
    [
        ("source_identity", lambda a: a.pop("source_identity")),
        ("source_identity", lambda a: a.update(source_identity={"uri": "", "sha256": SHA})),
        ("source_identity", lambda a: a.update(source_identity={"uri": "repo://x", "sha256": "abc"})),
        ("input_identity", lambda a: a.pop("input_identity")),
        ("input_identity", lambda a: a.update(input_identity="   ")),
        ("input_identity", lambda a: a.update(input_identity="a-plain-string-is-not-an-identity")),
        ("input_identity", lambda a: a.update(input_identity={"sha256": "abc"})),
        ("execution_identity", lambda a: a.update(execution_identity={**a["execution_identity"], "seed": True})),
        ("execution_identity", lambda a: a.update(execution_identity={**a["execution_identity"], "run_id": "other"})),
        ("execution_identity", lambda a: a.update(execution_identity={**a["execution_identity"], "command_identity": "xyz"})),
        ("artifact_lineage", lambda a: a.update(artifact_lineage={"status": "INCOMPLETE", "artifact_sha256": SHA})),
        ("artifact_lineage", lambda a: a.pop("artifact_lineage")),
    ],
)
def test_missing_identity_makes_engineering_artifact_incomplete_not_evidence(field, mutate):
    artifact = make_identified()
    mutate(artifact)
    decision = classify_artifact(artifact)
    assert decision.state is EvidenceState.INCOMPLETE
    assert decision.evidence_ready is False
    assert field in decision.missing_identities


def test_empirical_artifact_without_provenance_is_incomplete(identified):
    artifact = identified(evidence_class="descriptive_empirical")
    del artifact["source_identity"]
    decision = classify_artifact(artifact)
    assert decision.state is EvidenceState.INCOMPLETE
    assert "source_identity" in decision.missing_identities


def test_complete_identity_is_the_only_path_to_evidence_ready():
    decision = classify_artifact(make_identified())
    assert decision.evidence_ready is True
    assert decision.missing_identities == ()


@pytest.mark.parametrize("value", [None, True, False, float("nan"), float("inf"), "0.5", [0.5]])
def test_normalize_metric_keeps_missing_or_invalid_values_null(value):
    assert normalize_metric(value) is None


def test_normalize_metric_keeps_a_genuine_zero_as_zero_not_null():
    assert normalize_metric(0) == 0.0
    assert normalize_metric(0.0) == 0.0


def test_integer_too_large_for_a_float_stays_null_and_does_not_raise():
    assert normalize_metric(10 ** 400) is None
    assert normalize_metric(-(10 ** 400)) is None


def test_oversized_integer_metric_is_admitted_as_null_on_an_evidence_ready_artifact(identified):
    decision = classify_artifact(identified(metrics={"x": 10 ** 400}))
    assert decision.evidence_ready is True
    assert admit_metrics(decision, {"x": 10 ** 400}) == {"x": None}


def test_admit_metrics_returns_nulls_for_missing_and_nonfinite_values_on_ready_decision():
    decision = classify_artifact(make_identified())
    admitted = admit_metrics(decision, {"I_mean": LEAK_SENTINEL, "Qabs_mean": float("nan"), "f_dress": None})
    assert admitted == {"I_mean": LEAK_SENTINEL, "Qabs_mean": None, "f_dress": None}


def test_admit_metrics_never_invents_a_zero_for_an_absent_key():
    decision = classify_artifact(make_identified())
    admitted = admit_metrics(decision, {"I_mean": LEAK_SENTINEL})
    assert "f_dress" not in admitted
    assert all(value != 0.0 for key, value in admitted.items() if key != "I_mean")


@pytest.mark.parametrize(
    "artifact",
    [
        make_identified(data_mode="synthetic", evidence_class="synthetic_demonstration"),
        make_identified(data_mode="proxy", evidence_class="proxy_inference"),
        make_identified(status="FAILED"),
        make_identified(status="PARTIAL"),
        make_identified(source_identity=None),
    ],
)
def test_metrics_are_withheld_for_every_non_evidence_decision(artifact):
    decision = classify_artifact(artifact)
    assert decision.evidence_ready is False
    assert admit_metrics(decision, artifact["metrics"]) is None


def test_admit_metrics_rejects_non_mapping_payload_even_when_ready():
    decision = classify_artifact(make_identified())
    assert admit_metrics(decision, [LEAK_SENTINEL]) is None
