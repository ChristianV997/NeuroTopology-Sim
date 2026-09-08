"""Requirement 7: never use forbidden strong-claim language, or
unqualified causal language, unless the record is formal evidence and
has an approved human-review decision."""
from __future__ import annotations

from tools.awareness_studio_research_loop.compiler import compile_research_cycle
from tools.awareness_studio_research_loop.render_markdown import check_unsupported_promotion
from tests.awareness_studio_research_loop.fixtures_data import complete_cycle_overrides

NOW = "2026-01-01T00:00:00+00:00"


def test_forbidden_phrase_in_a_claim_is_flagged_and_hedged(manifest_factory):
    overrides = complete_cycle_overrides()
    overrides["literature_evidence"]["claims"][0]["claim_text"] = "This study demonstrated quantum coherence in the meditative state."
    overrides["literature_evidence"]["claims"][0]["claim_status"] = "unsupported"
    manifest = manifest_factory(overrides)

    report = compile_research_cycle(manifest, now=NOW)

    assert any(v["id"] == "C1" for v in report["unsupported_promotion_violations"])
    assert "[UNVERIFIED CLAIM" in report["paper_draft_markdown"]


def test_causal_language_in_a_result_without_formal_evidence_is_flagged(manifest_factory):
    overrides = complete_cycle_overrides()
    overrides["execution_results"]["executions"][0]["metric_values"][0]["name"] = "training caused a reduction"
    # Make sure it stays non-formal (so the causal language cannot be licensed).
    overrides["experiment_plans"]["plans"][0]["preregistered"] = False
    manifest = manifest_factory(overrides)

    report = compile_research_cycle(manifest, now=NOW)

    assert any(v["id"] == "E1" for v in report["unsupported_promotion_violations"])


def test_forbidden_phrase_licensed_by_formal_evidence_and_approval_is_not_flagged():
    violation = check_unsupported_promotion(text="demonstrated quantum coherence", evidence_class="formal", review_decision="approved")
    assert violation is None


def test_forbidden_phrase_without_approval_is_flagged_even_if_formal():
    violation = check_unsupported_promotion(text="demonstrated quantum coherence", evidence_class="formal", review_decision="pending")
    assert violation is not None


def test_hypothesis_statement_causal_wording_is_not_flagged_but_forbidden_phrase_is(manifest_factory):
    # Hypothesizing causation is ordinary pre-evidence science.
    overrides = complete_cycle_overrides()
    overrides["hypothesis_registry"]["hypotheses"][0]["statement"] = "We hypothesize that decentering causes reduced rumination."
    manifest = manifest_factory(overrides)
    report = compile_research_cycle(manifest, now=NOW)
    assert not [v for v in report["unsupported_promotion_violations"] if v["id"] == "H1"]

    overrides2 = complete_cycle_overrides()
    overrides2["hypothesis_registry"]["hypotheses"][0]["statement"] = "This confirmed liberation from suffering."
    manifest2 = manifest_factory(overrides2)
    report2 = compile_research_cycle(manifest2, now=NOW)
    assert any(v["id"] == "H1" for v in report2["unsupported_promotion_violations"])
