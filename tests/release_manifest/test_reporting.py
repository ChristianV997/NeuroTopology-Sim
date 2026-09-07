import json

import pytest

from tools.release_manifest.models import Evidence, ReleaseCandidateManifest, ScientificGateInput
from tools.release_manifest.reporting import NonFiniteValueError, to_finite_json, to_markdown


def _base_manifest() -> ReleaseCandidateManifest:
    return ReleaseCandidateManifest(
        repository="ChristianV997/NeuroTopology-Sim",
        target_branch="main",
        integration_branch="integration",
        source_commit="abc123",
    )


def test_to_finite_json_round_trips():
    manifest = _base_manifest()
    text = to_finite_json(manifest)
    parsed = json.loads(text)
    assert parsed["schema"] == manifest.schema
    assert parsed["repository"] == "ChristianV997/NeuroTopology-Sim"


def test_to_finite_json_rejects_nan():
    manifest = _base_manifest()
    manifest.scientific_gate_status = Evidence(float("nan"), "test")
    with pytest.raises(NonFiniteValueError):
        to_finite_json(manifest)


def test_to_finite_json_rejects_infinity():
    manifest = _base_manifest()
    manifest.scientific_gate_status = Evidence(float("inf"), "test")
    with pytest.raises(NonFiniteValueError):
        to_finite_json(manifest)


def test_to_markdown_contains_key_sections():
    manifest = _base_manifest()
    md = to_markdown(manifest)
    assert "Release Candidate Manifest" in md
    assert "Merge state" in md
    assert "CI classifications" in md
    assert "Scientific gate" in md


def test_deterministic_repeat_json_is_byte_identical():
    manifest = _base_manifest()
    outputs = {to_finite_json(manifest) for _ in range(15)}
    assert len(outputs) == 1
