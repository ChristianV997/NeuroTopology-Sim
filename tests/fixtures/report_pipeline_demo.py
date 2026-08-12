"""Small, deterministic demo fixtures for `workflows.report_pipeline`.

Mirrors `tests/fixtures/make_synthetic_bids.py`'s convention: these are
generator FUNCTIONS a test calls to write tiny fixture files into a
caller-supplied directory (usually `tmp_path`), not pre-baked static
files -- so nothing here can drift stale against a schema change, and
nothing here is a tracked output artifact (see tests/fixtures/README.md).

Covers the demo pack the report-pipeline-runner mission (Phase F) asks
for: an MNE/BIDS epoch-table recipe spec + epoch table, an MNE/BIDS
derived feature table + mapping, an fMRI timeseries-recipe spec + input,
an fMRI derived feature table + mapping, and an existing EvidenceBundle
(built for real from this repository's own already-committed
`contracts/btc_icft/ds005620/pitnn_cohort/` artifacts -- not downloaded,
not fabricated).
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import numpy as np

_REPO_ROOT = Path(__file__).resolve().parents[2]
SEED_REGISTRY = _REPO_ROOT / "benchmarks" / "registry_seed.json"
DS005620_SOURCE = _REPO_ROOT / "contracts" / "btc_icft" / "ds005620" / "pitnn_cohort"


def _coupled_timeseries(n_parcels: int = 6, n_timepoints: int = 50, coupling: float = 0.0, seed: int = 0) -> list:
    rng = np.random.RandomState(seed)
    base = rng.randn(n_parcels, n_timepoints)
    if coupling:
        shared = rng.randn(1, n_timepoints)
        base = base * (1 - coupling) + shared * coupling
    return base.tolist()


def write_mne_bids_epoch_table_recipe_demo(tmp_path: Path) -> tuple[Path, Path]:
    """Returns `(recipe_spec_path, epoch_table_path)` for
    `input_mode="mne_bids_epoch_table_recipe"`."""
    from adapters.mne_bids_feature_recipe_schema import FeatureRecipeSpecV1

    rng = np.random.RandomState(0)
    epoch_table = {
        "sfreq": 100.0,
        "subjects": {
            "sub-01": {
                "epochs": {
                    "rest_marker": [rng.randn(4, 200).tolist() for _ in range(3)],
                    "task_marker": [rng.randn(4, 200).tolist() for _ in range(3)],
                }
            }
        },
    }
    epoch_table_path = tmp_path / "demo_epoch_table.json"
    epoch_table_path.write_text(json.dumps(epoch_table), encoding="utf-8")

    spec = FeatureRecipeSpecV1.make(
        dataset_id="demo_eeg_ds", feature_set_id="mne_bids_spectral_v1",
        source_state="rest", target_state="task",
        requested_features=["qc.valid_epoch_count"],
        max_subjects=5, max_runs=5, max_epochs_per_state=10, max_total_epochs=100,
        event_state_mapping={"rest_marker": "rest", "task_marker": "task"},
        feature_definitions={"qc.valid_epoch_count": "Count of valid epochs used per state."},
        limitations=["report pipeline demo fixture"], provenance="report pipeline demo fixture",
    )
    spec_path = tmp_path / "demo_eeg_recipe_spec.json"
    spec.write_json(spec_path)
    return spec_path, epoch_table_path


def write_mne_bids_derived_features_demo(tmp_path: Path) -> tuple[Path, Path]:
    """Returns `(features_path, mapping_path)` for
    `input_mode="mne_bids_derived_features"`."""
    features_path = tmp_path / "demo_mne_bids_features.csv"
    features_path.write_text(
        "dataset_id,subject_id,session_id,source_state,target_state,feature_name,"
        "source_value,target_value,feature_definition,artifact_path\n"
        "demo_eeg_derived_ds,sub-01,,rest,task,spectral.alpha_power,0.3,0.5,"
        "Mean relative alpha power.,\n",
        encoding="utf-8",
    )
    mapping_path = tmp_path / "demo_mne_bids_mapping.json"
    mapping_path.write_text(json.dumps({
        "format": "long", "dataset_id": "demo_eeg_derived_ds", "modality": "EEG",
        "feature_definitions": {"spectral.alpha_power": "Mean relative alpha power."},
        "preprocessing_provenance": {"note": "report pipeline demo fixture"},
        "null_control_status": "not_provided",
    }), encoding="utf-8")
    return features_path, mapping_path


def write_fmri_timeseries_recipe_demo(tmp_path: Path) -> tuple[Path, Path]:
    """Returns `(recipe_spec_path, timeseries_table_path)` for
    `input_mode="fmri_timeseries_recipe"`."""
    from adapters.fmri_derivatives_feature_recipe_schema import FmriFeatureRecipeSpecV1

    # Two subjects (not one) -- phase_space cross-subject normalization
    # needs more than a single data point to avoid an "insufficient_data_only
    # status but non-empty coordinates" edge case in evidence.builder's own
    # bundle-metadata validation when combined with include_phase_space.
    table = {
        "dataset_id": "demo_fmri_ds", "atlas_or_parcellation": "Schaefer100",
        "subjects": {
            "sub-01": {
                "session": None,
                "timeseries": {
                    "placebo_label": _coupled_timeseries(coupling=0.0, seed=1),
                    "drug_label": _coupled_timeseries(coupling=0.85, seed=2),
                },
            },
            "sub-02": {
                "session": None,
                "timeseries": {
                    "placebo_label": _coupled_timeseries(coupling=0.0, seed=3),
                    "drug_label": _coupled_timeseries(coupling=0.85, seed=4),
                },
            },
        },
    }
    table_path = tmp_path / "demo_fmri_timeseries.json"
    table_path.write_text(json.dumps(table), encoding="utf-8")

    spec = FmriFeatureRecipeSpecV1.make(
        dataset_id="demo_fmri_ds", feature_set_id="fmri_connectivity_graph_v1",
        source_state="placebo", target_state="drug", atlas_or_parcellation="Schaefer100",
        requested_features=["connectivity.mean_connectivity"],
        max_subjects=5, max_runs=5, max_timepoints_per_state=100, max_total_timepoints=10000,
        state_mapping={"placebo_label": "placebo", "drug_label": "drug"},
        feature_definitions={"connectivity.mean_connectivity": "Mean off-diagonal Pearson correlation."},
        confound_policy={"description": "No confounds regression applied to this synthetic demo fixture."},
        input_kind="timeseries_table",
        limitations=["report pipeline demo fixture"], provenance="report pipeline demo fixture",
    )
    spec_path = tmp_path / "demo_fmri_recipe_spec.json"
    spec.write_json(spec_path)
    return spec_path, table_path


def write_fmri_graph_summary_recipe_demo(tmp_path: Path) -> tuple[Path, Path]:
    """Returns `(recipe_spec_path, graph_summary_path)` for
    `input_mode="fmri_graph_summary_recipe"`."""
    from adapters.fmri_derivatives_feature_recipe_schema import FmriFeatureRecipeSpecV1

    graph_summary = {
        "format": "graph_summary", "dataset_id": "demo_fmri_gs_ds", "modality": "fMRI",
        "atlas_or_parcellation": "Schaefer100", "source_state": "placebo", "target_state": "drug",
        "preprocessing_provenance": {"note": "already-computed graph metrics (demo fixture)"},
        "confound_policy": "24-param + aCompCor",
        "feature_definitions": {"connectivity.global_efficiency": "Global efficiency of the connectivity graph."},
        "subjects": [
            {"subject_id": "sub-01", "metrics": {"connectivity.global_efficiency": {"source_value": 0.31, "target_value": 0.42}}},
        ],
    }
    gs_path = tmp_path / "demo_graph_summary.json"
    gs_path.write_text(json.dumps(graph_summary), encoding="utf-8")

    spec = FmriFeatureRecipeSpecV1.make(
        dataset_id="demo_fmri_gs_ds", feature_set_id="fmri_connectivity_graph_v1",
        source_state="placebo", target_state="drug", atlas_or_parcellation="Schaefer100",
        requested_features=["connectivity.global_efficiency"],
        max_subjects=5, max_runs=5, max_timepoints_per_state=100, max_total_timepoints=10000,
        state_mapping={"placebo_label": "placebo", "drug_label": "drug"},
        feature_definitions={"connectivity.global_efficiency": "Global efficiency of the connectivity graph."},
        confound_policy={"description": "No confounds regression applied to this synthetic demo fixture."},
        input_kind="graph_summary",
        limitations=["report pipeline demo fixture"], provenance="report pipeline demo fixture",
    )
    spec_path = tmp_path / "demo_fmri_gs_recipe_spec.json"
    spec.write_json(spec_path)
    return spec_path, gs_path


def write_fmri_derived_features_demo(tmp_path: Path) -> tuple[Path, Path]:
    """Returns `(features_path, mapping_path)` for
    `input_mode="fmri_derived_features"`."""
    features_path = tmp_path / "demo_fmri_features.csv"
    features_path.write_text(
        "dataset_id,subject_id,session_id,source_state,target_state,atlas_or_parcellation,"
        "feature_name,source_value,target_value,feature_definition,artifact_path\n"
        "demo_fmri_derived_ds,sub-01,,placebo,drug,Schaefer100,connectivity.mean_connectivity,"
        "0.12,0.34,Mean off-diagonal Pearson correlation.,\n",
        encoding="utf-8",
    )
    mapping_path = tmp_path / "demo_fmri_mapping.json"
    mapping_path.write_text(json.dumps({
        "format": "long", "dataset_id": "demo_fmri_derived_ds", "modality": "fMRI",
        "atlas_or_parcellation": "Schaefer100",
        "feature_definitions": {"connectivity.mean_connectivity": "Mean off-diagonal Pearson correlation."},
        "confound_policy": "24-param + aCompCor",
        "preprocessing_provenance": {"note": "report pipeline demo fixture"},
        "null_control_status": "not_provided",
    }), encoding="utf-8")
    return features_path, mapping_path


def build_existing_evidence_bundle_demo(out_dir: Path, *, registry_path: Optional[Path] = None) -> Path:
    """Builds a real (not fabricated) `EvidenceBundleV1` from this
    repository's own already-committed `contracts/btc_icft/ds005620/
    pitnn_cohort/` artifacts, via `evidence.builder.build_evidence_bundle`
    -- no raw data download, no synthetic transition records. Returns the
    path to the written `EvidenceBundle.json`, for use as
    `evidence_bundle_path` under `input_mode="existing_evidence_bundle"`."""
    from evidence.builder import build_evidence_bundle

    bundle = build_evidence_bundle(
        dataset="ds005620", feature_set="cohort_summary", source=DS005620_SOURCE, out=out_dir,
        registry_path=registry_path or SEED_REGISTRY,
    )
    return out_dir / "EvidenceBundle.json"
