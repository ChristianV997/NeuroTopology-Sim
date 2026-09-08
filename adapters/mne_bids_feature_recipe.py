"""Bounded MNE/BIDS local derived-feature extraction recipe.

Turns an already-local BIDS-like EEG root (or a pre-windowed epoch-table
fixture) into the explicit `derived_features.csv` + `mapping.json` pair
`adapters.mne_bids` consumes. This module never downloads data, never
infers `source_state`/`target_state` from event labels (only an explicit
`event_state_mapping` ever does that), and never computes a null control
(`null_control_status` is always `"not_provided"`).

Two `input_kind` modes:

- **`epoch_table`** (default, no MNE dependency): reads a small JSON file
  of already-windowed epoch arrays -- `{"sfreq":.., "channels":[...],
  "subjects": {"sub-01": {"epochs": {"rest": [[[...]]], "task": [...]}}}}`.
  This is the primary, always-tested path.
- **`bids_raw`** (best-effort, requires the already-declared `mne`
  dependency): walks `bids_root` for `*_events.tsv` files, reads the
  sibling raw EEG file via `mne.io.read_raw`, and epochs directly from the
  events file's own `onset`/`duration` columns (never from a stim
  channel/`find_events` guess).

Feature computation for both modes reuses
`sciencer_d.btc_icft.level_m.real_features.compute_band_power` (this
repository's own existing, tested Welch-PSD band-power implementation)
rather than reimplementing spectral decomposition -- see
docs/mne_bids_feature_recipe.md.
"""
from __future__ import annotations

import csv
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Union

import numpy as np

from adapters.mne_bids_feature_recipe_schema import DerivedFeatureRecipeManifestV1, FeatureRecipeSpecV1
from adapters.mne_bids_feature_recipe_validation import (
    SUPPORTED_COMPLEXITY_FEATURES,
    SUPPORTED_QC_FEATURES,
    SUPPORTED_SPECTRAL_FEATURES,
)
from dataset_acquisition.store import validate_target_root
from sciencer_d.btc_icft.level_m.real_features import compute_band_power

_REPO_ROOT = Path(__file__).resolve().parents[1]

_LONG_COLUMNS: tuple[str, ...] = (
    "dataset_id", "subject_id", "session_id", "source_state", "target_state",
    "feature_name", "source_value", "target_value", "feature_definition", "artifact_path",
)


class FeatureRecipeError(ValueError):
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


def _bids_entities(filename: str) -> dict[str, Optional[str]]:
    """Parse `sub-XX`/`ses-XX`/`task-XX`/`run-XX` BIDS entities from a
    filename. Purely mechanical string parsing -- never used to infer a
    state, only to locate/filter files."""
    entities: dict[str, Optional[str]] = {"sub": None, "ses": None, "task": None, "run": None}
    for key in entities:
        match = re.search(rf"(?:^|_){key}-([A-Za-z0-9]+)(?:_|\.)", filename)
        if match:
            entities[key] = match.group(1)
    return entities


# ── feature computation (shared by both input_kind modes) ────────────────


def _spectral_entropy(signal: np.ndarray, sfreq: float) -> float:
    """Shannon entropy (normalized to [0, 1]) of the Welch PSD's normalized
    distribution -- the standard textbook definition of spectral entropy.
    Implemented directly (not via an external package) so this recipe has
    no dependency beyond scipy/numpy, both already core requirements."""
    from scipy.signal import welch

    sig = np.asarray(signal, dtype=float)
    nperseg = min(len(sig), int(sfreq * 2))
    if nperseg < 8:
        return float("nan")
    _freqs, psd = welch(sig, fs=sfreq, nperseg=nperseg)
    psd = psd[psd > 0]
    if psd.size < 2:
        return float("nan")
    p = psd / psd.sum()
    entropy = float(-np.sum(p * np.log2(p)))
    return entropy / float(np.log2(len(p)))


def compute_features_for_epochs(
    epochs: list[np.ndarray],
    *,
    sfreq: float,
    requested_features: list[str],
    frequency_bands: dict[str, list[float]],
    epoch_length_seconds: Optional[float] = None,
) -> dict[str, float]:
    """`epochs` is a list of `(n_channels, n_samples)` arrays for one
    (subject, state). Returns `{feature_name: value}`, averaged across
    epochs and channels. Never fabricates a value for an empty `epochs`
    list -- returns NaN for every requested feature instead."""
    bands = {name: tuple(bounds) for name, bounds in frequency_bands.items()}
    result: dict[str, float] = {}

    if not epochs:
        return {name: float("nan") for name in requested_features}

    n_channels = epochs[0].shape[0]
    total_samples = sum(e.shape[1] for e in epochs)
    flat_all = np.concatenate([e.flatten() for e in epochs]) if epochs else np.array([])
    missing_fraction = float(np.isnan(flat_all).mean()) if flat_all.size else 0.0

    for feature_name in requested_features:
        if feature_name in SUPPORTED_SPECTRAL_FEATURES:
            band_name = feature_name.split(".", 1)[1].replace("_power", "")
            values: list[float] = []
            for epoch in epochs:
                for ch in range(epoch.shape[0]):
                    sig = epoch[ch]
                    if np.all(np.isnan(sig)):
                        continue
                    band_power = compute_band_power(np.nan_to_num(sig), sfreq, bands=bands)
                    key = f"{band_name}_power_rel"
                    if key in band_power:
                        values.append(band_power[key])
            result[feature_name] = float(np.mean(values)) if values else float("nan")

        elif feature_name in SUPPORTED_COMPLEXITY_FEATURES:
            values = []
            for epoch in epochs:
                for ch in range(epoch.shape[0]):
                    sig = epoch[ch]
                    if np.all(np.isnan(sig)):
                        continue
                    values.append(_spectral_entropy(np.nan_to_num(sig), sfreq))
            finite = [v for v in values if not np.isnan(v)]
            result[feature_name] = float(np.mean(finite)) if finite else float("nan")

        elif feature_name == "qc.valid_epoch_count":
            result[feature_name] = float(len(epochs))
        elif feature_name == "qc.channel_count":
            result[feature_name] = float(n_channels)
        elif feature_name == "qc.duration_seconds":
            if epoch_length_seconds is not None:
                result[feature_name] = float(len(epochs) * epoch_length_seconds)
            else:
                result[feature_name] = float(total_samples) / float(sfreq) if sfreq else float("nan")
        elif feature_name == "qc.missing_value_fraction":
            result[feature_name] = missing_fraction
        else:
            result[feature_name] = float("nan")

    return result


# ── epoch_table input_kind ────────────────────────────────────────────────


def load_epoch_table(path: Union[str, Path]) -> dict[str, Any]:
    path = Path(path)
    if not path.exists():
        raise FeatureRecipeError(f"epoch table file does not exist: {path}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise FeatureRecipeError(f"epoch table file is not valid JSON: {path} ({exc})") from exc
    if "sfreq" not in data or "subjects" not in data:
        raise FeatureRecipeError(f"epoch table must contain 'sfreq' and 'subjects': {path}")
    return data


@dataclass
class _ExtractionResult:
    rows: list[dict[str, Any]]
    subjects_seen: list[str]
    subjects_used: list[str]
    sessions_used: list[str]
    states_observed: list[str]
    skipped_subjects: list[dict[str, Any]]
    skipped_runs: list[dict[str, Any]]
    skipped_events: list[dict[str, Any]]
    errors: list[str]
    qc_summary: dict[str, Any]


def _apply_subject_filter(subject_ids: list[str], spec: FeatureRecipeSpecV1) -> list[str]:
    if spec.subject_filter:
        return [s for s in subject_ids if s in spec.subject_filter]
    return subject_ids


def extract_from_epoch_table(spec: FeatureRecipeSpecV1, table_path: Union[str, Path]) -> _ExtractionResult:
    table = load_epoch_table(table_path)
    sfreq = float(table["sfreq"])
    all_subjects = sorted(table["subjects"].keys())
    filtered_subjects = _apply_subject_filter(all_subjects, spec)

    rows: list[dict[str, Any]] = []
    subjects_used: list[str] = []
    sessions_used: list[str] = []
    states_observed: set[str] = set()
    skipped_subjects: list[dict[str, Any]] = []
    errors: list[str] = []
    epoch_counts: dict[str, dict[str, int]] = {}
    total_epochs_used = 0

    for subject_id in filtered_subjects:
        if len(subjects_used) + len(skipped_subjects) >= spec.max_subjects:
            skipped_subjects.append({"subject_id": subject_id, "reason": "exceeded max_subjects bound"})
            continue

        entry = table["subjects"][subject_id]
        session_id = entry.get("session")
        epochs_by_raw_label = entry.get("epochs") or {}

        # event_state_mapping keys are the raw labels present in the
        # fixture/table; values are the canonical states. Only labels
        # explicitly present in the mapping are ever consulted.
        epochs_by_state: dict[str, list[np.ndarray]] = {}
        for raw_label, canonical_state in spec.event_state_mapping.items():
            if raw_label not in epochs_by_raw_label:
                continue
            arrays = [np.asarray(e, dtype=float) for e in epochs_by_raw_label[raw_label]]
            epochs_by_state.setdefault(canonical_state, []).extend(arrays)

        if spec.source_state not in epochs_by_state or spec.target_state not in epochs_by_state:
            skipped_subjects.append({
                "subject_id": subject_id,
                "reason": f"missing epochs for source_state='{spec.source_state}' or target_state='{spec.target_state}'",
            })
            continue

        source_epochs = epochs_by_state[spec.source_state][: spec.max_epochs_per_state]
        target_epochs = epochs_by_state[spec.target_state][: spec.max_epochs_per_state]

        if total_epochs_used + len(source_epochs) + len(target_epochs) > spec.max_total_epochs:
            remaining = max(spec.max_total_epochs - total_epochs_used, 0)
            source_epochs = source_epochs[: remaining // 2]
            target_epochs = target_epochs[: remaining - len(source_epochs)]
            if not source_epochs or not target_epochs:
                skipped_subjects.append({"subject_id": subject_id, "reason": "exceeded max_total_epochs bound"})
                continue

        total_epochs_used += len(source_epochs) + len(target_epochs)
        epoch_counts[subject_id] = {spec.source_state: len(source_epochs), spec.target_state: len(target_epochs)}

        source_features = compute_features_for_epochs(
            source_epochs, sfreq=sfreq, requested_features=spec.requested_features, frequency_bands=spec.frequency_bands,
            epoch_length_seconds=spec.epoch_window.get("length_seconds"),
        )
        target_features = compute_features_for_epochs(
            target_epochs, sfreq=sfreq, requested_features=spec.requested_features, frequency_bands=spec.frequency_bands,
            epoch_length_seconds=spec.epoch_window.get("length_seconds"),
        )

        for feature_name in spec.requested_features:
            rows.append({
                "dataset_id": spec.dataset_id,
                "subject_id": subject_id,
                "session_id": session_id,
                "source_state": spec.source_state,
                "target_state": spec.target_state,
                "feature_name": feature_name,
                "source_value": source_features[feature_name],
                "target_value": target_features[feature_name],
                "feature_definition": spec.feature_definitions[feature_name],
                "artifact_path": None,
            })

        subjects_used.append(subject_id)
        if session_id:
            sessions_used.append(str(session_id))
        states_observed.add(spec.source_state)
        states_observed.add(spec.target_state)

    n_source = sum(c.get(spec.source_state, 0) for c in epoch_counts.values())
    n_target = sum(c.get(spec.target_state, 0) for c in epoch_counts.values())
    qc_summary = {
        "epoch_counts_by_subject": epoch_counts,
        "total_source_epochs": n_source,
        "total_target_epochs": n_target,
        "state_imbalance": n_source != n_target,
    }

    return _ExtractionResult(
        rows=rows,
        subjects_seen=all_subjects,
        subjects_used=subjects_used,
        sessions_used=sorted(set(sessions_used)),
        states_observed=sorted(states_observed),
        skipped_subjects=skipped_subjects,
        skipped_runs=[],
        skipped_events=[],
        errors=errors,
        qc_summary=qc_summary,
    )


# ── bids_raw input_kind (best-effort, requires mne) ───────────────────────

_RAW_SUFFIXES: tuple[str, ...] = ("_eeg.fif", "_eeg.edf", "_eeg.bdf", "_eeg.set", "_eeg.vhdr")


def _find_sibling_raw_file(events_path: Path) -> Optional[Path]:
    base = events_path.name.replace("_events.tsv", "")
    for suffix in _RAW_SUFFIXES:
        candidate = events_path.parent / f"{base}{suffix}"
        if candidate.exists():
            return candidate
    return None


def _read_events_tsv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        return [dict(row) for row in reader]


def extract_from_bids_raw(spec: FeatureRecipeSpecV1) -> _ExtractionResult:
    try:
        import mne
    except ImportError as exc:
        raise FeatureRecipeError(f"input_kind='bids_raw' requires the mne package: {exc}") from exc

    bids_root = Path(spec.bids_root)
    if not bids_root.exists() or not bids_root.is_dir():
        raise FeatureRecipeError(f"bids_root does not exist or is not a directory: {bids_root}")

    events_files = sorted(bids_root.rglob("*_events.tsv"))
    rows: list[dict[str, Any]] = []
    all_subjects: set[str] = set()
    subjects_used: list[str] = []
    sessions_used: set[str] = set()
    states_observed: set[str] = set()
    skipped_subjects: list[dict[str, Any]] = []
    skipped_runs: list[dict[str, Any]] = []
    skipped_events: list[dict[str, Any]] = []
    errors: list[str] = []
    epoch_counts: dict[str, dict[str, int]] = {}
    total_epochs_used = 0
    subjects_considered: set[str] = set()

    for events_path in events_files:
        entities = _bids_entities(events_path.name)
        subject_id = f"sub-{entities['sub']}" if entities["sub"] else None
        if not subject_id:
            continue
        all_subjects.add(subject_id)

        if spec.subject_filter and subject_id not in spec.subject_filter:
            continue
        if spec.task_filter and entities["task"] not in spec.task_filter:
            continue
        if spec.run_filter and entities["run"] not in spec.run_filter:
            continue
        if spec.session_filter and entities["ses"] not in spec.session_filter:
            continue

        if subject_id not in subjects_considered and len(subjects_considered) >= spec.max_subjects:
            skipped_subjects.append({"subject_id": subject_id, "reason": "exceeded max_subjects bound"})
            continue
        subjects_considered.add(subject_id)

        raw_path = _find_sibling_raw_file(events_path)
        if raw_path is None:
            skipped_runs.append({"file": str(events_path.relative_to(bids_root)), "reason": "no sibling raw EEG file found"})
            continue

        try:
            raw = mne.io.read_raw(str(raw_path), preload=True, verbose=False)
        except Exception as exc:  # unreadable/corrupt file -- skip, never abort the whole recipe
            skipped_runs.append({"file": str(raw_path.relative_to(bids_root)), "reason": f"failed to read raw file: {exc}"})
            continue

        if spec.reference_policy == "average":
            raw.set_eeg_reference("average", verbose=False)
        l_freq = spec.filter_policy.get("l_freq")
        h_freq = spec.filter_policy.get("h_freq")
        if l_freq is not None or h_freq is not None:
            raw.filter(l_freq=l_freq, h_freq=h_freq, verbose=False)

        picks = spec.channel_policy.get("picks") or ["all"]
        if picks != ["all"]:
            raw.pick(picks)

        sfreq = float(raw.info["sfreq"])
        epoch_length_samples = int(spec.epoch_window.get("length_seconds", 2.0) * sfreq)

        events = _read_events_tsv(events_path)
        epochs_by_state: dict[str, list[np.ndarray]] = {}
        for event in events:
            trial_type = event.get("trial_type")
            if trial_type not in spec.event_state_mapping:
                skipped_events.append({
                    "file": str(events_path.relative_to(bids_root)),
                    "trial_type": trial_type,
                    "reason": "not present in event_state_mapping (never inferred)",
                })
                continue
            canonical_state = spec.event_state_mapping[trial_type]
            try:
                onset_sample = int(float(event["onset"]) * sfreq)
            except (KeyError, ValueError):
                skipped_events.append({"file": str(events_path.relative_to(bids_root)), "trial_type": trial_type, "reason": "invalid onset"})
                continue
            end_sample = onset_sample + epoch_length_samples
            if end_sample > raw.n_times:
                skipped_events.append({"file": str(events_path.relative_to(bids_root)), "trial_type": trial_type, "reason": "epoch window exceeds recording length"})
                continue
            data = raw.get_data(start=onset_sample, stop=end_sample)
            epochs_by_state.setdefault(canonical_state, []).append(data)

        if spec.source_state not in epochs_by_state or spec.target_state not in epochs_by_state:
            skipped_subjects.append({
                "subject_id": subject_id,
                "reason": f"missing epochs for source_state='{spec.source_state}' or target_state='{spec.target_state}'",
            })
            continue

        source_epochs = epochs_by_state[spec.source_state][: spec.max_epochs_per_state]
        target_epochs = epochs_by_state[spec.target_state][: spec.max_epochs_per_state]

        if total_epochs_used + len(source_epochs) + len(target_epochs) > spec.max_total_epochs:
            remaining = max(spec.max_total_epochs - total_epochs_used, 0)
            source_epochs = source_epochs[: remaining // 2]
            target_epochs = target_epochs[: remaining - len(source_epochs)]
            if not source_epochs or not target_epochs:
                skipped_subjects.append({"subject_id": subject_id, "reason": "exceeded max_total_epochs bound"})
                continue

        total_epochs_used += len(source_epochs) + len(target_epochs)
        epoch_counts[subject_id] = {spec.source_state: len(source_epochs), spec.target_state: len(target_epochs)}

        source_features = compute_features_for_epochs(
            source_epochs, sfreq=sfreq, requested_features=spec.requested_features, frequency_bands=spec.frequency_bands,
            epoch_length_seconds=spec.epoch_window.get("length_seconds"),
        )
        target_features = compute_features_for_epochs(
            target_epochs, sfreq=sfreq, requested_features=spec.requested_features, frequency_bands=spec.frequency_bands,
            epoch_length_seconds=spec.epoch_window.get("length_seconds"),
        )

        session_id = f"ses-{entities['ses']}" if entities["ses"] else None
        for feature_name in spec.requested_features:
            rows.append({
                "dataset_id": spec.dataset_id,
                "subject_id": subject_id,
                "session_id": session_id,
                "source_state": spec.source_state,
                "target_state": spec.target_state,
                "feature_name": feature_name,
                "source_value": source_features[feature_name],
                "target_value": target_features[feature_name],
                "feature_definition": spec.feature_definitions[feature_name],
                "artifact_path": raw_path.relative_to(bids_root).as_posix(),
            })

        subjects_used.append(subject_id)
        if session_id:
            sessions_used.add(session_id)
        states_observed.add(spec.source_state)
        states_observed.add(spec.target_state)

    n_source = sum(c.get(spec.source_state, 0) for c in epoch_counts.values())
    n_target = sum(c.get(spec.target_state, 0) for c in epoch_counts.values())
    qc_summary = {
        "epoch_counts_by_subject": epoch_counts,
        "total_source_epochs": n_source,
        "total_target_epochs": n_target,
        "state_imbalance": n_source != n_target,
    }

    return _ExtractionResult(
        rows=rows,
        subjects_seen=sorted(all_subjects),
        subjects_used=subjects_used,
        sessions_used=sorted(sessions_used),
        states_observed=sorted(states_observed),
        skipped_subjects=skipped_subjects,
        skipped_runs=skipped_runs,
        skipped_events=skipped_events,
        errors=errors,
        qc_summary=qc_summary,
    )


# ── orchestration + output writing ────────────────────────────────────────


def run_feature_recipe(
    spec: FeatureRecipeSpecV1, *, epoch_table_path: Optional[Union[str, Path]] = None
) -> _ExtractionResult:
    spec.validate_or_raise()
    if spec.input_kind == "epoch_table":
        if epoch_table_path is None:
            raise FeatureRecipeError("epoch_table_path is required when input_kind='epoch_table'")
        return extract_from_epoch_table(spec, epoch_table_path)
    if spec.input_kind == "bids_raw":
        return extract_from_bids_raw(spec)
    raise FeatureRecipeError(f"unsupported input_kind: {spec.input_kind}")


def _write_derived_features_csv(rows: list[dict[str, Any]], path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=_LONG_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({col: row.get(col, "") if row.get(col) is not None else "" for col in _LONG_COLUMNS})


def _write_mapping_json(spec: FeatureRecipeSpecV1, path: Path) -> None:
    mapping = {
        "format": "long",
        "dataset_id": spec.dataset_id,
        "modality": spec.modality,
        "feature_definitions": dict(spec.feature_definitions),
        "preprocessing_provenance": {
            "recipe": "adapters.mne_bids_feature_recipe",
            "recipe_id": spec.recipe_id,
            "feature_set_id": spec.feature_set_id,
            "input_kind": spec.input_kind,
            "frequency_bands": spec.frequency_bands,
            "epoch_window": spec.epoch_window,
            "reference_policy": spec.reference_policy,
            "filter_policy": spec.filter_policy,
            "artifact_policy": spec.artifact_policy,
        },
        "null_control_status": "not_provided",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(mapping, indent=2) + "\n", encoding="utf-8")


def write_recipe_outputs(
    spec: FeatureRecipeSpecV1, result: _ExtractionResult, out_dir: Union[str, Path]
) -> tuple[Path, Path, DerivedFeatureRecipeManifestV1, Path]:
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

    manifest = DerivedFeatureRecipeManifestV1.make(
        recipe_id=spec.recipe_id,
        dataset_id=spec.dataset_id,
        input_root=spec.bids_root or "(epoch_table)",
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
        skipped_subjects=result.skipped_subjects,
        skipped_runs=result.skipped_runs,
        skipped_events=result.skipped_events,
        errors=result.errors,
        qc_summary=result.qc_summary,
        repo_commit=_repo_commit(),
        limitations=[
            "This recipe computes only the small, conservative feature set requested -- it is not a general "
            "preprocessing framework and does not perform artifact rejection, ICA, or re-referencing beyond "
            "reference_policy='average'.",
            "Derived feature values are not evidence by themselves -- see docs/mne_bids_feature_recipe.md.",
        ],
        provenance=(
            f"Produced by adapters.mne_bids_feature_recipe.run_feature_recipe for recipe_id={spec.recipe_id} "
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


def _is_under_repo(path: Path) -> bool:
    try:
        path.resolve().relative_to(_REPO_ROOT)
        return True
    except ValueError:
        return False
