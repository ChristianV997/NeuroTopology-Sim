{
  "ablations": [
    {
      "ablation_id": "level_m_only",
      "claim_implication": "empirical_claims_blocked_until_resolved",
      "expected_output": "level_m_only_ablation.json",
      "failure_condition": "ablation_not_explainable_or_inversion",
      "input_artifacts_required": [
        "stage_results.json"
      ],
      "name": "level m only",
      "purpose": "Test robustness and claim sensitivity.",
      "safe_status": "planned_only",
      "tests_claim": "feature_component_necessity"
    },
    {
      "ablation_id": "level_t_only",
      "claim_implication": "empirical_claims_blocked_until_resolved",
      "expected_output": "level_t_only_ablation.json",
      "failure_condition": "ablation_not_explainable_or_inversion",
      "input_artifacts_required": [
        "stage_results.json"
      ],
      "name": "level t only",
      "purpose": "Test robustness and claim sensitivity.",
      "safe_status": "planned_only",
      "tests_claim": "feature_component_necessity"
    },
    {
      "ablation_id": "m_plus_t",
      "claim_implication": "empirical_claims_blocked_until_resolved",
      "expected_output": "m_plus_t_ablation.json",
      "failure_condition": "ablation_not_explainable_or_inversion",
      "input_artifacts_required": [
        "stage_results.json"
      ],
      "name": "m plus t",
      "purpose": "Test robustness and claim sensitivity.",
      "safe_status": "planned_only",
      "tests_claim": "feature_component_necessity"
    },
    {
      "ablation_id": "no_topology_features",
      "claim_implication": "empirical_claims_blocked_until_resolved",
      "expected_output": "no_topology_features_ablation.json",
      "failure_condition": "ablation_not_explainable_or_inversion",
      "input_artifacts_required": [
        "stage_results.json"
      ],
      "name": "no topology features",
      "purpose": "Test robustness and claim sensitivity.",
      "safe_status": "planned_only",
      "tests_claim": "feature_component_necessity"
    },
    {
      "ablation_id": "no_spectral_features",
      "claim_implication": "empirical_claims_blocked_until_resolved",
      "expected_output": "no_spectral_features_ablation.json",
      "failure_condition": "ablation_not_explainable_or_inversion",
      "input_artifacts_required": [
        "stage_results.json"
      ],
      "name": "no spectral features",
      "purpose": "Test robustness and claim sensitivity.",
      "safe_status": "planned_only",
      "tests_claim": "feature_component_necessity"
    },
    {
      "ablation_id": "no_complexity_features",
      "claim_implication": "empirical_claims_blocked_until_resolved",
      "expected_output": "no_complexity_features_ablation.json",
      "failure_condition": "ablation_not_explainable_or_inversion",
      "input_artifacts_required": [
        "stage_results.json"
      ],
      "name": "no complexity features",
      "purpose": "Test robustness and claim sensitivity.",
      "safe_status": "planned_only",
      "tests_claim": "feature_component_necessity"
    },
    {
      "ablation_id": "no_subject_covariates",
      "claim_implication": "empirical_claims_blocked_until_resolved",
      "expected_output": "no_subject_covariates_ablation.json",
      "failure_condition": "ablation_not_explainable_or_inversion",
      "input_artifacts_required": [
        "stage_results.json"
      ],
      "name": "no subject covariates",
      "purpose": "Test robustness and claim sensitivity.",
      "safe_status": "planned_only",
      "tests_claim": "feature_component_necessity"
    },
    {
      "ablation_id": "no_session_covariates",
      "claim_implication": "empirical_claims_blocked_until_resolved",
      "expected_output": "no_session_covariates_ablation.json",
      "failure_condition": "ablation_not_explainable_or_inversion",
      "input_artifacts_required": [
        "stage_results.json"
      ],
      "name": "no session covariates",
      "purpose": "Test robustness and claim sensitivity.",
      "safe_status": "planned_only",
      "tests_claim": "feature_component_necessity"
    },
    {
      "ablation_id": "topology_only_after_power_control",
      "claim_implication": "empirical_claims_blocked_until_resolved",
      "expected_output": "topology_only_after_power_control_ablation.json",
      "failure_condition": "ablation_not_explainable_or_inversion",
      "input_artifacts_required": [
        "stage_results.json"
      ],
      "name": "topology only after power control",
      "purpose": "Test robustness and claim sensitivity.",
      "safe_status": "planned_only",
      "tests_claim": "feature_component_necessity"
    },
    {
      "ablation_id": "reduced_feature_set",
      "claim_implication": "empirical_claims_blocked_until_resolved",
      "expected_output": "reduced_feature_set_ablation.json",
      "failure_condition": "ablation_not_explainable_or_inversion",
      "input_artifacts_required": [
        "stage_results.json"
      ],
      "name": "reduced feature set",
      "purpose": "Test robustness and claim sensitivity.",
      "safe_status": "planned_only",
      "tests_claim": "feature_component_necessity"
    }
  ],
  "dataset_id": "DS005620"
}