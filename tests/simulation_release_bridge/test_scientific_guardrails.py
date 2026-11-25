"""Tests for repository scientific guardrails in Simulation Release Bridge."""
from __future__ import annotations

import json
from tools.simulation_release_bridge.contracts import (
    SCIENTIFIC_VERDICT_DEFAULT,
    SimulationReleaseBundle,
)
from tools.simulation_release_bridge.builder import SimulationReleaseBuilder
from tools.simulation_release_bridge.fixtures import (
    create_complete_pass_stages,
    create_proxy_only_stages,
    create_synthetic_only_stages,
)


def test_scientific_verdict_is_never_pass():
    """Verify that even for a promoted operational PASS run, scientific_verdict is NOT_APPLICABLE."""
    stages = create_complete_pass_stages()
    builder = SimulationReleaseBuilder("rc-guardrail-test", require_canonical_runner=False)
    bundle = builder.build_from_stages(stages)

    assert bundle.scientific_verdict == SCIENTIFIC_VERDICT_DEFAULT
    assert bundle.scientific_verdict != "PASS"

    bundle_dict = bundle.to_dict()
    assert bundle_dict["scientific_verdict"] == "NOT_APPLICABLE"


def test_synthetic_confinement_to_demo_only():
    """Verify that synthetic runs are permanently tagged synthetic_demo_only and not empirical."""
    stages = create_synthetic_only_stages()
    builder = SimulationReleaseBuilder("rc-synth-test", require_canonical_runner=False)
    bundle = builder.build_from_stages(stages)

    assert bundle.data_mode == "synthetic"
    assert bundle.evidence_class == "synthetic_demo_only"
    assert bundle.promotion_status != "PROMOTED"
    assert bundle.promotion_checksum is None
    assert "synthetic_demo_only" in bundle.to_json()


def test_proxy_confinement_to_proxy_only():
    """Verify that surrogate/proxy runs are permanently tagged proxy_only."""
    stages = create_proxy_only_stages()
    builder = SimulationReleaseBuilder("rc-proxy-test", require_canonical_runner=False)
    bundle = builder.build_from_stages(stages)

    assert bundle.data_mode == "proxy"
    assert bundle.evidence_class == "proxy_only"
    assert bundle.promotion_status != "PROMOTED"
    assert bundle.promotion_checksum is None
    assert "proxy_only" in bundle.to_json()


def test_null_metrics_preserved_never_zero_filled():
    """Verify that None/null values in metrics are preserved without zero-filling."""
    stages = create_complete_pass_stages()
    stages["input_provenance"]["unobserved_metric"] = None
    stages["execution_outcome"]["exit_code"] = None

    builder = SimulationReleaseBuilder("rc-null-test", require_canonical_runner=False)
    bundle = builder.build_from_stages(stages)

    bundle_json = bundle.to_json()
    parsed = json.loads(bundle_json)
    assert parsed["stages"]["input_provenance"]["unobserved_metric"] is None
    assert parsed["stages"]["execution_outcome"]["exit_code"] is None
