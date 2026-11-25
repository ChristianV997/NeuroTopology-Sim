"""Failed simulation, partial run, blocked execution, malformed artifacts, and unsupported claims."""
from __future__ import annotations

import pytest

from awareness_studio.orchestrator.orchestrator import EvidenceState, admit_metrics, assess_claim, classify_artifact
from tests.orchestrator.conftest import LEAK_SENTINEL, SHA, make_identified


# ── failed simulation / partial run / blocked execution ──────────────────────

@pytest.mark.parametrize(
    "status, expected",
    [
        ("FAILED", EvidenceState.FAILED),
        ("ERROR", EvidenceState.FAILED),
        ("INFRASTRUCTURE_FAILURE", EvidenceState.FAILED),
        ("PARTIAL", EvidenceState.INCOMPLETE),
        ("TIMEOUT", EvidenceState.INCOMPLETE),
        ("NOT_RUN", EvidenceState.INCOMPLETE),
        ("BLOCKED", EvidenceState.BLOCKED),
        ("NOT_IMPLEMENTED", EvidenceState.BLOCKED),
    ],
)
def test_run_status_overrides_an_otherwise_complete_engineering_artifact(status, expected):
    artifact = make_identified(status=status)
    decision = classify_artifact(artifact)
    assert decision.state is expected
    assert decision.evidence_ready is False
    assert admit_metrics(decision, artifact["metrics"]) is None


def test_failed_simulation_keeps_its_recorded_status_reason():
    decision = classify_artifact(make_identified(status="FAILED"))
    assert "run_status:FAILED" in decision.reasons


def test_completed_status_does_not_by_itself_grant_evidence_when_identity_is_missing():
    artifact = make_identified(status="COMPLETED")
    del artifact["artifact_lineage"]
    decision = classify_artifact(artifact)
    assert decision.state is EvidenceState.INCOMPLETE


def test_run_status_cannot_rescue_a_synthetic_artifact_into_evidence():
    decision = classify_artifact(make_identified(status="COMPLETED", data_mode="synthetic",
                                                 evidence_class="synthetic_demonstration"))
    assert decision.state is EvidenceState.SYNTHETIC
    assert decision.evidence_ready is False


@pytest.mark.parametrize(
    "status, expected",
    [
        ("CANCELLED", EvidenceState.FAILED),
        ("ABORTED", EvidenceState.FAILED),
        ("KILLED", EvidenceState.FAILED),
        ("ERRORED", EvidenceState.FAILED),
        ("FAILURE", EvidenceState.FAILED),
        ("FAIL", EvidenceState.FAILED),
        ("SUCCESS_WITH_ERRORS", EvidenceState.FAILED),
        ("TIMED_OUT", EvidenceState.INCOMPLETE),
        ("INCONCLUSIVE", EvidenceState.INCOMPLETE),
        ("RUNNING", EvidenceState.INCOMPLETE),
        ("IN_PROGRESS", EvidenceState.INCOMPLETE),
        ("PASS", EvidenceState.INCOMPLETE),  # a verdict word, not a run-completion status
        ("A_NEW_STATUS", EvidenceState.INCOMPLETE),  # unrecognized statuses fail closed
        ("PLANNING_ONLY", EvidenceState.PLANNING),
        ("REVIEW_REQUIRED", EvidenceState.REVIEW_REQUIRED),
        ("EVIDENCE_READY_FOR_REVIEW", EvidenceState.REVIEW_REQUIRED),
    ],
)
def test_status_outside_the_completed_vocabulary_is_never_evidence_ready(identified, status, expected):
    decision = classify_artifact(identified(status=status))
    assert decision.state is expected
    assert decision.evidence_ready is False


def test_engineering_execution_complete_with_identity_is_evidence_ready(identified):
    decision = classify_artifact(identified(status="ENGINEERING_EXECUTION_COMPLETE"))
    assert decision.state is EvidenceState.ENGINEERING
    assert decision.evidence_ready is True


@pytest.mark.parametrize("value", [None, "", "   "])
def test_null_or_blank_status_is_invalid_and_never_treated_as_absent(identified, value):
    assert classify_artifact(identified(status=value)).state is EvidenceState.INVALID


def test_evidence_requires_a_declared_run_status(identified):
    artifact = identified()
    del artifact["status"]
    decision = classify_artifact(artifact)
    assert decision.state is EvidenceState.INCOMPLETE
    assert "run_status_undeclared" in decision.reasons


def test_failed_execution_state_is_not_overridden_by_a_completed_status(identified):
    decision = classify_artifact(identified(status="COMPLETED", execution_state="FAILED"))
    assert decision.state is EvidenceState.FAILED
    assert decision.evidence_ready is False


def test_one_unrecognized_status_blocks_readiness_even_beside_a_completed_status(identified):
    decision = classify_artifact(identified(status="COMPLETED", state="WHATEVER"))
    assert decision.state is EvidenceState.INCOMPLETE
    assert decision.evidence_ready is False


def test_untrusted_status_text_is_never_echoed_into_reasons(identified):
    decision = classify_artifact(identified(status=f"COMPLETED I_mean={LEAK_SENTINEL}"))
    assert decision.state is EvidenceState.INCOMPLETE
    assert "run_status:unrecognized" in decision.reasons
    assert all(str(LEAK_SENTINEL) not in reason for reason in decision.reasons)


# ── malformed artifacts ───────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "artifact",
    [
        ["not", "an", "object"],
        "a bare string",
        None,
    ],
)
def test_non_object_artifact_is_invalid(artifact):
    decision = classify_artifact(artifact)
    assert decision.state is EvidenceState.INVALID
    assert decision.evidence_ready is False


def test_missing_run_id_is_invalid_not_incomplete(identified):
    artifact = identified()
    del artifact["run_id"]
    assert classify_artifact(artifact).state is EvidenceState.INVALID


def test_non_finite_metric_makes_the_whole_artifact_invalid(identified):
    artifact = identified(metrics={"I_mean": float("nan")})
    decision = classify_artifact(artifact)
    assert decision.state is EvidenceState.INVALID
    assert any(reason.startswith("malformed_artifact:non_finite_value") for reason in decision.reasons)


def test_non_text_status_is_invalid(identified):
    assert classify_artifact(identified(status=7)).state is EvidenceState.INVALID


def test_non_text_data_mode_is_invalid(identified):
    assert classify_artifact(identified(data_mode=["synthetic"])).state is EvidenceState.INVALID


def test_artifact_nested_beyond_the_depth_limit_is_invalid(identified):
    nested: dict = {}
    cursor = nested
    for _ in range(200):
        cursor["child"] = {}
        cursor = cursor["child"]
    decision = classify_artifact(identified(extra=nested))
    assert decision.state is EvidenceState.INVALID
    assert decision.reasons == ("malformed_artifact:nesting_too_deep",)


def test_unexpected_error_during_classification_fails_closed_as_invalid(monkeypatch, identified):
    import awareness_studio.orchestrator.orchestrator as orchestrator_module

    def _unexpected(artifact):
        raise TypeError("unexpected shape")

    monkeypatch.setattr(orchestrator_module, "_identity_gaps", _unexpected)
    decision = classify_artifact(identified())
    assert decision.state is EvidenceState.INVALID
    assert decision.evidence_ready is False
    assert decision.reasons == ("malformed_artifact:unexpected_value",)


def test_non_finite_reason_does_not_echo_the_offending_key(identified):
    decision = classify_artifact(identified(metrics={f"I_mean_{LEAK_SENTINEL}": float("nan")}))
    assert decision.reasons == ("malformed_artifact:non_finite_value",)


def test_run_id_carrying_free_text_is_invalid_and_not_echoed(identified):
    decision = classify_artifact(identified(run_id=f"I_mean={LEAK_SENTINEL}"))
    assert decision.state is EvidenceState.INVALID
    assert decision.reasons == ("malformed_artifact:run_id_invalid",)


def test_unknown_evidence_class_reason_does_not_echo_the_declared_text(identified):
    decision = classify_artifact(identified(evidence_class=f"novel_{LEAK_SENTINEL}"))
    assert decision.state is EvidenceState.INVALID
    assert decision.reasons == ("unknown_evidence_class",)


# ── claim gate ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "statement",
    [
        "This pipeline is a clinical screening tool.",
        "The metric is a biomarker of consciousness detection.",
        "The signal proves a causal mechanism.",
        "This detects a meditation stage.",
    ],
)
def test_banned_claim_language_is_unsupported_even_for_planning(statement):
    decision = assess_claim({"statement": statement, "requested_state": "planning"})
    assert decision.state is EvidenceState.INVALID
    assert any(reason.startswith("unsupported_claim:banned_language") for reason in decision.reasons)


def test_empirical_claim_without_evidence_is_unsupported():
    decision = assess_claim({"statement": "The condition difference is measurable.", "requested_state": "empirical"})
    assert decision.state is EvidenceState.INVALID
    assert "unsupported_claim:no_evidence_for_requested_state" in decision.reasons


def test_empirical_claim_backed_only_by_proxy_evidence_is_unsupported(identified):
    proxy = identified(data_mode="proxy", evidence_class="proxy_inference")
    decision = assess_claim({"statement": "The condition difference is measurable.",
                             "requested_state": "empirical", "evidence": [proxy]})
    assert decision.state is EvidenceState.INVALID


def test_claim_carrying_a_formal_bayes_factor_is_unsupported():
    decision = assess_claim({"statement": "Engineering check passed.", "requested_state": "engineering",
                             "formal_bayes_factor": 3.2})
    assert decision.state is EvidenceState.INVALID


def test_planning_proposal_is_review_required_and_never_evidence():
    decision = assess_claim({"statement": "A reviewable plan exists.", "requested_state": "planning"})
    assert decision.state is EvidenceState.REVIEW_REQUIRED
    assert decision.evidence_ready is False


def test_engineering_claim_backed_by_identified_engineering_evidence_is_accepted(identified):
    decision = assess_claim({"statement": "The configured pipeline runs deterministically.",
                             "requested_state": "engineering", "evidence": [identified()]})
    assert decision.state is EvidenceState.ENGINEERING
    assert decision.evidence_ready is True


def test_engineering_claim_with_one_unidentified_evidence_item_is_rejected(identified):
    incomplete = identified()
    del incomplete["source_identity"]
    decision = assess_claim({"statement": "The pipeline runs deterministically.",
                             "requested_state": "engineering", "evidence": [identified(), incomplete]})
    assert decision.state is EvidenceState.INVALID


def test_malformed_claim_is_invalid():
    assert assess_claim("not a claim").state is EvidenceState.INVALID
    assert assess_claim({"statement": "", "requested_state": "planning"}).state is EvidenceState.INVALID
    assert assess_claim({"statement": "x", "requested_state": "not_a_state"}).state is EvidenceState.INVALID


def test_claim_evidence_never_carries_metric_value_into_decision(identified):
    decision = assess_claim({"statement": "The pipeline runs deterministically.",
                             "requested_state": "engineering", "evidence": [identified()]})
    assert LEAK_SENTINEL not in decision.to_dict().values()
