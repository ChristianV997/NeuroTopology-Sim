from __future__ import annotations

def build_post_run_expected_artifacts() -> dict:
    return {
        "expected_outputs_after_real_execution": [
            "outputs/btc_icft/ds005620_real_benchmark_execution/ds005620_real_benchmark_execution.json",
            "outputs/btc_icft/ds005620_real_benchmark_execution/stage_results.json",
            "outputs/btc_icft/ds005620_real_benchmark_execution/omega_event.json",
        ],
        "expected_controls_after_real_execution": [
            "outputs/btc_icft/ds005620_real_execution_gate/report.md",
            "outputs/btc_icft/ds005620_generated_language_validation.json",
            "outputs/btc_icft/ontology_language_validation.json",
        ],
        "expected_publication_artifacts_after_controls": [
            "outputs/btc_icft/ds005620_real_benchmark_execution_mock/evidence_packet.json",
            "outputs/btc_icft/ds005620_real_benchmark_execution_mock/paper_skeleton.md",
        ],
    }
