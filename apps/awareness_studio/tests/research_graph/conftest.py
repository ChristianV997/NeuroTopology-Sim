"""Shared fixtures for the evidence graph test suite."""
from __future__ import annotations

import pytest


@pytest.fixture
def complete_manifest_data() -> dict:
    """Fixture returning a comprehensive manifest covering all 9 node types and 10 edge types."""
    return {
        "metadata": {
            "campaign_id": "topo-falsification-2026",
            "environment": "offline-ci",
        },
        "sources": [
            {
                "source_id": "src-2024-001",
                "title": "Persistent Homology of Neural State Transitions",
                "doi": "10.1016/j.neuroimage.2024.120001",
                "source_type": "journal_article",
                "evidence_tier": "T1_verified_primary",
                "verification_status": "verified",
                "status": "active",
                "tags": ["topology", "eeg"],
            },
            {
                "source_id": "src-2023-002",
                "title": "Legacy Pairwise Connectivity Baseline",
                "doi": "10.1016/j.neuroimage.2023.110002",
                "source_type": "journal_article",
                "status": "superseded",
                "tags": ["pairwise"],
            }
        ],
        "claims": [
            {
                "claim_id": "clm-topo-01",
                "source_id": "src-2024-001",
                "claim_text": "Triadic hypergraph representations capture non-random simplicial coordination in microstates.",
                "claim_class": "correlational",
                "linked_hypothesis": "hyp-triadic-01",
                "confidence": 0.85,
            }
        ],
        "hypotheses": [
            {
                "hypothesis_id": "hyp-triadic-01",
                "precise_claim": "Higher-order simplicial coordination persists across temporal transitions.",
                "null_prediction": "Simplicial coordination does not exceed phase-randomized surrogate distributions.",
                "falsification_criterion": "Simplicial Betti-1 difference p >= 0.05 against null surrogate.",
                "feature_family": "triadic_hypergraph",
                "status": "active",
                "claim_ids": ["clm-topo-01"],
                "evidence_links": ["ev-emp-01"],
                "contradictory_evidence_links": [],
                "blocked_by": [],
                "provenance": {"source_id": "src-2024-001"},
            },
            {
                "hypothesis_id": "hyp-legacy-02",
                "precise_claim": "Pairwise connectivity is sufficient to model phase transitions.",
                "null_prediction": "No higher-order residual variance.",
                "falsification_criterion": "Triadic model outperforms pairwise by delta AIC > 10.",
                "status": "superseded",
                "provenance": {"source_id": "src-2023-002"},
            }
        ],
        "experiments": [
            {
                "experiment_id": "exp-triadic-01",
                "hypothesis_id": "hyp-triadic-01",
                "domain": "higher_order_spectra",
                "design_type": "paired_cohort",
                "dataset_ids": ["ds005620"],
                "power_analysis": {"n": 30, "power": 0.85},
            }
        ],
        "runs": [
            {
                "run_id": "run-triadic-001",
                "experiment_id": "exp-triadic-01",
                "data_mode": "empirical",
                "verdict": "PASS",
                "elapsed_s": 1.25,
                "metrics": {"betti_1_stability": 0.45, "p_val": 0.01},
                "artifacts": {
                    "summary.json": "outputs/run_001/summary.json",
                    "topology_curve.csv": "outputs/run_001/curve.csv",
                },
            }
        ],
        "artifacts": [
            {
                "artifact_id": "art-external-report",
                "label": "Audit Validation Report",
                "generator_id": "run-triadic-001",
                "validates_id": "run-triadic-001",
                "properties": {"format": "pdf", "size_bytes": 1024},
            }
        ],
        "validations": [
            {
                "validation_id": "val-falsification-01",
                "check_name": "surrogate_null_stability_test",
                "verdict": "PASS",
                "run_id": "run-triadic-001",
                "hypothesis_id": "hyp-triadic-01",
                "metrics": {"surrogate_z_score": 3.4},
            }
        ],
        "theory_revisions": [
            {
                "revision_id": "rev-2026-01",
                "hypothesis_id": "hyp-triadic-01",
                "previous_status": "proposed",
                "new_status": "active",
                "reason_codes": ["surrogate_validation_passed"],
                "supersedes_id": "hyp-legacy-02",
            }
        ],
        "evidence": [
            {
                "evidence_id": "ev-emp-01",
                "hypothesis_id": "hyp-triadic-01",
                "experiment_id": "exp-triadic-01",
                "source_id": "src-2024-001",
                "data_type": "empirical_dataset",
                "is_synthetic": False,
                "is_contradictory": False,
                "metrics_observed": {"effect_size": 0.42, "p_value": 0.01},
            }
        ]
    }
