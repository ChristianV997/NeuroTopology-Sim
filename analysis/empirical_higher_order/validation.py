"""Strict validation and readiness classification for local empirical manifests."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import math
from pathlib import Path
from typing import Any, Mapping

import numpy as np

from .schema import FEATURE_FAMILIES, ManifestError, load_manifest, local_path, sha256_file


class ReadinessState(str, Enum):
    READY_FOR_DESCRIPTIVE_ANALYSIS = "READY_FOR_DESCRIPTIVE_ANALYSIS"
    READY_FOR_FORECASTING = "READY_FOR_FORECASTING"
    INSUFFICIENT_PAIRED_SUBJECTS = "INSUFFICIENT_PAIRED_SUBJECTS"
    INCOMPLETE_PROVENANCE = "INCOMPLETE_PROVENANCE"
    MISSING_OPTIONAL_DEPENDENCY = "MISSING_OPTIONAL_DEPENDENCY"
    NO_DATA = "NO_DATA"
    SYNTHETIC_DEMO_ONLY = "SYNTHETIC_DEMO_ONLY"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass
class ValidationResult:
    status: ReadinessState
    reasons: list[str] = field(default_factory=list)
    recordings: list[dict[str, Any]] = field(default_factory=list)
    paired_subjects: list[str] = field(default_factory=list)
    missing_optional: list[str] = field(default_factory=list)
    manifest: dict[str, Any] | None = None

    @property
    def ok(self) -> bool:
        return self.status in {ReadinessState.READY_FOR_DESCRIPTIVE_ANALYSIS, ReadinessState.READY_FOR_FORECASTING}

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "reasons": list(dict.fromkeys(self.reasons)),
            "recording_count": len(self.recordings),
            "paired_subjects": list(self.paired_subjects),
            "paired_subject_count": len(self.paired_subjects),
            "missing_optional_dependencies": list(self.missing_optional),
        }


def _finite(value: Any) -> bool:
    try:
        return math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _load_array(path: Path) -> np.ndarray:
    if path.suffix.lower() == ".npy":
        return np.asarray(np.load(path, mmap_mode="r", allow_pickle=False))
    if path.suffix.lower() == ".npz":
        with np.load(path, allow_pickle=False) as bundle:
            if not bundle.files:
                raise ManifestError(f"empty feature archive: {path}")
            return np.asarray(bundle[bundle.files[0]])
    raise ManifestError(f"feature artifact must be .npy or .npz: {path}")


def _recording_paths(recording: Mapping[str, Any], base: Path) -> dict[str, Path | None]:
    raw = recording.get("feature_paths")
    if not isinstance(raw, Mapping):
        raw = {}
    paths = {family: local_path(raw.get(family), base, required=(family != "higher_order_spectra")) for family in FEATURE_FAMILIES}
    paths["target"] = local_path(recording.get("target_path"), base, required=False)
    paths["timestamps"] = local_path(recording.get("timestamps_path"), base, required=False)
    return paths


def validate_manifest(path: str | Path) -> ValidationResult:
    try:
        manifest = load_manifest(path)
    except (ManifestError, OSError) as exc:
        return ValidationResult(ReadinessState.INCONCLUSIVE, [str(exc)])
    base = Path(manifest["_base_dir"])
    recordings = manifest.get("recordings")
    if not isinstance(recordings, list) or not recordings:
        return ValidationResult(ReadinessState.NO_DATA, ["recordings is empty or absent"], manifest=manifest)
    if manifest.get("schema_version") != "NeuroTopologySim.EmpiricalHigherOrderManifest.v1":
        return ValidationResult(ReadinessState.INCOMPLETE_PROVENANCE, ["unsupported or missing manifest schema_version"], manifest=manifest)
    if not _finite(manifest.get("prediction_horizon")) or float(manifest["prediction_horizon"]) <= 0:
        return ValidationResult(ReadinessState.INCOMPLETE_PROVENANCE, ["positive prediction_horizon is required"], manifest=manifest)
    if not str(manifest.get("target_definition", "")).strip():
        return ValidationResult(ReadinessState.INCOMPLETE_PROVENANCE, ["target_definition must be explicit"], manifest=manifest)
    reasons: list[str] = []
    validated: list[dict[str, Any]] = []
    optional_missing: set[str] = set()
    incomplete = False
    invalid = False
    target_missing = False
    synthetic = bool(manifest.get("synthetic", False))
    if manifest.get("source_type") not in {"empirical_local", "synthetic"}:
        reasons.append("source_type must explicitly be empirical_local or synthetic")
        incomplete = True
    provenance = manifest.get("provenance")
    if not isinstance(provenance, Mapping) or not provenance.get("source") or provenance.get("complete") is not True:
        reasons.append("provenance.source and provenance.complete=true are required")
        incomplete = True
    dataset_path = None
    try:
        dataset_path = local_path(manifest.get("dataset_path"), base)
    except ManifestError as exc:
        reasons.append(str(exc)); invalid = True
    if dataset_path is None or not dataset_path.is_file():
        reasons.append("dataset_path must identify an existing local dataset artifact")
        incomplete = True
    elif not manifest.get("dataset_checksum") or str(manifest["dataset_checksum"]).lower() != sha256_file(dataset_path):
        reasons.append("dataset checksum does not match the declared SHA-256")
        invalid = True
    by_pair: dict[str, dict[str, set[str]]] = {}
    identities: set[tuple[str, str, str]] = set()
    for index, raw in enumerate(recordings):
        if not isinstance(raw, Mapping):
            reasons.append(f"recordings[{index}] is not an object"); invalid = True; continue
        required_text = ("subject_id", "session_id", "run_id", "condition_label", "pairing_key", "recording_quality_state")
        missing = [key for key in required_text if not str(raw.get(key, "")).strip()]
        if missing:
            reasons.append(f"recordings[{index}] missing explicit fields: {', '.join(missing)}"); incomplete = True
        if "condition_label" in missing:
            reasons.append(f"recordings[{index}] condition label is ambiguous, not an implicit default")
            invalid = True
        if raw.get("recording_quality_state") not in {"PASS", "FAIL", "UNKNOWN"}:
            reasons.append(f"recordings[{index}] has invalid recording-quality state"); invalid = True
        elif raw.get("recording_quality_state") == "FAIL":
            reasons.append(f"recordings[{index}] recording-quality state is FAIL")
            invalid = True
        if raw.get("origin") not in {"empirical", "synthetic"}:
            reasons.append(f"recordings[{index}] origin must be empirical or synthetic"); incomplete = True
        if raw.get("origin") == "synthetic": synthetic = True
        identity = tuple(str(raw.get(key, "")).strip() for key in ("subject_id", "session_id", "run_id"))
        if all(identity) and identity in identities:
            reasons.append(f"recordings[{index}] duplicates subject/session/run identity")
            invalid = True
        identities.add(identity)
        if not _finite(raw.get("sampling_rate_hz")) or float(raw.get("sampling_rate_hz")) <= 0:
            reasons.append(f"recordings[{index}] sampling_rate_hz is invalid"); invalid = True
        channels = raw.get("channel_count")
        if not isinstance(channels, int) or channels < 1:
            reasons.append(f"recordings[{index}] channel_count is invalid"); invalid = True
        coords = raw.get("montage_coordinates")
        if not isinstance(coords, list) or not isinstance(channels, int) or len(coords) != channels:
            reasons.append(f"recordings[{index}] montage coordinates do not match channel count"); incomplete = True
        else:
            try:
                arr = np.asarray(coords, dtype=float)
                if arr.ndim != 2 or arr.shape[1] < 2 or not np.all(np.isfinite(arr)):
                    raise ValueError
            except (TypeError, ValueError):
                reasons.append(f"recordings[{index}] montage coordinates must be finite numeric Nx2/Nx3"); invalid = True
        try:
            paths = _recording_paths(raw, base)
        except ManifestError as exc:
            reasons.append(f"recordings[{index}]: {exc}"); invalid = True; continue
        if paths["target"] is None or not paths["target"].is_file():
            target_missing = True
        for family in FEATURE_FAMILIES[:-1]:
            if paths[family] is None or not paths[family].is_file():
                reasons.append(f"recordings[{index}] missing {family} feature artifact"); incomplete = True
        if paths["higher_order_spectra"] is None or not paths["higher_order_spectra"].is_file():
            optional_missing.add("higher_order_spectra")
        for family, artifact in paths.items():
            if family == "higher_order_spectra" or family in {"target", "timestamps"}:
                continue
            try:
                values = _load_array(artifact)
                if not np.all(np.isfinite(values)):
                    reasons.append(f"recordings[{index}] {family} contains NaN or Inf"); invalid = True
            except (OSError, ValueError, ManifestError) as exc:
                reasons.append(f"recordings[{index}] {family} cannot be read: {exc}"); invalid = True
        subject = str(raw.get("subject_id", "")).strip()
        pairing = str(raw.get("pairing_key", "")).strip()
        condition = str(raw.get("condition_label", "")).strip()
        if subject and pairing and condition:
            by_pair.setdefault(pairing, {}).setdefault(subject, set()).add(condition)
        validated.append({"raw": dict(raw), "paths": paths})
    paired = sorted(subject for group in by_pair.values() for subject, labels in group.items() if len(labels) == 2)
    ambiguous = any(len(labels) != 2 for group in by_pair.values() for labels in group.values())
    if ambiguous:
        reasons.append("each pairing key must resolve to exactly two explicit condition labels per subject")
        invalid = True
    if synthetic:
        return ValidationResult(ReadinessState.SYNTHETIC_DEMO_ONLY, reasons + ["synthetic origin is never eligible for empirical forecasting"], validated, paired, sorted(optional_missing), manifest)
    if invalid:
        return ValidationResult(ReadinessState.INCONCLUSIVE, reasons, validated, paired, sorted(optional_missing), manifest)
    if incomplete:
        return ValidationResult(ReadinessState.INCOMPLETE_PROVENANCE, reasons, validated, paired, sorted(optional_missing), manifest)
    if len(paired) < 2:
        return ValidationResult(ReadinessState.INSUFFICIENT_PAIRED_SUBJECTS, reasons + ["at least two paired subjects are required for subject-held-out forecasting"], validated, paired, sorted(optional_missing), manifest)
    if target_missing:
        return ValidationResult(ReadinessState.READY_FOR_DESCRIPTIVE_ANALYSIS, reasons + ["forecast target is not supplied; descriptive execution only"], validated, paired, sorted(optional_missing), manifest)
    if optional_missing:
        reasons.append("higher_order_spectra is optional and unavailable; classified explicitly")
    return ValidationResult(ReadinessState.READY_FOR_FORECASTING, reasons, validated, paired, sorted(optional_missing), manifest)
