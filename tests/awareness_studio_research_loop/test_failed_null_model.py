from __future__ import annotations

from tools.awareness_studio_research_loop.compiler import compile_research_cycle
from tests.awareness_studio_research_loop.fixtures_data import complete_cycle_overrides

NOW = "2026-01-01T00:00:00+00:00"


def test_failed_null_test_requires_theory_revision(manifest_factory):
    overrides = complete_cycle_overrides()
    overrides["null_surrogate_results"]["null_tests"][0]["verdict"] = "FAIL"
    manifest = manifest_factory(overrides)

    report = compile_research_cycle(manifest, now=NOW)

    assert report["cycle_states"]["H1"]["state"] == "THEORY_REVISION_REQUIRED"
    assert any("FAIL" in reason for reason in report["cycle_states"]["H1"]["reasons"])


def test_timed_out_null_test_is_validation_pending_not_a_verdict(manifest_factory):
    overrides = complete_cycle_overrides()
    overrides["null_surrogate_results"]["null_tests"][0]["verdict"] = "TIMEOUT"
    manifest = manifest_factory(overrides)

    report = compile_research_cycle(manifest, now=NOW)

    assert report["cycle_states"]["H1"]["state"] == "VALIDATION_PENDING"


def test_inconclusive_null_test_is_its_own_state(manifest_factory):
    overrides = complete_cycle_overrides()
    overrides["null_surrogate_results"]["null_tests"][0]["verdict"] = "INCONCLUSIVE"
    manifest = manifest_factory(overrides)

    report = compile_research_cycle(manifest, now=NOW)

    assert report["cycle_states"]["H1"]["state"] == "INCONCLUSIVE"
