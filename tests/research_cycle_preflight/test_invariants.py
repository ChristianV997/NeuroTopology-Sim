"""Requirements 3-5: fail closed on hard blockers, never emit a
scientific PASS / formal Bayes factor / causal / biological / topology
confirmation or fabricated provenance, and produce deterministic finite
JSON.
"""
from __future__ import annotations

import json

import pytest

from tools.research_cycle_preflight.compose import run_preflight
from tools.research_cycle_preflight.models import NEVER_EMITTED

from .conftest import ALL_FIXTURE_NAMES


@pytest.mark.parametrize("fixture_name", ALL_FIXTURE_NAMES)
def test_never_emitted_fields_are_always_present_and_always_the_same_value(load_request, fixture_name):
    result = run_preflight(load_request(fixture_name), now="2026-01-01T00:00:00+00:00")
    assert result["never_emits"] == NEVER_EMITTED
    assert result["never_emits"]["scientific_pass"] is False
    assert result["never_emits"]["formal_bayes_factor"] is None
    assert result["never_emits"]["causal_confirmation"] is False
    assert result["never_emits"]["biological_confirmation"] is False
    assert result["never_emits"]["topology_confirmation"] is False


def test_injecting_fake_confirmation_fields_into_the_request_has_no_effect(load_request):
    """A caller cannot smuggle a fabricated result past the preflight by
    adding the fields it would have produced itself -- run_preflight
    only ever reads its own declared request vocabulary (plan, claim,
    prior_run_dir, data_access_request)."""
    request = load_request("complete_plan")
    request["scientific_pass"] = True
    request["formal_bayes_factor"] = 999.0
    request["causal_confirmation"] = True
    request["biological_confirmation"] = True
    request["topology_confirmation"] = True
    request["cleared_for_execution"] = "OVERRIDDEN"
    request["operational_readiness"] = "READY"

    result = run_preflight(request, now="2026-01-01T00:00:00+00:00")

    assert result["never_emits"] == NEVER_EMITTED
    # the legitimate fields are unaffected -- still derived from the real plan
    assert result["operational_readiness"] == "READY"
    assert result["cleared_for_execution"] is True


def test_cleared_for_execution_defaults_to_false_not_true(load_request):
    """Fail-closed: an empty/malformed request must never default to
    cleared."""
    result = run_preflight({}, now="2026-01-01T00:00:00+00:00")
    assert result["operational_readiness"] == "BLOCKED"
    assert result["cleared_for_execution"] is False


def test_no_fixture_ever_fabricates_provenance(load_request):
    """Requirement: never emit fabricated provenance. A plan/claim that
    declares no provenance must come back with that absence intact, not
    a filled-in placeholder."""
    result = run_preflight(load_request("missing_provenance"), now="2026-01-01T00:00:00+00:00")
    plan_audit = result["validators_composed"]["research_plan_quality"]
    provenance_criterion = next(c for c in plan_audit["criteria"] if c["dimension"] == "source_quality_provenance")
    assert provenance_criterion["status"] == "missing"
    assert "no sources were provided" in provenance_criterion["detail"]


@pytest.mark.parametrize("fixture_name", ALL_FIXTURE_NAMES)
def test_fixtures_are_deterministic_across_repeated_evaluation(load_request, fixture_name):
    request = load_request(fixture_name)
    result1 = run_preflight(request, now="2026-01-01T00:00:00+00:00")
    result2 = run_preflight(request, now="2026-01-01T00:00:00+00:00")
    assert json.dumps(result1, sort_keys=True) == json.dumps(result2, sort_keys=True)
    assert result1["report_sha256"] == result2["report_sha256"]


@pytest.mark.parametrize("fixture_name", ALL_FIXTURE_NAMES)
def test_report_is_finite_json(load_request, fixture_name):
    """``allow_nan=False`` raises ValueError on an actual non-finite
    float (a real NaN/Infinity object), so a successful dump here is
    the real finiteness proof -- unlike a crude substring search, which
    would misfire on the ``non_finite_artifacts`` fixture: its
    diagnostic *message* legitimately contains the English word "NaN"
    while describing why that artifact was blocked."""
    result = run_preflight(load_request(fixture_name), now="2026-01-01T00:00:00+00:00")
    text = json.dumps(result, sort_keys=True, allow_nan=False)
    assert json.loads(text) == result


def test_report_checksum_excludes_itself_from_its_own_input(load_request):
    import hashlib

    result = run_preflight(load_request("complete_plan"), now="2026-01-01T00:00:00+00:00")
    stripped = {k: v for k, v in result.items() if k != "report_sha256"}
    expected = hashlib.sha256(json.dumps(stripped, sort_keys=True, allow_nan=False).encode("utf-8")).hexdigest()
    assert result["report_sha256"] == expected


def test_omitted_now_only_changes_generated_at_and_checksum(load_request):
    request = load_request("complete_plan")
    result1 = run_preflight(request)
    result2 = run_preflight(request)
    volatile = {"generated_at", "report_sha256"}
    stable1 = {k: v for k, v in result1.items() if k not in volatile}
    stable2 = {k: v for k, v in result2.items() if k not in volatile}
    assert stable1 == stable2
