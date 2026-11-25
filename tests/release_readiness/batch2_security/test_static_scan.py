"""Static scan fixtures for unsafe remote materialization paths."""
from __future__ import annotations

import pytest

from tools.release_readiness.batch2_security import fixtures as fx
from tools.release_readiness.batch2_security.schema import ThreatClass
from tools.release_readiness.batch2_security.static_scan import scan_source_text


@pytest.mark.parametrize(
    "fixture_id,threat",
    [
        ("curl_transfer", ThreatClass.UNAUTHORIZED_SHELL_TRANSFER.value),
        ("wget_transfer", ThreatClass.UNAUTHORIZED_SHELL_TRANSFER.value),
        ("aws_sync", ThreatClass.UNAUTHORIZED_AWS_FULL_TRANSFER.value),
        ("openneuro_download", ThreatClass.FULL_DATASET_DOWNLOAD.value),
        ("boto3_download_file", ThreatClass.UNAUTHORIZED_BOTO3_FULL_OBJECT.value),
        ("boto3_get_object_full", ThreatClass.UNBOUNDED_REMOTE_MATERIALIZATION.value),
        ("urllib_urlopen", ThreatClass.UNRESTRICTED_URLLIB.value),
    ],
)
def test_adversarial_static_fixtures_are_detected(fixture_id: str, threat: str):
    hits = scan_source_text(fx.STATIC_FIXTURES[fixture_id], fixture_id=fixture_id)
    assert any(h.threat_class == threat for h in hits), hits
    assert all(h.remediation_owners for h in hits if h.threat_class == threat)


def test_ranged_get_object_is_not_flagged_as_full_object():
    hits = scan_source_text(
        fx.STATIC_FIXTURES["boto3_get_object_ranged"], fixture_id="boto3_get_object_ranged"
    )
    assert not any(
        h.threat_class == ThreatClass.UNBOUNDED_REMOTE_MATERIALIZATION.value
        and "without Range" in h.message
        for h in hits
    )


def test_unbounded_body_read_detected():
    source = 'payload = client.get_object(Bucket=b, Key=k)["Body"]\ndata = payload.read()\n'
    hits = scan_source_text(source, fixture_id="body_read")
    assert any(
        h.threat_class == ThreatClass.UNBOUNDED_REMOTE_MATERIALIZATION.value for h in hits
    )
