"""
Multi-dataset path config (P22).

Generic per-dataset path config that generalizes the DS005620 pattern.
DS005620 retains its legacy output paths for backward compatibility with
P18.3, P20, and P21 outputs. Other datasets use the generic
`outputs/btc_icft/<dataset_id>/...` layout.

stdlib only.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


_DEFAULT_MANIFEST_PATH = "configs/btc_icft/multi_dataset_real_sources.json"


@dataclass
class DatasetProfile:
    dataset_id: str
    title: str
    source_hint: str
    source_url_hint: str
    expected_modality: str
    expected_formats: list
    canonical_local_roots: list
    metadata_candidates: list
    raw_eeg_extensions: list
    label_contract_required: bool
    human_review_required: bool
    real_execution_supported: bool
    dataset_specific_executor_available: bool
    generic_artifact_operator_supported: bool
    generic_execution_gate_supported: bool
    autonomous_iteration_supported: bool
    notes: str
    guardrails: list


@dataclass
class DatasetRealPathConfig:
    """Where to find / where to write per-stage artifacts for a dataset."""
    dataset_id: str
    local_root: str
    metadata_path: str
    raw_eeg_root: str
    reviewed_contract_source: str
    reviewed_contract_materialized: str
    reader_preflight_path: str
    mne_extract_path: str
    signal_blocks_path: str
    level_m_csv_path: str
    level_t_csv_path: str
    real_execution_gate_path: str


@dataclass
class DatasetArtifactPathConfig:
    """Wrapper that bundles real-path config with operator/iteration roots."""
    dataset_id: str
    real_paths: DatasetRealPathConfig
    artifact_operator_root: str
    autonomous_iteration_root: str


@dataclass
class DatasetOutputRoots:
    dataset_id: str
    real_execution_gate_root: str
    artifact_operator_root: str
    autonomous_iteration_root: str
    matrix_root: str


def normalize_dataset_id_for_path(dataset_id: str) -> str:
    """Return the canonical path-safe dataset id used in output directories.

    DS005620 keeps its uppercase ID (matches existing layout under outputs/btc_icft/).
    Other dataset IDs are kept as-is (e.g. ds001787, PhysioNet_GABA).
    """
    if not dataset_id:
        raise ValueError("dataset_id must be non-empty")
    return dataset_id


def _resolve_default_manifest_path() -> Path:
    """Resolve the default manifest path from the cwd or fall back to repo root."""
    cwd_path = Path(_DEFAULT_MANIFEST_PATH)
    if cwd_path.exists():
        return cwd_path
    # Fall back to a path relative to this module: ../../../configs/btc_icft/...
    module_path = Path(__file__).resolve()
    repo_root = module_path.parent.parent.parent.parent
    fallback = repo_root / _DEFAULT_MANIFEST_PATH
    return fallback


def load_multi_dataset_source_manifest(
    path: Optional[str] = None,
) -> list:
    """Load profiles from the source manifest JSON. Returns list[DatasetProfile]."""
    if path is None:
        p = _resolve_default_manifest_path()
    else:
        p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Source manifest not found: {p}")
    data = json.loads(p.read_text(encoding="utf-8"))
    profiles = []
    for d in data.get("datasets", []):
        profiles.append(DatasetProfile(
            dataset_id=d["dataset_id"],
            title=d.get("title", ""),
            source_hint=d.get("source_hint", ""),
            source_url_hint=d.get("source_url_hint", ""),
            expected_modality=d.get("expected_modality", "EEG"),
            expected_formats=list(d.get("expected_formats", [])),
            canonical_local_roots=list(d.get("canonical_local_roots", [])),
            metadata_candidates=list(d.get("metadata_candidates", [])),
            raw_eeg_extensions=list(d.get("raw_eeg_extensions", [])),
            label_contract_required=bool(d.get("label_contract_required", True)),
            human_review_required=bool(d.get("human_review_required", True)),
            real_execution_supported=bool(d.get("real_execution_supported", False)),
            dataset_specific_executor_available=bool(
                d.get("dataset_specific_executor_available", False)
            ),
            generic_artifact_operator_supported=bool(
                d.get("generic_artifact_operator_supported", True)
            ),
            generic_execution_gate_supported=bool(
                d.get("generic_execution_gate_supported", True)
            ),
            autonomous_iteration_supported=bool(
                d.get("autonomous_iteration_supported", True)
            ),
            notes=d.get("notes", ""),
            guardrails=list(d.get("guardrails", [])),
        ))
    return profiles


def get_dataset_profile(
    dataset_id: str,
    *,
    manifest_path: Optional[str] = None,
) -> DatasetProfile:
    profiles = load_multi_dataset_source_manifest(manifest_path)
    for p in profiles:
        if p.dataset_id == dataset_id:
            return p
    raise ValueError(f"Unknown dataset_id: {dataset_id!r}")


def build_dataset_path_config(profile: DatasetProfile) -> DatasetRealPathConfig:
    """Construct DatasetRealPathConfig from profile, preserving legacy DS005620 layout."""
    ds = profile.dataset_id
    # DS005620 retains its legacy paths (matches existing P18.3/P20/P21 outputs).
    if ds == "DS005620":
        local_root = "data/DS005620"
        return DatasetRealPathConfig(
            dataset_id=ds,
            local_root=local_root,
            metadata_path="data/DS005620/events.tsv",
            raw_eeg_root="data/DS005620/raw",
            reviewed_contract_source="data/DS005620/ds005620_activation_declaration.json",
            reviewed_contract_materialized=(
                "outputs/btc_icft/ds005620_reviewed_contract/p12_external_contract.json"
            ),
            reader_preflight_path="outputs/btc_icft/eeg_reader_preflight/DS005620",
            mne_extract_path="outputs/btc_icft/eeg_mne_extract/DS005620",
            signal_blocks_path="outputs/btc_icft/eeg_signal_blocks_from_mne/DS005620",
            level_m_csv_path="outputs/btc_icft/eeg_level_m/DS005620/features_m_signal.csv",
            level_t_csv_path="outputs/btc_icft/eeg_level_t/DS005620/features_t_signal.csv",
            real_execution_gate_path=(
                "outputs/btc_icft/ds005620_real_execution_gate/ready_for_real_execution.json"
            ),
        )

    # Generic layout for all other datasets.
    # Use the first canonical_local_root that exists; fall back to data/<ds>.
    local_root = ""
    for candidate in profile.canonical_local_roots:
        if Path(candidate).exists():
            local_root = candidate
            break
    if not local_root:
        local_root = profile.canonical_local_roots[0] if profile.canonical_local_roots else f"data/{ds}"

    return DatasetRealPathConfig(
        dataset_id=ds,
        local_root=local_root,
        metadata_path=f"{local_root}/events.tsv",
        raw_eeg_root=f"{local_root}/raw",
        reviewed_contract_source=f"{local_root}/{ds}_activation_declaration.json",
        reviewed_contract_materialized=(
            f"outputs/btc_icft/{ds}/reviewed_contract/p12_external_contract.json"
        ),
        reader_preflight_path=f"outputs/btc_icft/{ds}/eeg_reader_preflight",
        mne_extract_path=f"outputs/btc_icft/{ds}/eeg_mne_extract",
        signal_blocks_path=f"outputs/btc_icft/{ds}/eeg_signal_blocks",
        level_m_csv_path=f"outputs/btc_icft/{ds}/eeg_level_m/features_m_signal.csv",
        level_t_csv_path=f"outputs/btc_icft/{ds}/eeg_level_t/features_t_signal.csv",
        real_execution_gate_path=(
            f"outputs/btc_icft/{ds}/real_execution_gate/ready_for_real_execution.json"
        ),
    )


def build_dataset_output_roots(dataset_id: str) -> DatasetOutputRoots:
    """Compute output roots for matrix / operator / iteration outputs."""
    if dataset_id == "DS005620":
        return DatasetOutputRoots(
            dataset_id=dataset_id,
            real_execution_gate_root="outputs/btc_icft/ds005620_real_execution_gate",
            artifact_operator_root="outputs/btc_icft/ds005620_real_artifact_operator",
            autonomous_iteration_root="outputs/btc_icft/ds005620_autonomous_iteration",
            matrix_root="outputs/btc_icft/multi_dataset_real_execution",
        )
    return DatasetOutputRoots(
        dataset_id=dataset_id,
        real_execution_gate_root=f"outputs/btc_icft/{dataset_id}/real_execution_gate",
        artifact_operator_root=f"outputs/btc_icft/{dataset_id}/real_artifact_operator",
        autonomous_iteration_root=f"outputs/btc_icft/{dataset_id}/autonomous_iteration",
        matrix_root="outputs/btc_icft/multi_dataset_real_execution",
    )


def build_dataset_artifact_path_config(
    profile: DatasetProfile,
) -> DatasetArtifactPathConfig:
    real = build_dataset_path_config(profile)
    roots = build_dataset_output_roots(profile.dataset_id)
    return DatasetArtifactPathConfig(
        dataset_id=profile.dataset_id,
        real_paths=real,
        artifact_operator_root=roots.artifact_operator_root,
        autonomous_iteration_root=roots.autonomous_iteration_root,
    )
