"""Rule 4: a proxy Bayes factor is not formal evidence.

Distinct from test_synthetic_pass_claim.py: these cases check the
proxy-vs-formal *labeling* itself (metric_type display label,
claim_class-derived evidence-strength label), independent of whether a
PASS was claimed.
"""
from __future__ import annotations

from tools.research_record.compiler import compile_record
from tools.research_record.guardrails import evidence_strength_label, metric_label

NOW = "2026-01-01T00:00:00+00:00"


def test_proxy_k_metric_is_never_labeled_bayes_factor(manifest_factory):
    manifest = manifest_factory(
        {
            "falsification": {
                "results": [
                    {"hypothesis_id": "HYP-PROXY-1", "claim_class": "proxy", "data_mode": "empirical", "metric_type": "proxy_K", "metric_value": 3.1, "verdict": "INCONCLUSIVE"}
                ]
            }
        }
    )

    record = compile_record(manifest, now=NOW)
    result = record["falsification_semantics"]["results"][0]

    assert result["is_formal_bayes_factor"] is False
    assert result["metric_display_label"] == "proxy_K (not a formal Bayes factor)"
    assert result["claim_class"] == "proxy"
    # A proxy result with no PASS claim is not a synthetic_pass_claim conflict...
    assert not [c for c in record["conflicts"] if c["kind"] == "synthetic_pass_claim"]
    # ...but it is still surfaced as non-formal in scientific_limitations.
    assert any("proxy quantities are not formal Bayes factors" in item for item in record["scientific_limitations"])


def test_only_literal_bayes_factor_metric_type_is_formal():
    assert metric_label("bayes_factor")["is_formal_bayes_factor"] is True
    assert metric_label("bayes_factor")["metric_display_label"] == "Bayes factor"
    for other in ("proxy_K", "approx_bf", "Bayes_Factor", "BAYES_FACTOR", ""):
        result = metric_label(other)
        assert result["is_formal_bayes_factor"] is False
        assert "not a formal Bayes factor" in result["metric_display_label"]


def test_evidence_strength_label_axis_matches_claim_class():
    assert evidence_strength_label("empirical") == "formal empirical evidence"
    assert evidence_strength_label("proxy") == "proxy evidence (not formal)"
    assert evidence_strength_label("synthetic") == "synthetic evidence (not formal, not empirical)"
    assert evidence_strength_label("not-a-real-value") == "evidence class unknown"
