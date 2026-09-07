from __future__ import annotations

from tools.research_record.compiler import compile_record

NOW = "2026-01-01T00:00:00+00:00"


def test_synthetic_falsification_pass_is_a_conflict(manifest_factory):
    manifest = manifest_factory(
        {
            "falsification": {
                "results": [
                    {"hypothesis_id": "HYP-SYN-1", "claim_class": "synthetic", "data_mode": "synthetic", "metric_type": "proxy_K", "metric_value": 4.7, "verdict": "PASS"}
                ]
            }
        }
    )

    record = compile_record(manifest, now=NOW)

    conflicts = [c for c in record["conflicts"] if c["kind"] == "synthetic_pass_claim"]
    assert any(c["id"] == "HYP-SYN-1" for c in conflicts)
    assert record["final_release_recommendation"] == "BLOCKED_BY_SCIENTIFIC_VALIDATION"
    assert record["scientific_status"]["label"] == "blocked"
    assert record["scientific_status"]["synthetic_pass_claim_violations"] == 1


def test_proxy_topology_pass_is_a_conflict(manifest_factory):
    manifest = manifest_factory(
        {"topology_validation": {"checks": [{"name": "beta1_gate", "metric_family": "graph_beta_1", "data_mode": "proxy", "metric_value": 1.0, "verdict": "PASS"}]}}
    )

    record = compile_record(manifest, now=NOW)
    conflicts = [c for c in record["conflicts"] if c["kind"] == "synthetic_pass_claim"]
    assert any(c["id"] == "beta1_gate" for c in conflicts)


def test_contribution_claiming_empirical_pass_from_synthetic_claim_class_is_a_conflict(manifest_factory):
    manifest = manifest_factory(
        {
            "agent_contributions": {
                "repository": None,
                "baseline_commit": None,
                "evidence_source": "github_api",
                "inventory_is_not_evidence": True,
                "required_warnings": [],
                "contributions": [
                    {
                        "id": "nts-pr-999",
                        "agent": "claude",
                        "branch": "b",
                        "pr_number": 999,
                        "merge_status": "open",
                        "verification_status": {"scientific_pass": "claimed"},
                        "research_classification": {"claim_class": "synthetic", "empirical_pass_allowed": False},
                        "limitations": [],
                    }
                ],
            }
        }
    )

    record = compile_record(manifest, now=NOW)
    conflicts = [c for c in record["conflicts"] if c["kind"] == "synthetic_pass_claim"]
    assert any(c["id"] == "nts-pr-999" for c in conflicts)


def test_timed_out_check_is_not_a_synthetic_pass_conflict(manifest_factory):
    # Rule 8: a timeout is not a scientific outcome at all -- it must not
    # even be evaluated against the synthetic-PASS guardrail, since
    # TIMEOUT != PASS.
    manifest = manifest_factory(
        {"falsification": {"results": [{"hypothesis_id": "HYP-TO-1", "claim_class": "synthetic", "data_mode": "synthetic", "metric_type": "proxy_K", "metric_value": None, "verdict": "TIMEOUT"}]}}
    )

    record = compile_record(manifest, now=NOW)
    assert not [c for c in record["conflicts"] if c["kind"] == "synthetic_pass_claim"]
    assert record["final_release_recommendation"] == "BLOCKED_BY_CI"


def test_empirical_pass_is_not_a_conflict(manifest_factory):
    manifest = manifest_factory(
        {"falsification": {"results": [{"hypothesis_id": "HYP-EMP-1", "claim_class": "empirical", "data_mode": "empirical", "metric_type": "bayes_factor", "metric_value": 12.0, "verdict": "PASS"}]}}
    )

    record = compile_record(manifest, now=NOW)
    assert not [c for c in record["conflicts"] if c["kind"] == "synthetic_pass_claim"]
