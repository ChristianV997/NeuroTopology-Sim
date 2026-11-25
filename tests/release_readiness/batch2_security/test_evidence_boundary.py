"""Provenance / checksum / commit / synthetic-to-empirical boundaries."""
from __future__ import annotations

import pytest

from tools.release_readiness.batch2_security import fixtures as fx
from tools.release_readiness.batch2_security.evidence_boundary import evaluate_evidence_record
from tools.release_readiness.batch2_security.schema import ThreatClass


def test_complete_evidence_has_no_findings():
    assert evaluate_evidence_record(fx.EVIDENCE_FIXTURES["evidence_complete"]) == []


@pytest.mark.parametrize(
    "fixture_id,threat",
    [
        ("fabricated_provenance", ThreatClass.FABRICATED_PROVENANCE.value),
        ("missing_checksum", ThreatClass.MISSING_CHECKSUM.value),
        ("missing_commit", ThreatClass.MISSING_COMMIT_IDENTITY.value),
        ("synthetic_to_empirical", ThreatClass.SYNTHETIC_TO_EMPIRICAL.value),
    ],
)
def test_adversarial_evidence_fixtures(fixture_id: str, threat: str):
    hits = evaluate_evidence_record(fx.EVIDENCE_FIXTURES[fixture_id], fixture_id=fixture_id)
    assert any(h.threat_class == threat for h in hits), hits
