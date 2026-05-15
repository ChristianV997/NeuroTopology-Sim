"""
Science task registry (P18.2).
Tracks known pipeline tasks with metadata, run counts, and statuses.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional


@dataclass
class ScienceTaskRecord:
    task_id: str
    module: str
    command: list[str]
    description: str
    required_inputs: list[str]
    expected_outputs: list[str]
    run_count: int = 0
    last_status: Optional[str] = None
    last_run_ts: Optional[str] = None
    tags: list[str] = field(default_factory=list)


@dataclass
class ScienceTaskRegistry:
    tasks: list[ScienceTaskRecord]

    def get(self, task_id: str) -> Optional[ScienceTaskRecord]:
        for t in self.tasks:
            if t.task_id == task_id:
                return t
        return None

    def to_dict(self) -> dict:
        return {"tasks": [asdict(t) for t in self.tasks]}

    def mark_run(self, task_id: str, status: str, ts: Optional[str] = None) -> None:
        from datetime import datetime, timezone

        task = self.get(task_id)
        if task is None:
            return
        task.run_count += 1
        task.last_status = status
        task.last_run_ts = ts or datetime.now(timezone.utc).isoformat()


def build_default_science_task_registry() -> ScienceTaskRegistry:
    tasks = [
        ScienceTaskRecord(
            task_id="p17_1_materialize_reviewed_contract",
            module="sciencer_d.btc_icft.pipelines.materialize_ds005620_reviewed_contract",
            command=["python", "-m", "sciencer_d.btc_icft.pipelines.materialize_ds005620_reviewed_contract"],
            description="Materialize P17.1 reviewed external contract artifact from declaration",
            required_inputs=["declaration_yaml_or_json"],
            expected_outputs=["p12_external_contract.json", "p17_1_reviewed_contract.json"],
            tags=["p17", "contract"],
        ),
        ScienceTaskRecord(
            task_id="p18_0_plan_benchmark_readiness",
            module="sciencer_d.btc_icft.pipelines.plan_ds005620_real_benchmark",
            command=["python", "-m", "sciencer_d.btc_icft.pipelines.plan_ds005620_real_benchmark"],
            description="P18.0 benchmark readiness gate and dry-run planner",
            required_inputs=["p12_external_contract.json", "metadata", "signal_blocks"],
            expected_outputs=[
                "ds005620_benchmark_readiness.json",
                "benchmark_input_statuses.json",
                "dry_run_command_plan.json",
                "execution_blockers.json",
                "omega_event.json",
                "report.md",
            ],
            tags=["p18", "readiness"],
        ),
        ScienceTaskRecord(
            task_id="p18_1_run_benchmark_dry_run",
            module="sciencer_d.btc_icft.pipelines.run_ds005620_real_benchmark",
            command=["python", "-m", "sciencer_d.btc_icft.pipelines.run_ds005620_real_benchmark"],
            description="P18.1 guarded benchmark executor (dry-run mode)",
            required_inputs=["p12_external_contract.json"],
            expected_outputs=[
                "ds005620_real_benchmark_execution.json",
                "stage_execution_plan.json",
                "stage_results.json",
                "execution_blockers.json",
                "omega_event.json",
                "report.md",
            ],
            tags=["p18", "executor", "dry_run"],
        ),
        ScienceTaskRecord(
            task_id="p18_1_run_benchmark_mock_e2e",
            module="sciencer_d.btc_icft.pipelines.run_ds005620_real_benchmark",
            command=[
                "python", "-m", "sciencer_d.btc_icft.pipelines.run_ds005620_real_benchmark",
                "--mock-e2e", "--execute", "--peer-reviewed-contract-confirmed",
            ],
            description="P18.1 mock end-to-end benchmark using in-tree fixtures",
            required_inputs=[],
            expected_outputs=[
                "ds005620_real_benchmark_execution.json",
                "stage_execution_plan.json",
                "stage_results.json",
                "execution_blockers.json",
                "omega_event.json",
                "report.md",
            ],
            tags=["p18", "executor", "mock_e2e"],
        ),
        ScienceTaskRecord(
            task_id="p19_1_extract_mne_signal_blocks",
            module="sciencer_d.btc_icft.pipelines.extract_mne_signal_blocks",
            command=["python", "-m", "sciencer_d.btc_icft.pipelines.extract_mne_signal_blocks"],
            description="P19.1 MNE signal block extraction from local EEG files",
            required_inputs=["local_eeg_files"],
            expected_outputs=["signal_block_inventory.json", "window_inventory.csv", "window_signal_values.json"],
            tags=["p19", "mne", "extraction"],
        ),
        ScienceTaskRecord(
            task_id="p19_2_canonical_signal_block_conversion",
            module="sciencer_d.btc_icft.pipelines.convert_mne_signal_blocks",
            command=["python", "-m", "sciencer_d.btc_icft.pipelines.convert_mne_signal_blocks"],
            description="P19.2 canonical signal-block conversion with strict join keys",
            required_inputs=["signal_block_inventory.json"],
            expected_outputs=[
                "signal_block_inventory.json",
                "window_inventory.csv",
                "window_signal_values.json",
                "reader_alignment_report.json",
            ],
            tags=["p19", "canonical", "signal_blocks"],
        ),
        ScienceTaskRecord(
            task_id="p9_level_m_features",
            module="sciencer_d.btc_icft.pipelines.extract_eeg_level_m_features",
            command=["python", "-m", "sciencer_d.btc_icft.pipelines.extract_eeg_level_m_features"],
            description="P9 Level M signal feature extraction",
            required_inputs=["canonical_signal_blocks"],
            expected_outputs=["features_m_signal.csv"],
            tags=["p9", "level_m", "features"],
        ),
        ScienceTaskRecord(
            task_id="p10_level_t_topology",
            module="sciencer_d.btc_icft.pipelines.extract_eeg_level_t_topology",
            command=["python", "-m", "sciencer_d.btc_icft.pipelines.extract_eeg_level_t_topology"],
            description="P10 Level T signal topology extraction",
            required_inputs=["canonical_signal_blocks"],
            expected_outputs=["features_t_signal.csv"],
            tags=["p10", "level_t", "topology"],
        ),
        ScienceTaskRecord(
            task_id="p12_align_eeg_labels",
            module="sciencer_d.btc_icft.pipelines.align_eeg_labels",
            command=["python", "-m", "sciencer_d.btc_icft.pipelines.align_eeg_labels", "--external-contract"],
            description="P12 label alignment with reviewed external contract",
            required_inputs=["p12_external_contract.json", "metadata", "features_m_signal.csv"],
            expected_outputs=["label_alignment.csv"],
            tags=["p12", "alignment"],
        ),
        ScienceTaskRecord(
            task_id="p13_inject_eeg_targets",
            module="sciencer_d.btc_icft.pipelines.inject_eeg_targets",
            command=["python", "-m", "sciencer_d.btc_icft.pipelines.inject_eeg_targets"],
            description="P13 target injection from P12 alignment output",
            required_inputs=["features_m_signal.csv", "label_alignment.csv"],
            expected_outputs=["features_m_signal_labeled.csv"],
            tags=["p13", "targets"],
        ),
        ScienceTaskRecord(
            task_id="p11_run_eeg_signal_mt",
            module="sciencer_d.btc_icft.pipelines.run_eeg_signal_mt",
            command=["python", "-m", "sciencer_d.btc_icft.pipelines.run_eeg_signal_mt"],
            description="P11 target-aware M+T benchmark",
            required_inputs=["features_m_signal_labeled.csv", "features_t_signal.csv"],
            expected_outputs=["metrics_signal_mt.json"],
            tags=["p11", "benchmark"],
        ),
        ScienceTaskRecord(
            task_id="build_artifact_manifest",
            module="tools.build_ds005620_artifact_manifest",
            command=["python", "tools/build_ds005620_artifact_manifest.py"],
            description="Build DS005620 artifact manifest from execution outputs",
            required_inputs=["ds005620_real_benchmark_execution.json"],
            expected_outputs=["artifact_manifest.json"],
            tags=["tools", "manifest"],
        ),
        ScienceTaskRecord(
            task_id="export_evidence_packet",
            module="tools.export_ds005620_evidence_packet",
            command=["python", "tools/export_ds005620_evidence_packet.py"],
            description="Export DS005620 evidence packet for review",
            required_inputs=["artifact_manifest.json"],
            expected_outputs=["evidence_packet.json", "evidence_packet.md", "notion_import_payload.json"],
            tags=["tools", "evidence"],
        ),
        ScienceTaskRecord(
            task_id="generate_paper_skeleton",
            module="tools.generate_ds005620_paper_skeleton",
            command=["python", "tools/generate_ds005620_paper_skeleton.py"],
            description="Generate DS005620 paper skeleton with reviewer checklist",
            required_inputs=["evidence_packet.json"],
            expected_outputs=["paper_skeleton.md", "reviewer_checklist.md", "negative_space_disclaimers.md"],
            tags=["tools", "paper"],
        ),
        ScienceTaskRecord(
            task_id="preflight_real_local",
            module="sciencer_d.btc_icft.pipelines.preflight_ds005620_real_local",
            command=["python", "-m", "sciencer_d.btc_icft.pipelines.preflight_ds005620_real_local"],
            description="Real/local preflight check before live P18.1 execution",
            required_inputs=["metadata", "p12_external_contract.json", "signal_blocks", "level_m", "level_t"],
            expected_outputs=["preflight_report.json", "preflight_report.md"],
            tags=["preflight", "real_local"],
        ),
        ScienceTaskRecord(
            task_id="validate_e2e_execution",
            module="tools.validate_ds005620_e2e_execution",
            command=["python", "tools/validate_ds005620_e2e_execution.py"],
            description="Validate P18.1 E2E execution artifacts",
            required_inputs=["ds005620_real_benchmark_execution.json"],
            expected_outputs=["(stdout: PASS)"],
            tags=["tools", "validation"],
        ),
        ScienceTaskRecord(
            task_id="inspect_science_runtime",
            module="sciencer_d.btc_icft.pipelines.inspect_science_runtime",
            command=["python", "-m", "sciencer_d.btc_icft.pipelines.inspect_science_runtime"],
            description="Inspect science runtime state, task inventory, and next actions",
            required_inputs=["artifact_root"],
            expected_outputs=[
                "runtime_state.json",
                "task_inventory.json",
                "runtime_snapshot.json",
                "runtime_event_log.jsonl",
                "runtime_report.md",
            ],
            tags=["runtime", "inspect"],
        ),
        ScienceTaskRecord(
            task_id="ds005620_real_execution_gate",
            module="sciencer_d.btc_icft.pipelines.prepare_ds005620_real_local_execution",
            command=[
                "python", "-m",
                "sciencer_d.btc_icft.pipelines.prepare_ds005620_real_local_execution",
                "--out", "outputs/btc_icft/ds005620_real_execution_gate",
            ],
            description=(
                "P18.3 real/local execution gate: inspects prerequisites and prepares "
                "human-reviewed execution commands without running real data."
            ),
            required_inputs=[
                "data/DS005620/events.tsv",
                "outputs/btc_icft/ds005620_reviewed_contract/p12_external_contract.json",
            ],
            expected_outputs=[
                "ready_for_real_execution.json",
                "real_execution_gate.json",
                "real_execution_command_plan.json",
                "human_peer_review_checklist.json",
                "human_peer_review_checklist.md",
                "missing_artifacts.json",
                "report.md",
            ],
            tags=["p18", "gate", "real_local", "preflight"],
        ),
    ]
    return ScienceTaskRegistry(tasks=tasks)
