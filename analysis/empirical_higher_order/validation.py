"""Strict validation and readiness classification for local empirical manifests."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import hashlib
import math
import tempfile
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
    snapshot_dir: tempfile.TemporaryDirectory | None = field(default=None, repr=False, compare=False)

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
    if isinstance(value, bool):
        return False
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


def _validate_artifact_checksums(
    recording: Mapping[str, Any],
    paths: Mapping[str, Path | None],
    index: int,
    reasons: list[str],
    snapshot_root: Path,
) -> tuple[bool, bool, dict[str, Path]]:
    """Verify and snapshot the exact bytes later validation/scoring will read."""
    declared = recording.get("artifact_checksums")
    if not isinstance(declared, Mapping):
        reasons.append(f"recordings[{index}] artifact_checksums mapping is required")
        return True, False, {}
    incomplete = False
    invalid = False
    verified_paths: dict[str, Path] = {}
    for name, artifact in paths.items():
        if artifact is None:
            continue
        checksum = declared.get(name)
        if not isinstance(checksum, str) or not checksum.strip():
            reasons.append(f"recordings[{index}] missing SHA-256 for {name}")
            incomplete = True
            continue
        expected = checksum.strip().lower()
        if len(expected) != 64 or any(character not in "0123456789abcdef" for character in expected):
            reasons.append(f"recordings[{index}] {name} checksum must be a SHA-256 hex digest")
            invalid = True
            continue
        if not artifact.is_file():
            # A declared checksum asserts that this artifact exists and is readable. An absent or
            # non-file target therefore fails the binding; it is not merely an undeclared artifact.
            reasons.append(f"recordings[{index}] declared {name} artifact is missing or not a regular file")
            invalid = True
            continue
        snapshot_path = snapshot_root / f"{index}-{name}{artifact.suffix.lower()}"
        digest = hashlib.sha256()
        try:
            with artifact.open("rb") as source, snapshot_path.open("xb") as snapshot:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(chunk)
                    snapshot.write(chunk)
        except OSError as exc:
            snapshot_path.unlink(missing_ok=True)
            reasons.append(f"recordings[{index}] {name} cannot be snapshotted: {exc}")
            invalid = True
            continue
        if digest.hexdigest() != expected:
            snapshot_path.unlink(missing_ok=True)
            reasons.append(f"recordings[{index}] {name} checksum does not match the declared SHA-256")
            invalid = True
            continue
        verified_paths[name] = snapshot_path
    return incomplete, invalid, verified_paths


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
    target_definition = manifest.get("target_definition")
    if not isinstance(target_definition, str) or not target_definition.strip():
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
    provenance_source = provenance.get("source") if isinstance(provenance, Mapping) else None
    if (
        not isinstance(provenance_source, str)
        or not provenance_source.strip()
        or provenance.get("complete") is not True
    ):
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
    else:
        try:
            dataset_checksum = sha256_file(dataset_path)
        except OSError as exc:
            reasons.append(f"dataset checksum cannot be read: {exc}")
            invalid = True
        else:
            if (
                not manifest.get("dataset_checksum")
                or str(manifest["dataset_checksum"]).lower() != dataset_checksum
            ):
                reasons.append("dataset checksum does not match the declared SHA-256")
                invalid = True
    snapshot_dir = tempfile.TemporaryDirectory(prefix="empirical-higher-order-")
    snapshot_root = Path(snapshot_dir.name)
    by_pair: dict[str, dict[str, set[str]]] = {}
    identities: set[tuple[str, str, str]] = set()
    for index, raw in enumerate(recordings):
        if not isinstance(raw, Mapping):
            reasons.append(f"recordings[{index}] is not an object"); invalid = True; continue
        required_text = ("subject_id", "session_id", "run_id", "condition_label", "pairing_key", "recording_quality_state")
        missing = [
            key for key in required_text
            if not isinstance(raw.get(key), str) or not raw[key].strip()
        ]
        if missing:
            reasons.append(f"recordings[{index}] missing explicit fields: {', '.join(missing)}"); incomplete = True
        if "condition_label" in missing:
            reasons.append(f"recordings[{index}] condition label is ambiguous, not an implicit default")
            invalid = True
        if raw.get("recording_quality_state") not in {"PASS", "FAIL", "UNKNOWN"}:
            reasons.append(f"recordings[{index}] has invalid recording-quality state"); invalid = True
        elif raw.get("recording_quality_state") == "UNKNOWN":
            reasons.append(f"recordings[{index}] recording-quality state is UNKNOWN; explicit PASS is required")
            incomplete = True
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
        if isinstance(channels, bool) or not isinstance(channels, int) or channels < 1:
            reasons.append(f"recordings[{index}] channel_count is invalid"); invalid = True
        coords = raw.get("montage_coordinates")
        if (
            not isinstance(coords, list)
            or isinstance(channels, bool)
            or not isinstance(channels, int)
            or len(coords) != channels
        ):
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
        elif paths["timestamps"] is None or not paths["timestamps"].is_file():
            reasons.append(f"recordings[{index}] timestamps artifact is required when a forecast target is supplied")
            incomplete = True
        for family in FEATURE_FAMILIES[:-1]:
            if paths[family] is None or not paths[family].is_file():
                reasons.append(f"recordings[{index}] missing {family} feature artifact"); incomplete = True
        if paths["higher_order_spectra"] is None or not paths["higher_order_spectra"].is_file():
            optional_missing.add("higher_order_spectra")
        checksum_incomplete, checksum_invalid, verified_paths = _validate_artifact_checksums(
            raw, paths, index, reasons, snapshot_root
        )
        incomplete = incomplete or checksum_incomplete
        invalid = invalid or checksum_invalid
        # Optional higher_order_spectra is not required, but a supplied and checksum-bound copy must be valid.
        for family in FEATURE_FAMILIES:
            artifact = verified_paths.get(family)
            if artifact is None:
                continue
            try:
                values = _load_array(artifact)
                if values.size == 0:
                    reasons.append(f"recordings[{index}] {family} artifact is empty; at least one observation is required")
                    invalid = True
                elif not np.all(np.isfinite(values)):
                    reasons.append(f"recordings[{index}] {family} contains NaN or Inf"); invalid = True
            except (OSError, TypeError, ValueError, ManifestError) as exc:
                reasons.append(f"recordings[{index}] {family} cannot be read: {exc}"); invalid = True
        for family in ("target", "timestamps"):
            if family == "timestamps" and "target" not in verified_paths:
                continue
            artifact = verified_paths.get(family)
            if artifact is None:
                continue
            try:
                values = _load_array(artifact)
                if values.size == 0:
                    reasons.append(f"recordings[{index}] {family} artifact is empty; at least one observation is required")
                    invalid = True
            except (OSError, TypeError, ValueError, ManifestError) as exc:
                reasons.append(f"recordings[{index}] {family} cannot be read: {exc}"); invalid = True
        subject = str(raw.get("subject_id", "")).strip()
        pairing = str(raw.get("pairing_key", "")).strip()
        condition = str(raw.get("condition_label", "")).strip()
        if subject and pairing and condition:
            by_pair.setdefault(pairing, {}).setdefault(subject, set()).add(condition)
        validated.append({"raw": dict(raw), "paths": verified_paths})
    paired = sorted(subject for group in by_pair.values() for subject, labels in group.items() if len(labels) == 2)
    ambiguous = any(len(labels) != 2 for group in by_pair.values() for labels in group.values())
    if ambiguous:
        reasons.append("each pairing key must resolve to exactly two explicit condition labels per subject")
        invalid = True
    if synthetic:
        return ValidationResult(ReadinessState.SYNTHETIC_DEMO_ONLY, reasons + ["synthetic origin is never eligible for empirical forecasting"], validated, paired, sorted(optional_missing), manifest, snapshot_dir)
    if invalid:
        return ValidationResult(ReadinessState.INCONCLUSIVE, reasons, validated, paired, sorted(optional_missing), manifest, snapshot_dir)
    if incomplete:
        return ValidationResult(ReadinessState.INCOMPLETE_PROVENANCE, reasons, validated, paired, sorted(optional_missing), manifest, snapshot_dir)
    if len(paired) < 2:
        return ValidationResult(ReadinessState.INSUFFICIENT_PAIRED_SUBJECTS, reasons + ["at least two paired subjects are required for subject-held-out forecasting"], validated, paired, sorted(optional_missing), manifest, snapshot_dir)
    if target_missing:
        return ValidationResult(ReadinessState.READY_FOR_DESCRIPTIVE_ANALYSIS, reasons + ["forecast target is not supplied; descriptive execution only"], validated, paired, sorted(optional_missing), manifest, snapshot_dir)
    if optional_missing:
        reasons.append("higher_order_spectra is optional and unavailable; classified explicitly")
    return ValidationResult(ReadinessState.READY_FOR_FORECASTING, reasons, validated, paired, sorted(optional_missing), manifest, snapshot_dir)
