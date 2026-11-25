from __future__ import annotations

from tools.mobile_report.compiler import compile_report

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

    report = compile_report(manifest, now=NOW)

    conflicts = [c for c in report["conflicts"] if c["kind"] == "synthetic_pass_claim"]
    assert any(c["id"] == "HYP-SYN-1" for c in conflicts)
    assert report["final_release_recommendation"] == "BLOCKED_BY_SCIENTIFIC_VALIDATION"


def test_proxy_topology_pass_is_a_conflict(manifest_factory):
    manifest = manifest_factory(
        {"topology_validation": {"checks": [{"name": "beta1_gate", "metric_family": "graph_beta_1", "data_mode": "proxy", "metric_value": 1.0, "verdict": "PASS"}]}}
    )

    report = compile_report(manifest, now=NOW)
    conflicts = [c for c in report["conflicts"] if c["kind"] == "synthetic_pass_claim"]
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

    report = compile_report(manifest, now=NOW)
    conflicts = [c for c in report["conflicts"] if c["kind"] == "synthetic_pass_claim"]
    assert any(c["id"] == "nts-pr-999" for c in conflicts)


def test_empirical_pass_is_not_a_conflict(manifest_factory):
    manifest = manifest_factory(
        {"falsification": {"results": [{"hypothesis_id": "HYP-EMP-1", "claim_class": "empirical", "data_mode": "empirical", "metric_type": "bayes_factor", "metric_value": 12.0, "verdict": "PASS"}]}}
    )

    report = compile_report(manifest, now=NOW)
    assert not [c for c in report["conflicts"] if c["kind"] == "synthetic_pass_claim"]
