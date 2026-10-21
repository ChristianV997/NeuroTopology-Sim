"""Requirement 6: tests for complete engineering plans, missing
provenance, synthetic-only inputs, partial runs, network violations,
unsupported claims, invalid labels, missing null metadata, and
non-finite artifacts -- each isolated to exactly one fixture and
verified against the real, composed validators before being locked in
here (see conftest.py::EXPECTED_CASES).
"""
from __future__ import annotations

import pytest

from tools.research_cycle_preflight.compose import run_preflight

from .conftest import ALL_FIXTURE_NAMES, EXPECTED_CASES


@pytest.mark.parametrize("fixture_name", ALL_FIXTURE_NAMES)
def test_fixture_matches_expected_decision(load_request, fixture_name):
    expected_operational, expected_scientific, expected_cleared = EXPECTED_CASES[fixture_name]
    result = run_preflight(load_request(fixture_name), now="2026-01-01T00:00:00+00:00")
    assert result["operational_readiness"] == expected_operational
    assert result["scientific_admissibility"] == expected_scientific
    assert result["cleared_for_execution"] is expected_cleared


def test_complete_plan_is_the_only_fixture_cleared_for_execution(load_request):
    cleared = [name for name in ALL_FIXTURE_NAMES if EXPECTED_CASES[name][2]]
    assert cleared == ["complete_plan"], (
        "this suite proves discrimination, not blanket rejection or blanket approval -- "
        "exactly one fixture should be clean enough to clear"
    )


def test_missing_provenance_reports_both_hard_blockers(load_request):
    result = run_preflight(load_request("missing_provenance"), now="2026-01-01T00:00:00+00:00")
    joined = " ".join(result["operational_blockers"])
    assert "source_quality_provenance" in joined
    assert "dataset_identity_checksum" in joined


def test_network_violation_reports_both_data_access_violations(load_request):
    result = run_preflight(load_request("network_violation"), now="2026-01-01T00:00:00+00:00")
    data_access = result["validators_composed"]["data_access_policy"]
    assert set(data_access["violations"]) == {"FULL_DATASET_DOWNLOAD_REJECTED", "BOUNDED_TRANSFER_NOT_DECLARED"}
    assert data_access["status"] == "BLOCKED"


def test_partial_run_is_classified_but_not_a_hard_operational_blocker(load_request):
    result = run_preflight(load_request("partial_run"), now="2026-01-01T00:00:00+00:00")
    assert result["validators_composed"]["simulation_artifact_lineage"]["status"] == "PARTIAL"
    assert result["operational_readiness"] == "NEEDS_REVISION"
    assert result["operational_blockers"] == []


def test_non_finite_artifact_is_a_hard_operational_blocker(load_request):
    result = run_preflight(load_request("non_finite_artifacts"), now="2026-01-01T00:00:00+00:00")
    assert result["validators_composed"]["simulation_artifact_lineage"]["status"] == "BLOCKED"
    assert result["operational_readiness"] == "BLOCKED"
    assert any("artifact_lineage" in blocker for blocker in result["operational_blockers"])


def test_synthetic_only_inputs_block_scientific_admissibility_not_operational_readiness(load_request):
    result = run_preflight(load_request("synthetic_only_inputs"), now="2026-01-01T00:00:00+00:00")
    assert result["validators_composed"]["research_claim_gate"]["decision"] == "CLAIM_SYNTHETIC_ONLY"
    assert result["scientific_admissibility"] == "BLOCKED"
    assert result["operational_readiness"] == "READY"
    assert result["cleared_for_execution"] is False


def test_unsupported_claim_is_rejected_by_the_real_gate(load_request):
    result = run_preflight(load_request("unsupported_claim"), now="2026-01-01T00:00:00+00:00")
    assert result["validators_composed"]["research_claim_gate"]["decision"] == "CLAIM_REJECTED"
    assert "UNSUPPORTED_CLAIM_CLASS" in result["validators_composed"]["research_claim_gate"]["reason_codes"]
    assert result["scientific_admissibility"] == "BLOCKED"


def test_no_claim_is_not_applicable_not_admissible(load_request):
    """Requirement: a preflight run before a claim has been drafted must
    never read as scientifically admissible by default."""
    result = run_preflight(load_request("complete_plan"), now="2026-01-01T00:00:00+00:00")
    assert result["validators_composed"]["research_claim_gate"] is None
    assert result["scientific_admissibility"] == "NOT_APPLICABLE"

