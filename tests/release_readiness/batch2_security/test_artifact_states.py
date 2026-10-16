"""Failed / partial / timed-out / interrupted / malformed artifact states."""
from __future__ import annotations

import pytest

from tools.release_readiness.batch2_security import fixtures as fx
from tools.release_readiness.batch2_security.artifact_states import (
    classify_artifact_state,
    evaluate_artifact_state,
    expected_incomplete,
)
from tools.release_readiness.batch2_security.schema import ThreatClass


@pytest.mark.parametrize(
    "fixture_id",
    [
        "artifact_failed",
        "artifact_partial",
        "artifact_timed_out",
        "artifact_interrupted",
        "artifact_malformed",
    ],
)
def test_incomplete_artifacts_are_classified(fixture_id: str):
    record = fx.ARTIFACT_FIXTURES[fixture_id]
    status = classify_artifact_state(record)
    assert status == expected_incomplete(fixture_id)
    hits = evaluate_artifact_state(record, fixture_id=fixture_id)
    assert any(h.threat_class == ThreatClass.ARTIFACT_INCOMPLETE_STATE.value for h in hits)


def test_interrupted_claiming_security_pass_is_flagged():
    hits = evaluate_artifact_state(
        fx.ARTIFACT_FIXTURES["artifact_interrupted"], fixture_id="artifact_interrupted"
    )
    assert any("security_pass" in h.message for h in hits)


def test_malformed_claiming_scientific_pass_is_flagged():
    hits = evaluate_artifact_state(
        fx.ARTIFACT_FIXTURES["artifact_malformed"], fixture_id="artifact_malformed"
    )
    assert any(h.threat_class == ThreatClass.SYNTHETIC_TO_EMPIRICAL.value for h in hits)


def test_complete_control_is_not_incomplete():
    hits = evaluate_artifact_state(
        fx.ARTIFACT_FIXTURES["artifact_complete"], fixture_id="artifact_complete"
    )
    assert not any(h.threat_class == ThreatClass.ARTIFACT_INCOMPLETE_STATE.value for h in hits)
