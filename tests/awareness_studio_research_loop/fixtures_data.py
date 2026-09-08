"""Shared fixture data for research-cycle orchestrator tests (plain
module, not a pytest fixture, so it can be imported directly by any test
file without relying on conftest-relative-import quirks)."""
from __future__ import annotations

import copy
from typing import Any


def complete_cycle_overrides() -> dict[str, Any]:
    """A fully-passing, single-hypothesis research cycle (H1/C1/S1/E1),
    reaching PAPER_DRAFT_READY with zero gate violations. Individual
    tests deep-copy and mutate this to construct one specific failure
    mode at a time."""
    return copy.deepcopy(
        {
            "literature_evidence": {
                "sources": [{"source_id": "S1", "title": "A Fixture Paper About Decentering", "source_checksum": "abc123", "evidence_tier": "T1_verified_primary", "verification_status": "verified"}],
                "claims": [{"claim_id": "C1", "source_id": "S1", "claim_text": "Decentering correlates with reduced rumination.", "claim_class": "correlational", "claim_status": "empirical", "linked_hypothesis": "H1"}],
                "hypothesis_links": [{"hypothesis_id": "H1", "claim_ids": ["C1"], "relationship": "supports"}],
                "experiment_links": [],
                "evidence_updates": [{"update_id": "U1", "entity_type": "hypothesis", "entity_id": "H1", "update_type": "amended", "reason": "Incorporated E1 null-test PASS result"}],
            },
            "hypothesis_registry": {
                "hypotheses": [{"hypothesis_id": "H1", "statement": "We hypothesize that decentering training changes topology metric Qz.", "claim_ids": [], "null_prediction": "No difference in Qz between groups.", "falsification_criterion": None}]
            },
            "experiment_plans": {
                "plans": [
                    {
                        "experiment_id": "E1",
                        "hypothesis_id": "H1",
                        "falsification_criterion": "Reject if p>0.05 two-tailed",
                        "metrics": [{"name": "Qz_delta", "unit": "dimensionless", "feature_family": "topology"}],
                        "dataset_id": "ds123",
                        "dataset_checksum": "data_sha",
                        "held_out_split_locked": True,
                        "is_predictive": True,
                        "preregistered": True,
                        "synthetic": False,
                    }
                ]
            },
            "execution_results": {
                "executions": [
                    {
                        "experiment_id": "E1",
                        "status": "completed",
                        "data_mode": "empirical",
                        "input_checksums": ["in1"],
                        "output_checksums": ["out1"],
                        "software_commit": "abc1234",
                        "runtime_seconds": 12.5,
                        "dependency_state": "satisfied",
                        "metric_values": [{"name": "Qz_delta", "value": 0.42, "unit": "dimensionless"}],
                    }
                ]
            },
            "null_surrogate_results": {"null_tests": [{"experiment_id": "E1", "method": "phase_randomization", "verdict": "PASS", "statistic": 2.1, "notes": "n=500 surrogates"}]},
            "theory_state": {"theory_id": "T1", "version": 1, "statements": ["Decentering training modulates topology metrics."], "contradictory_evidence_ids": [], "alternative_explanations": ["placebo/expectation effects"]},
            "reviewer_decisions": {"decisions": [{"subject_type": "hypothesis", "subject_id": "H1", "decision": "approved", "reviewer": "pi", "notes": "reviewed"}]},
        }
    )
