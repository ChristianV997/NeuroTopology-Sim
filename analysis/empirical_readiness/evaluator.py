"""Read-only empirical-input readiness evaluator.

Consumes cohort, provenance, container-reader, and analysis-configuration
dictionaries. Does not load signal samples, download data, compute Bayes
factors, or modify provenance/adapter modules. A checksum is not empirical
validation. Synthetic input cannot PASS.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping
import json
import math

SCHEMA = "NeuroTopologySim.EmpiricalReadiness.v1"
VALIDATOR_VERSION = "1.0.0"
DEFAULT_MIN_PAIRS = 8
DEFAULT_MIN_CHANNELS = 8
ORIGIN_LABELS = frozenset({
    "empirical_local",
    "synthetic_demo",
    "external_solver",
    "unavailable",
})
READY_STATES = frozenset({
    "READY_FOR_DESCRIPTIVE_ANALYSIS",
    "READY_FOR_PAIRED_STATISTICS",
    "READY_FOR_FORMAL_EVIDENCE_REVIEW",
})
BLOCKING_STATES = frozenset({
    "INSUFFICIENT_PAIRED_SUBJECTS",
    "INCOMPLETE_PROVENANCE",
    "INVALID_INPUT",
    "SYNTHETIC_DEMO_ONLY",
    "MISSING_OPTIONAL_DEPENDENCY",
    "UNSUPPORTED_SAMPLING_RATE",
})
REQUIRED_UNITS = ("time", "sampling_frequency", "amplitude")


class ReadinessError(ValueError):
    """Malformed readiness packet or non-finite JSON value."""


@dataclass
class CheckResult:
    name: str
    passed: bool
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "passed": self.passed, "detail": self.detail}


@dataclass
class ReadinessReport:
    status: str
    reasons: list[str]
    checks: list[CheckResult]
    n_recordings: int
    n_empirical_recordings: int
    n_paired_subjects: int
    min_pairs_required: int
    descriptive_ready: bool
    paired_ready: bool
    formal_evidence_eligible: bool
    origin_summary: dict[str, int]
    missing_optional_dependency: str | None = None
    schema: str = SCHEMA
    validator_version: str = VALIDATOR_VERSION
    scientific_support: str = "not_claimed"

    def to_dict(self) -> dict[str, Any]:
        return json_safe(
            {
                "schema": SCHEMA,
                "validator_version": self.validator_version,
                "status": self.status,
                "reasons": list(self.reasons),
                "checks": [item.to_dict() for item in self.checks],
                "n_recordings": self.n_recordings,
                "n_empirical_recordings": self.n_empirical_recordings,
                "n_paired_subjects": self.n_paired_subjects,
                "min_pairs_required": self.min_pairs_required,
                "descriptive_ready": self.descriptive_ready,
                "paired_ready": self.paired_ready,
                "formal_evidence_eligible": self.formal_evidence_eligible,
                "origin_summary": dict(self.origin_summary),
                "missing_optional_dependency": self.missing_optional_dependency,
                "scientific_support": "not_claimed",
                "bayes_factor_computed": False,
                "signals_loaded": False,
            }
        )


def json_safe(value: Any, path: str = "$") -> Any:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ReadinessError(f"{path} is not a finite JSON number")
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, list):
        return [json_safe(item, f"{path}[{index}]") for index, item in enumerate(value)]
    if isinstance(value, tuple):
        return [json_safe(item, f"{path}[{index}]") for index, item in enumerate(value)]
    if isinstance(value, Mapping):
        return {
            str(key): json_safe(item, f"{path}.{key}")
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    raise ReadinessError(f"{path} is not JSON-serializable ({type(value).__name__})")


def serialize_report(report: ReadinessReport) -> str:
    return json.dumps(report.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _finite(name: str, value: Any) -> float | None:
    if value is None or value == "":
        return None
    number = float(value)
    if not math.isfinite(number):
        raise ReadinessError(f"{name} must be a finite number")
    return number


def _as_list(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _origin(recording: Mapping[str, Any]) -> str:
    origin = _text(recording.get("origin")) or "unavailable"
    if origin not in ORIGIN_LABELS:
        raise ReadinessError(f"origin {origin!r} is not recognized")
    return origin


def _paired_subjects(recordings: list[Mapping[str, Any]], cohort: Mapping[str, Any]) -> tuple[int, list[str]]:
    declared = cohort.get("pairs")
    if isinstance(declared, list) and declared:
        count = 0
        reasons: list[str] = []
        for index, pair in enumerate(declared):
            if not isinstance(pair, Mapping):
                reasons.append(f"pairs[{index}] is not a mapping")
                continue
            subject = _text(pair.get("subject_id"))
            conditions = [_text(item) for item in _as_list(pair.get("conditions"))]
            conditions = [item for item in conditions if item]
            if subject and len(set(conditions)) >= 2:
                count += 1
            else:
                reasons.append(f"pairs[{index}] lacks a subject with two explicit conditions")
        return count, reasons
    by_subject: dict[str, set[str]] = {}
    for recording in recordings:
        subject = _text(recording.get("subject_id"))
        condition = _text(recording.get("condition_label"))
        if subject and condition:
            by_subject.setdefault(subject, set()).add(condition)
    count = sum(1 for labels in by_subject.values() if len(labels) >= 2)
    return count, []


def evaluate_readiness(packet: Mapping[str, Any]) -> ReadinessReport:
    """Evaluate a local readiness packet. Never fetches or loads samples."""
    if not isinstance(packet, Mapping):
        raise ReadinessError("readiness packet must be a mapping")
    recordings = packet.get("recordings")
    if not isinstance(recordings, list) or not recordings:
        return ReadinessReport(
            status="INVALID_INPUT",
            reasons=["recordings must be a non-empty list"],
            checks=[CheckResult("recordings_present", False, "recordings missing")],
            n_recordings=0,
            n_empirical_recordings=0,
            n_paired_subjects=0,
            min_pairs_required=int(packet.get("min_pairs_required") or DEFAULT_MIN_PAIRS),
            descriptive_ready=False,
            paired_ready=False,
            formal_evidence_eligible=False,
            origin_summary={},
        )

    cohort = packet.get("cohort") if isinstance(packet.get("cohort"), Mapping) else {}
    topology = packet.get("topology") if isinstance(packet.get("topology"), Mapping) else {}
    statistics = packet.get("statistics") if isinstance(packet.get("statistics"), Mapping) else {}
    min_pairs = int(_finite("min_pairs_required", packet.get("min_pairs_required") or cohort.get("min_pairs_required") or DEFAULT_MIN_PAIRS) or DEFAULT_MIN_PAIRS)
    min_channels = int(_finite("min_channels", packet.get("min_channels") or DEFAULT_MIN_CHANNELS) or DEFAULT_MIN_CHANNELS)
    band = packet.get("requested_band_hz") if isinstance(packet.get("requested_band_hz"), Mapping) else {}
    high_hz = _finite("requested_band_hz.high_hz", band.get("high_hz"))

    checks: list[CheckResult] = []
    reasons: list[str] = []
    origins: dict[str, int] = {}
    missing_dep: str | None = None
    empirical_ok = 0
    files_exist = True
    readable = True
    checksums = True
    labels = True
    units_ok = True
    montage_ok = True
    rate_ok = True
    channels_ok = True
    preprocessing_ok = True
    origin_ok = True
    synthetic_only = True
    invalid = False

    for index, raw in enumerate(recordings):
        if not isinstance(raw, Mapping):
            invalid = True
            reasons.append(f"recordings[{index}] is not a mapping")
            continue
        origin = _origin(raw)
        origins[origin] = origins.get(origin, 0) + 1
        if origin != "synthetic_demo":
            synthetic_only = False
        path_text = _text(raw.get("local_path"))
        path = Path(path_text) if path_text else None
        exists = bool(path and path.is_file())
        size_ok = bool(exists and path.stat().st_size > 0)
        if not exists:
            files_exist = False
            reasons.append(f"recordings[{index}] local file is missing")
        elif not size_ok:
            readable = False
            reasons.append(f"recordings[{index}] local file is empty")
        if not _text(raw.get("file_checksum_sha256")):
            checksums = False
            reasons.append(f"recordings[{index}] checksum is missing")
        if not _text(raw.get("condition_label")):
            labels = False
            reasons.append(f"recordings[{index}] condition_label is missing")
        units = raw.get("units") if isinstance(raw.get("units"), Mapping) else {}
        if any(not _text(units.get(key)) for key in REQUIRED_UNITS):
            units_ok = False
            reasons.append(f"recordings[{index}] units are incomplete")
        montage = _text(raw.get("montage_state") or raw.get("montage_source"))
        if montage in (None, "unavailable", "incomplete"):
            montage_ok = False
            reasons.append(f"recordings[{index}] montage state is unknown")
        rate = _finite(f"recordings[{index}].sampling_rate_hz", raw.get("sampling_rate_hz"))
        if rate is None or rate <= 0:
            rate_ok = False
            reasons.append(f"recordings[{index}] sampling_rate_hz is invalid")
        elif high_hz is not None and rate / 2.0 < high_hz:
            rate_ok = False
            reasons.append(
                f"recordings[{index}] Nyquist {rate / 2.0:g} Hz is below requested {high_hz:g} Hz"
            )
        channels = _finite(f"recordings[{index}].channel_count", raw.get("channel_count"))
        if channels is None or channels < min_channels:
            channels_ok = False
            reasons.append(f"recordings[{index}] channel_count is below {min_channels}")
        steps = [_text(item) for item in _as_list(raw.get("preprocessing_steps"))]
        if not any(steps):
            preprocessing_ok = False
            reasons.append(f"recordings[{index}] preprocessing is unrecorded")
        capability = _text(raw.get("container_capability") or raw.get("capability"))
        if capability == "missing_optional_dependency":
            missing_dep = _text(raw.get("optional_dependency")) or "mne"
            reasons.append(f"recordings[{index}] missing optional dependency {missing_dep}")
        if origin == "empirical_local" and exists and size_ok:
            empirical_ok += 1

    n_pairs, pair_reasons = _paired_subjects(
        [item for item in recordings if isinstance(item, Mapping)],
        cohort,
    )
    reasons.extend(pair_reasons)
    tda_recorded = bool(topology.get("recorded") or topology.get("engine") or topology.get("maxdim") is not None)
    if not tda_recorded:
        reasons.append("TDA configuration is unrecorded")
    nulls = [_text(item) for item in _as_list(statistics.get("null_controls"))]
    nulls_ok = any(nulls)
    if not nulls_ok:
        reasons.append("null-control configuration is unrecorded")
    mcp = _text(statistics.get("multiple_comparison_policy"))
    if not mcp:
        reasons.append("multiple-comparison policy is unrecorded")

    checks.extend(
        [
            CheckResult("files_exist", files_exist, "local paths exist" if files_exist else "one or more files missing"),
            CheckResult("files_readable", readable and files_exist, "non-empty local files" if readable and files_exist else "unreadable or empty files"),
            CheckResult("checksums_present", checksums, "checksums declared"),
            CheckResult("condition_labels_explicit", labels, "condition labels present"),
            CheckResult("paired_subjects_sufficient", n_pairs >= min_pairs, f"{n_pairs} paired subjects; {min_pairs} required"),
            CheckResult("sampling_rate_supports_band", rate_ok, "Nyquist supports requested band" if rate_ok else "sampling rate unsupported"),
            CheckResult("channel_count_sufficient", channels_ok, f"channel count >= {min_channels}"),
            CheckResult("montage_state_known", montage_ok, "montage recorded"),
            CheckResult("units_known", units_ok, "time, sampling_frequency, amplitude present"),
            CheckResult("origin_labeled", origin_ok and bool(origins), "origin labels recognized"),
            CheckResult("preprocessing_recorded", preprocessing_ok, "preprocessing steps recorded"),
            CheckResult("tda_configuration_recorded", tda_recorded, "TDA configuration recorded"),
            CheckResult("null_controls_recorded", nulls_ok, "null controls recorded"),
            CheckResult("multiple_comparison_policy_recorded", bool(mcp), "multiple-comparison policy recorded"),
        ]
    )

    descriptive = (
        files_exist and readable and checksums and labels and rate_ok and channels_ok
        and units_ok and montage_ok and empirical_ok > 0 and missing_dep is None
        and not invalid and not synthetic_only
    )
    paired = descriptive and n_pairs >= min_pairs
    formal = (
        paired and preprocessing_ok and tda_recorded and nulls_ok and bool(mcp)
        and origins.get("empirical_local", 0) == len(recordings)
    )

    if invalid or not files_exist or not readable:
        status = "INVALID_INPUT"
    elif missing_dep is not None:
        status = "MISSING_OPTIONAL_DEPENDENCY"
    elif synthetic_only or empirical_ok == 0:
        status = "SYNTHETIC_DEMO_ONLY"
    elif not rate_ok:
        status = "UNSUPPORTED_SAMPLING_RATE"
    elif not checksums or not labels or not units_ok or not montage_ok or not preprocessing_ok or not tda_recorded:
        status = "INCOMPLETE_PROVENANCE"
    elif n_pairs < min_pairs:
        status = "INSUFFICIENT_PAIRED_SUBJECTS"
    elif formal:
        status = "READY_FOR_FORMAL_EVIDENCE_REVIEW"
    elif paired:
        status = "READY_FOR_PAIRED_STATISTICS"
    elif descriptive:
        status = "READY_FOR_DESCRIPTIVE_ANALYSIS"
    else:
        status = "INCOMPLETE_PROVENANCE"

    if status.startswith("READY_") and origins.get("synthetic_demo"):
        status = "SYNTHETIC_DEMO_ONLY"
        descriptive = False
        paired = False
        formal = False
        reasons.append("synthetic recordings block READY states")

    return ReadinessReport(
        status=status,
        reasons=list(dict.fromkeys(reasons)),
        checks=checks,
        n_recordings=len(recordings),
        n_empirical_recordings=empirical_ok,
        n_paired_subjects=n_pairs,
        min_pairs_required=min_pairs,
        descriptive_ready=descriptive and status in READY_STATES,
        paired_ready=paired and status in {"READY_FOR_PAIRED_STATISTICS", "READY_FOR_FORMAL_EVIDENCE_REVIEW"},
        formal_evidence_eligible=formal and status == "READY_FOR_FORMAL_EVIDENCE_REVIEW",
        origin_summary=origins,
        missing_optional_dependency=missing_dep,
    )
