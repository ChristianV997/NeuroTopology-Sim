"""Bounded fMRIPrep/Nilearn local derived-feature extraction recipe.

Turns an already-local fMRIPrep/Nilearn-style derived fMRI artifact (a
small JSON fixture of per-subject parcel timeseries or a precomputed
connectivity matrix, or a self-contained `adapters.fmri_derivatives`
`format="graph_summary"` document) into the explicit
`derived_features.csv` + `mapping.json` pair `adapters.fmri_derivatives`
consumes. This module never runs raw BOLD preprocessing, never executes
fMRIPrep, never fits a Nilearn model, never downloads data, never infers
`source_state`/`target_state` from file names or column names (only an
explicit `state_mapping` ever does that), and never computes a null
control (`null_control_status` is always `"not_provided"`).

Three `input_kind` modes:

- **`timeseries_table`** (default): a small JSON fixture of
  already-extracted parcel-level timeseries --
  `{"dataset_id":.., "atlas_or_parcellation":.., "subjects": {"sub-01":
  {"session": null, "timeseries": {"<raw_label>": [[parcel x
  timepoints]...]}, "confounds": {"<raw_label>": {"mean_fd":..}}}}}`.
  Pearson correlation is computed over the (bounded, truncated) parcel
  timeseries via `numpy.corrcoef`.
- **`connectivity_matrix`**: identical shape but a `"matrices"` key
  holding already-computed parcel x parcel matrices directly -- this
  recipe never computes a correlation matrix in this mode.
- **`graph_summary`**: reuses `adapters.fmri_derivatives_features`'s own
  `load_graph_summary`/`expand_graph_summary` directly (the same format
  `adapters.fmri_derivatives` itself already validates/consumes) -- a pure
  pass-through of already-computed values, never a fresh computation.

Graph-metric computation (`connectivity.global_efficiency`,
`connectivity.modularity`, `connectivity.degree`,
`connectivity.small_worldness`) reuses NetworkX (already an installed,
BSD-3-Clause, `requirements.txt`-declared dependency) rather than
reimplementing graph algorithms -- see docs/fmri_derivatives_feature_recipe.md.
"""
from __future__ import annotations

import csv
import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Union

import numpy as np

from adapters.fmri_derivatives_feature_recipe_schema import FmriDerivedFeatureRecipeManifestV1, FmriFeatureRecipeSpecV1
from adapters.fmri_derivatives_feature_recipe_validation import (
    GRAPH_REQUIRING_FEATURES,
    SUPPORTED_TOPOLOGY_FEATURES,
)
from dataset_acquisition.store import validate_target_root

_REPO_ROOT = Path(__file__).resolve().parents[1]

_LONG_COLUMNS: tuple[str, ...] = (
    "dataset_id", "subject_id", "session_id", "source_state", "target_state",
    "atlas_or_parcellation", "feature_name", "source_value", "target_value",
    "feature_definition", "artifact_path",
)


class FmriFeatureRecipeError(ValueError):
    """Raised for recipe-execution-level problems (bad input data, bounds
    exceeded with nothing extractable, ...) distinct from spec validation."""


def _repo_commit() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=str(_REPO_ROOT), capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return "unknown"


def _is_under_repo(path: Path) -> bool:
    try:
        path.resolve().relative_to(_REPO_ROOT)
        return True
    except ValueError:
        return False


def _is_nan(value: Any) -> bool:
    return isinstance(value, float) and value != value


# ── graph / connectivity computation ──────────────────────────────────────


def compute_correlation_matrix(timeseries: np.ndarray) -> Optional[np.ndarray]:
    """`timeseries`: `(n_parcels, n_timepoints)`. Returns `None` -- never a
    fabricated 0/1 matrix -- when any parcel signal is constant or
    entirely NaN (Pearson correlation is undefined in that case)."""
    arr = np.asarray(timeseries, dtype=float)
    if arr.ndim != 2 or arr.shape[0] < 2 or arr.shape[1] < 2:
        return None
    stds = np.nanstd(arr, axis=1)
    if np.any(~np.isfinite(stds)) or np.any(stds == 0):
        return None
    matrix = np.corrcoef(arr)
    if not np.all(np.isfinite(matrix)):
        return None
    return matrix


def compute_mean_connectivity(matrix: Optional[np.ndarray]) -> float:
    """Mean of the strictly-upper-triangular (off-diagonal) entries only --
    the diagonal must never dominate this value."""
    if matrix is None:
        return float("nan")
    n = matrix.shape[0]
    if n < 2:
        return float("nan")
    values = matrix[np.triu_indices(n, k=1)]
    if values.size == 0:
        return float("nan")
    return float(np.mean(values))


def _build_graph(matrix: np.ndarray, graph_policy: dict[str, Any]):
    import networkx as nx

    mat = np.array(matrix, dtype=float, copy=True)
    np.fill_diagonal(mat, 0.0)
    n = mat.shape[0]
    threshold_method = graph_policy.get("threshold_method")
    threshold = graph_policy.get("threshold")
    weighted = bool(graph_policy.get("weighted", False))

    if threshold_method == "absolute_threshold":
        cutoff = float(threshold)
    elif threshold_method == "density_threshold":
        density = max(0.0, min(1.0, float(threshold)))
        off_diag = mat[np.triu_indices(n, k=1)]
        cutoff = float(np.quantile(off_diag, 1.0 - density)) if off_diag.size else float("inf")
    else:
        raise FmriFeatureRecipeError(f"unsupported graph_policy.threshold_method: {threshold_method!r}")

    graph = nx.Graph()
    graph.add_nodes_from(range(n))
    for i in range(n):
        for j in range(i + 1, n):
            w = mat[i, j]
            if np.isfinite(w) and w >= cutoff:
                if weighted:
                    graph.add_edge(i, j, weight=float(w))
                else:
                    graph.add_edge(i, j)
    return graph


def compute_graph_metrics(
    matrix: Optional[np.ndarray], *, requested_features: list[str], graph_policy: dict[str, Any]
) -> dict[str, Any]:
    """Returns `{feature_name: value, "_skip_reasons": {feature_name:
    reason}}`. Never raises out of a single metric's computation -- an
    unsafe/undefined metric is marked unsupported (NaN + a recorded
    reason) rather than invented."""
    import networkx as nx

    result: dict[str, Any] = {}
    skip_reasons: dict[str, str] = {}
    needed = [f for f in requested_features if f in GRAPH_REQUIRING_FEATURES]
    if not needed:
        return {"_skip_reasons": skip_reasons}

    if matrix is None:
        for feature_name in needed:
            result[feature_name] = float("nan")
            skip_reasons[feature_name] = "no valid connectivity matrix available -- graph metric skipped"
        result["_skip_reasons"] = skip_reasons
        return result

    graph = _build_graph(matrix, graph_policy)

    for feature_name in needed:
        try:
            if feature_name == "connectivity.global_efficiency":
                result[feature_name] = float(nx.global_efficiency(graph)) if graph.number_of_nodes() > 1 else float("nan")
            elif feature_name == "connectivity.modularity":
                if graph.number_of_edges() == 0:
                    result[feature_name] = float("nan")
                    skip_reasons[feature_name] = "graph has no edges -- modularity undefined"
                    continue
                communities = list(nx.algorithms.community.greedy_modularity_communities(graph))
                result[feature_name] = float(nx.algorithms.community.modularity(graph, communities))
            elif feature_name == "connectivity.degree":
                degrees = [d for _, d in graph.degree()]
                result[feature_name] = float(np.mean(degrees)) if degrees else float("nan")
            elif feature_name == "connectivity.small_worldness":
                if graph.number_of_nodes() < 5 or graph.number_of_edges() == 0 or not nx.is_connected(graph):
                    result[feature_name] = float("nan")
                    skip_reasons[feature_name] = (
                        "small_worldness requires >=5 nodes and a connected graph -- skipped rather than invented"
                    )
                    continue
                try:
                    sigma = nx.algorithms.smallworld.sigma(graph, niter=1, nrand=2, seed=0)
                    result[feature_name] = float(sigma)
                except Exception as exc:  # NetworkX raises on many degenerate graphs -- fail closed, never invent
                    result[feature_name] = float("nan")
                    skip_reasons[feature_name] = f"small_worldness computation failed safely: {exc}"
            else:
                result[feature_name] = float("nan")
        except Exception as exc:  # defense in depth -- a single metric must never abort the whole extraction
            result[feature_name] = float("nan")
            skip_reasons[feature_name] = f"{feature_name} computation failed safely: {exc}"

    result["_skip_reasons"] = skip_reasons
    return result


def compute_features_for_state(
    matrix: Optional[np.ndarray],
    *,
    requested_features: list[str],
    graph_policy: dict[str, Any],
    n_timepoints: Optional[int] = None,
    missing_value_fraction: Optional[float] = None,
    confounds: Optional[dict[str, Any]] = None,
) -> dict[str, float]:
    """Never fabricates a value: every branch either derives a real number
    from `matrix`/`n_timepoints`/`confounds`, or returns NaN."""
    graph_metrics = compute_graph_metrics(matrix, requested_features=requested_features, graph_policy=graph_policy)
    result: dict[str, float] = {}
    for feature_name in requested_features:
        if feature_name == "connectivity.mean_connectivity":
            result[feature_name] = compute_mean_connectivity(matrix)
        elif feature_name in GRAPH_REQUIRING_FEATURES:
            result[feature_name] = graph_metrics.get(feature_name, float("nan"))
        elif feature_name == "qc.valid_timepoints":
            result[feature_name] = float(n_timepoints) if n_timepoints is not None else float("nan")
        elif feature_name == "qc.missing_value_fraction":
            result[feature_name] = float(missing_value_fraction) if missing_value_fraction is not None else float("nan")
        elif feature_name == "qc.mean_fd":
            value = (confounds or {}).get("mean_fd")
            result[feature_name] = float(value) if value is not None else float("nan")
        elif feature_name == "qc.motion_outlier_fraction":
            value = (confounds or {}).get("motion_outlier_fraction")
            result[feature_name] = float(value) if value is not None else float("nan")
        elif feature_name in SUPPORTED_TOPOLOGY_FEATURES:
            # Never computed by this recipe -- graph_summary pass-through only.
            result[feature_name] = float("nan")
        else:
            result[feature_name] = float("nan")
    return result


# ── input loading ──────────────────────────────────────────────────────────


def load_timeseries_or_matrix_table(path: Union[str, Path]) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        raise FmriFeatureRecipeError(f"input file does not exist: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FmriFeatureRecipeError(f"input file is not valid JSON: {path} ({exc})") from exc
    if "dataset_id" not in data or "subjects" not in data:
        raise FmriFeatureRecipeError(f"input table must contain 'dataset_id' and 'subjects': {path}")
    return data


@dataclass
class _ExtractionResult:
    rows: list[dict[str, Any]]
    subjects_seen: list[str]
    subjects_used: list[str]
    sessions_used: list[str]
    states_observed: list[str]
    skipped_subjects: list[dict[str, Any]]
    skipped_inputs: list[dict[str, Any]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    qc_summary: dict[str, Any] = field(default_factory=dict)


def _apply_subject_filter(subject_ids: list[str], spec: FmriFeatureRecipeSpecV1) -> list[str]:
    if spec.subject_filter:
        return [s for s in subject_ids if s in spec.subject_filter]
    return subject_ids


def _extract_from_matrix_or_timeseries_input(
    spec: FmriFeatureRecipeSpecV1, path: Union[str, Path], *, mode: str
) -> _ExtractionResult:
    table = load_timeseries_or_matrix_table(path)
    all_subjects = sorted(table["subjects"].keys())
    filtered_subjects = _apply_subject_filter(all_subjects, spec)
    data_key = "timeseries" if mode == "timeseries_table" else "matrices"

    rows: list[dict[str, Any]] = []
    subjects_used: list[str] = []
    sessions_used: list[str] = []
    states_observed: set[str] = set()
    skipped_subjects: list[dict[str, Any]] = []
    skipped_inputs: list[dict[str, Any]] = []
    timepoint_counts: dict[str, dict[str, int]] = {}
    total_timepoints_used = 0

    def _prep(raw_state_data: Any, *, subject_id: str, canonical_state: str) -> tuple[Optional[np.ndarray], Optional[int], Optional[float]]:
        arr = np.asarray(raw_state_data, dtype=float)
        if mode == "timeseries_table":
            truncated = arr[:, : spec.max_timepoints_per_state] if arr.ndim == 2 else arr
            n_used = int(truncated.shape[1]) if truncated.ndim == 2 else 0
            missing_fraction = float(np.isnan(truncated).mean()) if truncated.size else 0.0
            matrix = compute_correlation_matrix(truncated)
            if matrix is None:
                skipped_inputs.append({
                    "subject_id": subject_id, "state": canonical_state,
                    "reason": "constant or all-NaN parcel signal -- correlation is undefined",
                })
            return matrix, n_used, missing_fraction
        matrix = arr
        if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1] or not np.all(np.isfinite(matrix)):
            skipped_inputs.append({
                "subject_id": subject_id, "state": canonical_state,
                "reason": "connectivity matrix is not a finite square matrix -- skipped rather than fabricated",
            })
            return None, None, None
        return matrix, None, None

    for subject_id in filtered_subjects:
        if len(subjects_used) + len(skipped_subjects) >= spec.max_subjects:
            skipped_subjects.append({"subject_id": subject_id, "reason": "exceeded max_subjects bound"})
            continue

        entry = table["subjects"][subject_id]
        session_id = entry.get("session")
        raw_data_by_label = entry.get(data_key) or {}
        confounds_by_label = entry.get("confounds") or {}

        data_by_state: dict[str, Any] = {}
        confounds_by_state: dict[str, Any] = {}
        for raw_label, canonical_state in spec.state_mapping.items():
            if raw_label not in raw_data_by_label:
                continue
            data_by_state[canonical_state] = raw_data_by_label[raw_label]
            if raw_label in confounds_by_label:
                confounds_by_state[canonical_state] = confounds_by_label[raw_label]

        if spec.source_state not in data_by_state or spec.target_state not in data_by_state:
            skipped_subjects.append({
                "subject_id": subject_id,
                "reason": f"missing data for source_state='{spec.source_state}' or target_state='{spec.target_state}' "
                          "(no raw label in state_mapping resolved to it for this subject)",
            })
            continue

        source_matrix, source_n, source_missing = _prep(
            data_by_state[spec.source_state], subject_id=subject_id, canonical_state=spec.source_state
        )
        target_matrix, target_n, target_missing = _prep(
            data_by_state[spec.target_state], subject_id=subject_id, canonical_state=spec.target_state
        )

        if mode == "timeseries_table":
            requested_timepoints = (source_n or 0) + (target_n or 0)
            if total_timepoints_used + requested_timepoints > spec.max_total_timepoints:
                skipped_subjects.append({"subject_id": subject_id, "reason": "exceeded max_total_timepoints bound"})
                continue
            total_timepoints_used += requested_timepoints
            timepoint_counts[subject_id] = {spec.source_state: source_n or 0, spec.target_state: target_n or 0}

        source_features = compute_features_for_state(
            source_matrix, requested_features=spec.requested_features, graph_policy=spec.graph_policy,
            n_timepoints=source_n, missing_value_fraction=source_missing, confounds=confounds_by_state.get(spec.source_state),
        )
        target_features = compute_features_for_state(
            target_matrix, requested_features=spec.requested_features, graph_policy=spec.graph_policy,
            n_timepoints=target_n, missing_value_fraction=target_missing, confounds=confounds_by_state.get(spec.target_state),
        )

        subject_had_row = False
        for feature_name in spec.requested_features:
            source_value = source_features[feature_name]
            target_value = target_features[feature_name]
            if _is_nan(source_value) or _is_nan(target_value):
                skipped_inputs.append({
                    "subject_id": subject_id, "feature_name": feature_name,
                    "reason": "source_value or target_value is NaN (could not be computed safely) -- never exported as a valid row",
                })
                continue
            rows.append({
                "dataset_id": spec.dataset_id,
                "subject_id": subject_id,
                "session_id": session_id,
                "source_state": spec.source_state,
                "target_state": spec.target_state,
                "atlas_or_parcellation": spec.atlas_or_parcellation,
                "feature_name": feature_name,
                "source_value": source_value,
                "target_value": target_value,
                "feature_definition": spec.feature_definitions[feature_name],
                "artifact_path": None,
            })
            subject_had_row = True

        if subject_had_row:
            subjects_used.append(subject_id)
            if session_id:
                sessions_used.append(str(session_id))
            states_observed.add(spec.source_state)
            states_observed.add(spec.target_state)

    qc_summary = {
        "timepoint_counts_by_subject": timepoint_counts,
        "state_imbalance": any(
            c.get(spec.source_state, 0) != c.get(spec.target_state, 0) for c in timepoint_counts.values()
        ) if timepoint_counts else False,
    }

    return _ExtractionResult(
        rows=rows,
        subjects_seen=all_subjects,
        subjects_used=subjects_used,
        sessions_used=sorted(set(sessions_used)),
        states_observed=sorted(states_observed),
        skipped_subjects=skipped_subjects,
        skipped_inputs=skipped_inputs,
        errors=[],
        qc_summary=qc_summary,
    )


def extract_from_timeseries_table(spec: FmriFeatureRecipeSpecV1, table_path: Union[str, Path]) -> _ExtractionResult:
    return _extract_from_matrix_or_timeseries_input(spec, table_path, mode="timeseries_table")


def extract_from_connectivity_matrix(spec: FmriFeatureRecipeSpecV1, matrix_path: Union[str, Path]) -> _ExtractionResult:
    return _extract_from_matrix_or_timeseries_input(spec, matrix_path, mode="connectivity_matrix")


def extract_from_graph_summary(spec: FmriFeatureRecipeSpecV1, summary_path: Union[str, Path]) -> _ExtractionResult:
    """Pure pass-through of an already-computed
    `adapters.fmri_derivatives` `format="graph_summary"` document -- this
    recipe never computes a graph or a persistence diagram in this mode,
    it only filters/renames already-provided values down to
    `spec.requested_features`."""
    from adapters.fmri_derivatives_features import expand_graph_summary, load_graph_summary

    summary = load_graph_summary(summary_path)
    subject_rows, cohort_entry = expand_graph_summary(summary)

    rows: list[dict[str, Any]] = []
    subjects_seen: set[str] = set()
    subjects_used: set[str] = set()
    sessions_used: set[str] = set()
    states_observed: set[str] = set()
    skipped_inputs: list[dict[str, Any]] = []
    requested = set(spec.requested_features)

    for row in subject_rows:
        subjects_seen.add(row["subject_id"])
        if row["feature_name"] not in requested:
            continue
        source_value = row["source_value"]
        target_value = row["target_value"]
        if source_value is None or target_value is None or _is_nan(source_value) or _is_nan(target_value):
            skipped_inputs.append({
                "subject_id": row["subject_id"], "feature_name": row["feature_name"],
                "reason": "source_value or target_value missing/NaN in graph_summary -- never exported as a valid row",
            })
            continue
        rows.append({
            "dataset_id": row["dataset_id"],
            "subject_id": row["subject_id"],
            "session_id": row.get("session_id"),
            "source_state": row["source_state"],
            "target_state": row["target_state"],
            "atlas_or_parcellation": row.get("atlas_or_parcellation") or spec.atlas_or_parcellation,
            "feature_name": row["feature_name"],
            "source_value": float(source_value),
            "target_value": float(target_value),
            "feature_definition": row.get("feature_definition") or spec.feature_definitions.get(row["feature_name"], ""),
            "artifact_path": row.get("artifact_path"),
        })
        subjects_used.add(row["subject_id"])
        if row.get("session_id"):
            sessions_used.add(str(row["session_id"]))
        states_observed.add(row["source_state"])
        states_observed.add(row["target_state"])

    return _ExtractionResult(
        rows=rows,
        subjects_seen=sorted(subjects_seen),
        subjects_used=sorted(subjects_used),
        sessions_used=sorted(sessions_used),
        states_observed=sorted(states_observed),
        skipped_subjects=[],
        skipped_inputs=skipped_inputs,
        errors=[],
        qc_summary={"cohort_entry_present": cohort_entry is not None},
    )


# ── orchestration + output writing ────────────────────────────────────────


def run_feature_recipe(spec: FmriFeatureRecipeSpecV1, *, input_path: Optional[Union[str, Path]] = None) -> _ExtractionResult:
    spec.validate_or_raise()
    if input_path is None:
        raise FmriFeatureRecipeError("input_path is required")
    if spec.input_kind == "timeseries_table":
        return extract_from_timeseries_table(spec, input_path)
    if spec.input_kind == "connectivity_matrix":
        return extract_from_connectivity_matrix(spec, input_path)
    if spec.input_kind == "graph_summary":
        return extract_from_graph_summary(spec, input_path)
    raise FmriFeatureRecipeError(f"unsupported input_kind: {spec.input_kind}")


def _confound_policy_string(confound_policy: dict[str, Any]) -> str:
    return str((confound_policy or {}).get("description") or "").strip()


def _write_derived_features_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=_LONG_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") if row.get(col) is not None else "" for col in _LONG_COLUMNS})


def _write_mapping_json(spec: FmriFeatureRecipeSpecV1, path: Path) -> None:
    mapping = {
        "format": "long",
        "dataset_id": spec.dataset_id,
        "modality": spec.modality,
        "atlas_or_parcellation": spec.atlas_or_parcellation,
        "feature_definitions": dict(spec.feature_definitions),
        "confound_policy": _confound_policy_string(spec.confound_policy),
        "preprocessing_provenance": {
            "recipe": "adapters.fmri_derivatives_feature_recipe",
            "recipe_id": spec.recipe_id,
            "feature_set_id": spec.feature_set_id,
            "input_kind": spec.input_kind,
            "connectivity_policy": dict(spec.connectivity_policy or {}),
            "graph_policy": dict(spec.graph_policy or {}),
            "qc_policy": dict(spec.qc_policy or {}),
            "confound_policy_detail": dict(spec.confound_policy or {}),
        },
        "null_control_status": "not_provided",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(mapping, indent=2) + "\n", encoding="utf-8")


def write_recipe_outputs(
    spec: FmriFeatureRecipeSpecV1, result: _ExtractionResult, out_dir: Union[str, Path]
) -> tuple[Path, Path, FmriDerivedFeatureRecipeManifestV1, Path]:
    """Validates `out_dir` via the same target-root safety check
    `dataset_acquisition.store` already uses, then writes
    `derived_features.csv`, `mapping.json`, `recipe_manifest.json`, and
    `summary.json`."""
    resolved_out = validate_target_root(out_dir)
    resolved_out.mkdir(parents=True, exist_ok=True)

    features_path = resolved_out / "derived_features.csv"
    mapping_path = resolved_out / "mapping.json"
    manifest_path = resolved_out / "recipe_manifest.json"
    summary_path = resolved_out / "summary.json"

    _write_derived_features_csv(result.rows, features_path)
    _write_mapping_json(spec, mapping_path)

    n_transitions_exportable = len({(r["subject_id"], r["session_id"]) for r in result.rows})

    manifest = FmriDerivedFeatureRecipeManifestV1.make(
        recipe_id=spec.recipe_id,
        dataset_id=spec.dataset_id,
        input_root=spec.derivatives_root or f"({spec.input_kind})",
        output_features_path=str(features_path.relative_to(_REPO_ROOT)) if _is_under_repo(features_path) else str(features_path),
        output_mapping_path=str(mapping_path.relative_to(_REPO_ROOT)) if _is_under_repo(mapping_path) else str(mapping_path),
        output_summary_path=str(summary_path.relative_to(_REPO_ROOT)) if _is_under_repo(summary_path) else str(summary_path),
        subjects_seen=result.subjects_seen,
        subjects_used=result.subjects_used,
        sessions_used=result.sessions_used,
        runs_used=[],
        states_observed=result.states_observed,
        transitions_exportable=n_transitions_exportable,
        features_written=len(result.rows),
        skipped_inputs=result.skipped_inputs,
        skipped_subjects=result.skipped_subjects,
        errors=result.errors,
        qc_summary=result.qc_summary,
        repo_commit=_repo_commit(),
        limitations=[
            "This recipe computes only the small, conservative connectivity/graph/QC feature set requested -- "
            "it is not a general fMRIPrep/Nilearn replacement and does not run raw BOLD preprocessing, "
            "does not execute fMRIPrep, and does not fit any Nilearn model.",
            "Derived feature values are not evidence by themselves -- see docs/fmri_derivatives_feature_recipe.md.",
        ],
        provenance=(
            f"Produced by adapters.fmri_derivatives_feature_recipe.run_feature_recipe for recipe_id={spec.recipe_id} "
            f"(input_kind={spec.input_kind})."
        ),
    )
    manifest.validate_or_raise()
    manifest.write_json(manifest_path)

    summary = {
        "recipe_id": spec.recipe_id,
        "manifest_id": manifest.manifest_id,
        "dataset_id": spec.dataset_id,
        "subjects_used": len(result.subjects_used),
        "subjects_skipped": len(result.skipped_subjects),
        "states_observed": result.states_observed,
        "features_written": len(result.rows),
        "transitions_exportable": n_transitions_exportable,
        "qc_summary": result.qc_summary,
        "output_features_path": manifest.output_features_path,
        "output_mapping_path": manifest.output_mapping_path,
    }
    summary_path.parent.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    return features_path, mapping_path, manifest, summary_path
