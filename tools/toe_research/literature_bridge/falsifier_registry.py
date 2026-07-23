from __future__ import annotations

import argparse
import json
from pathlib import Path


FALSIFIERS = [
    {
        "id": "F1",
        "claim_affected": "Q/Qabs/fdress add residual predictive value beyond spectral and complexity baselines",
        "affected_subsystems": ["BTC-ICFT", "Level T", "M+T residual benchmark"],
        "observable_required": "cross-validated delta AUC and calibration against M-only baselines",
        "failure_condition": "No reproducible residual predictive improvement under specified controls",
        "claim_demotion_action": "Retain topology values as descriptive telemetry only",
        "next_experiment_or_simulation": "Run preregistered multi-dataset M-only versus M+T comparisons",
        "priority": "critical",
    },
    {
        "id": "F2",
        "claim_affected": "Anesthesia LOC/ROC has a consistent Q/fdress signature",
        "affected_subsystems": ["anesthesia wedge", "EEG target-aware validation"],
        "observable_required": "explicit LOC/ROC labels aligned to artifact-controlled EEG windows",
        "failure_condition": "No stable direction or timing of topology change across cohorts",
        "claim_demotion_action": "Remove state-signature language and report dataset-specific null results",
        "next_experiment_or_simulation": "Replicate with explicit labels across independent anesthesia datasets",
        "priority": "critical",
    },
    {
        "id": "F3",
        "claim_affected": "Observed winding is physiological rather than an interpolation artifact",
        "affected_subsystems": ["phase field", "EEG spatial interpolation", "Q telemetry"],
        "observable_required": "sensor-space and interpolation-sensitivity controls",
        "failure_condition": "Winding appears only after interpolation or changes under benign interpolation choices",
        "claim_demotion_action": "Quarantine interpolated winding from empirical interpretation",
        "next_experiment_or_simulation": "Run sensor-grid, montage, and interpolation ablations",
        "priority": "critical",
    },
    {
        "id": "F4",
        "claim_affected": "Topology metrics are robust to resolution and null controls",
        "affected_subsystems": ["Q", "Qabs", "fdress", "grid topology"],
        "observable_required": "grid-refinement, phase-randomization, and spatial-null distributions",
        "failure_condition": "Metrics fail convergence or are indistinguishable from specified nulls",
        "claim_demotion_action": "Restrict metrics to exploratory engineering diagnostics",
        "next_experiment_or_simulation": "Expand resolution sweeps and null ensembles",
        "priority": "critical",
    },
    {
        "id": "F5",
        "claim_affected": "Hodge, sheaf, or Laplacian telemetry improves on simpler metrics",
        "affected_subsystems": ["Hodge telemetry", "sheaf consistency", "persistent Laplacian"],
        "observable_required": "held-out predictive and calibration comparison against simpler baselines",
        "failure_condition": "No reproducible incremental value after complexity penalties",
        "claim_demotion_action": "Prefer the simpler metric family",
        "next_experiment_or_simulation": "Benchmark topology families under identical folds and nulls",
        "priority": "high",
    },
    {
        "id": "F6",
        "claim_affected": "Mental-flexibility features predict recovery latency or wellbeing longitudinally",
        "affected_subsystems": ["ToL bridge", "mental flexibility", "allostatic recovery"],
        "observable_required": "longitudinal outcomes with preregistered covariates",
        "failure_condition": "No out-of-sample association or unstable direction across cohorts",
        "claim_demotion_action": "Keep the bridge conceptual and remove predictive wording",
        "next_experiment_or_simulation": "Collect longitudinal, non-diagnostic validation data",
        "priority": "high",
    },
    {
        "id": "F7",
        "claim_affected": "A proposed TOE cosmological field term is compatible with observation",
        "affected_subsystems": ["cosmology constraints", "TOE field candidates"],
        "observable_required": "joint DESI, Euclid, CMB, BAO, and SNe constraints",
        "failure_condition": "Joint constraints exclude the proposed deviation from the standard model",
        "claim_demotion_action": "Reject or sharply bound the candidate field term",
        "next_experiment_or_simulation": "Fit the explicit model against current joint likelihoods",
        "priority": "critical",
    },
    {
        "id": "F8",
        "claim_affected": "TOE candidates predict measurable Kerr ringdown deviations",
        "affected_subsystems": ["gravitational-wave constraints", "GR reduction limit"],
        "observable_required": "black-hole spectroscopy and ringdown residuals",
        "failure_condition": "Improved observations remain consistent with Kerr and general relativity",
        "claim_demotion_action": "Constrain deviations and preserve the GR reduction limit",
        "next_experiment_or_simulation": "Propagate candidate parameters into ringdown posteriors",
        "priority": "critical",
    },
    {
        "id": "F9",
        "claim_affected": "Bioelectric regulation evidence supports subjective-experience claims",
        "affected_subsystems": ["bioelectric bridge", "basal cognition"],
        "observable_required": "independent evidence separating regulation from subjective report",
        "failure_condition": "Evidence supports adaptive regulation but not subjective experience",
        "claim_demotion_action": "Limit claims to regulation and basal cognition",
        "next_experiment_or_simulation": "Design substrate-comparative tests without consciousness shortcuts",
        "priority": "high",
    },
    {
        "id": "F10",
        "claim_affected": "Microtubule or biophotonic mechanisms contribute independently validated effects",
        "affected_subsystems": ["mechanism candidates", "consciousness adversarial matrix"],
        "observable_required": "independent replication with mechanism-specific perturbations",
        "failure_condition": "Effects do not replicate or are explained by conventional mechanisms",
        "claim_demotion_action": "Remove the mechanism from the active explanatory set",
        "next_experiment_or_simulation": "Prioritize blinded independent mechanism tests",
        "priority": "high",
    },
]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", required=True)
    args = parser.parse_args(argv)
    Path(args.out).write_text(json.dumps(FALSIFIERS, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
