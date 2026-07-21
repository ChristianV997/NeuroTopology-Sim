{
  "controls": [
    {
      "can_run_without_real_data": false,
      "claim_implication": "empirical_claims_blocked_until_resolved",
      "control_id": "channel_shuffle_null",
      "expected_output": "channel_shuffle_null_results.json",
      "failure_condition": "control_outperforms_primary_or_unstable",
      "input_artifacts_required": [
        "stage_results.json",
        "stage_outputs/p11_signal_mt/"
      ],
      "manual_or_auto": "manual",
      "name": "channel shuffle null",
      "purpose": "Stress-test non-causal and leakage-sensitive signal paths.",
      "safe_status": "planned_only"
    },
    {
      "can_run_without_real_data": false,
      "claim_implication": "empirical_claims_blocked_until_resolved",
      "control_id": "time_reversal_null",
      "expected_output": "time_reversal_null_results.json",
      "failure_condition": "control_outperforms_primary_or_unstable",
      "input_artifacts_required": [
        "stage_results.json",
        "stage_outputs/p11_signal_mt/"
      ],
      "manual_or_auto": "manual",
      "name": "time reversal null",
      "purpose": "Stress-test non-causal and leakage-sensitive signal paths.",
      "safe_status": "planned_only"
    },
    {
      "can_run_without_real_data": false,
      "claim_implication": "empirical_claims_blocked_until_resolved",
      "control_id": "phase_randomization_null",
      "expected_output": "phase_randomization_null_results.json",
      "failure_condition": "control_outperforms_primary_or_unstable",
      "input_artifacts_required": [
        "stage_results.json",
        "stage_outputs/p11_signal_mt/"
      ],
      "manual_or_auto": "manual",
      "name": "phase randomization null",
      "purpose": "Stress-test non-causal and leakage-sensitive signal paths.",
      "safe_status": "planned_only"
    },
    {
      "can_run_without_real_data": false,
      "claim_implication": "empirical_claims_blocked_until_resolved",
      "control_id": "label_permutation_null",
      "expected_output": "label_permutation_null_results.json",
      "failure_condition": "control_outperforms_primary_or_unstable",
      "input_artifacts_required": [
        "stage_results.json",
        "stage_outputs/p11_signal_mt/"
      ],
      "manual_or_auto": "manual",
      "name": "label permutation null",
      "purpose": "Stress-test non-causal and leakage-sensitive signal paths.",
      "safe_status": "planned_only"
    },
    {
      "can_run_without_real_data": false,
      "claim_implication": "empirical_claims_blocked_until_resolved",
      "control_id": "subject_blocked_permutation_null",
      "expected_output": "subject_blocked_permutation_null_results.json",
      "failure_condition": "control_outperforms_primary_or_unstable",
      "input_artifacts_required": [
        "stage_results.json",
        "stage_outputs/p11_signal_mt/"
      ],
      "manual_or_auto": "manual",
      "name": "subject blocked permutation null",
      "purpose": "Stress-test non-causal and leakage-sensitive signal paths.",
      "safe_status": "planned_only"
    },
    {
      "can_run_without_real_data": false,
      "claim_implication": "empirical_claims_blocked_until_resolved",
      "control_id": "frequency_band_control",
      "expected_output": "frequency_band_control_results.json",
      "failure_condition": "control_outperforms_primary_or_unstable",
      "input_artifacts_required": [
        "stage_results.json",
        "stage_outputs/p11_signal_mt/"
      ],
      "manual_or_auto": "manual",
      "name": "frequency band control",
      "purpose": "Stress-test non-causal and leakage-sensitive signal paths.",
      "safe_status": "planned_only"
    },
    {
      "can_run_without_real_data": false,
      "claim_implication": "empirical_claims_blocked_until_resolved",
      "control_id": "random_feature_control",
      "expected_output": "random_feature_control_results.json",
      "failure_condition": "control_outperforms_primary_or_unstable",
      "input_artifacts_required": [
        "stage_results.json",
        "stage_outputs/p11_signal_mt/"
      ],
      "manual_or_auto": "manual",
      "name": "random feature control",
      "purpose": "Stress-test non-causal and leakage-sensitive signal paths.",
      "safe_status": "planned_only"
    },
    {
      "can_run_without_real_data": false,
      "claim_implication": "empirical_claims_blocked_until_resolved",
      "control_id": "spatial_layout_control",
      "expected_output": "spatial_layout_control_results.json",
      "failure_condition": "control_outperforms_primary_or_unstable",
      "input_artifacts_required": [
        "stage_results.json",
        "stage_outputs/p11_signal_mt/"
      ],
      "manual_or_auto": "manual",
      "name": "spatial layout control",
      "purpose": "Stress-test non-causal and leakage-sensitive signal paths.",
      "safe_status": "planned_only"
    },
    {
      "can_run_without_real_data": false,
      "claim_implication": "empirical_claims_blocked_until_resolved",
      "control_id": "topology_interpolation_control",
      "expected_output": "topology_interpolation_control_results.json",
      "failure_condition": "control_outperforms_primary_or_unstable",
      "input_artifacts_required": [
        "stage_results.json",
        "stage_outputs/p11_signal_mt/"
      ],
      "manual_or_auto": "manual",
      "name": "topology interpolation control",
      "purpose": "Stress-test non-causal and leakage-sensitive signal paths.",
      "safe_status": "planned_only"
    },
    {
      "can_run_without_real_data": false,
      "claim_implication": "empirical_claims_blocked_until_resolved",
      "control_id": "spectral_power_matched_null",
      "expected_output": "spectral_power_matched_null_results.json",
      "failure_condition": "control_outperforms_primary_or_unstable",
      "input_artifacts_required": [
        "stage_results.json",
        "stage_outputs/p11_signal_mt/"
      ],
      "manual_or_auto": "manual",
      "name": "spectral power matched null",
      "purpose": "Stress-test non-causal and leakage-sensitive signal paths.",
      "safe_status": "planned_only"
    }
  ],
  "dataset_id": "DS005620"
}