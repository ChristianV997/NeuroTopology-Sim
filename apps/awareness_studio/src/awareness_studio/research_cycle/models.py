"""Immutable typed records for the Awareness Studio research-cycle ledger.

This module is deliberately local-only.  Records are evidence-aware metadata,
not a replacement for ``RunRecordV1`` and not a mechanism for promoting claims.
"""

from __future__ import annotations

from dataclasses import dataclass, fields, field
from enum import Enum
import hashlib
import json
import math
import re
from collections.abc import Mapping, Sequence
from typing import Any, ClassVar, TypeVar


SCHEMA_VERSION = "awareness-studio-research-cycle.v1"
CHECKSUM_RE = re.compile(r"^[0-9a-f]{64}$")
ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")


class EvidenceClass(str, Enum):
    ENGINEERING_FACT = "engineering_fact"
    BENCHMARK_RESULT = "benchmark_result"
    SYNTHETIC_DEMONSTRATION = "synthetic_demonstration"
    DESCRIPTIVE_EMPIRICAL = "descriptive_empirical"
    PROXY_INFERENCE = "proxy_inference"
    FORMAL_STATISTICAL_EVIDENCE = "formal_statistical_evidence"
    HYPOTHESIS = "hypothesis"
    SPECULATION = "speculation"
    UNSUPPORTED_CLAIM = "unsupported_claim"


VALID_STATUSES = frozenset(
    {
        "PENDING",
        "IN_PROGRESS",
        "COMPLETED",
        "INCONCLUSIVE",
        "BLOCKED",
        "FAILED",
        "NOT_IMPLEMENTED",
        "REVIEW_REQUIRED",
        "FINALIZED",
    }
)


class ResearchCycleError(ValueError):
    """Malformed or scientifically ambiguous ledger input."""


def _plain(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_plain(item) for item in value]
    item = getattr(value, "item", None)
    if callable(item):
        return _plain(item())
    raise ResearchCycleError(f"unsupported value type: {type(value).__name__}")


def json_safe(value: Any) -> Any:
    """Convert values to JSON-safe primitives; non-finite values become null."""
    value = _plain(value)
    if isinstance(value, Mapping):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [json_safe(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def canonical_json(value: Any) -> str:
    return json.dumps(json_safe(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def stable_id(kind: str, value: Any) -> str:
    """Return a deterministic, collision-resistant identifier for a record."""
    kind = _text(kind, "kind")
    return f"{kind}:{sha256_json(value)[:32]}"


def _text(value: Any, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ResearchCycleError(f"{name} must be a non-empty string")
    return value.strip()


def _identifier(value: Any, name: str) -> str:
    value = _text(value, name)
    if not ID_RE.fullmatch(value):
        raise ResearchCycleError(f"{name} is not a valid stable identifier")
    return value


def _checksum(value: Any, name: str) -> str:
    value = _text(value, name).lower()
    if not CHECKSUM_RE.fullmatch(value):
        raise ResearchCycleError(f"{name} must be a SHA-256 hex digest")
    return value


def _strings(values: Any, name: str, *, required: bool = True) -> tuple[str, ...]:
    if values is None and not required:
        return ()
    if not isinstance(values, Sequence) or isinstance(values, (str, bytes, bytearray)):
        raise ResearchCycleError(f"{name} must be an array of strings")
    result = tuple(_text(item, name) for item in values)
    if required and not result:
        raise ResearchCycleError(f"{name} cannot be empty")
    if len(set(result)) != len(result):
        raise ResearchCycleError(f"{name} must not contain duplicates")
    return result


def _mapping(value: Any, name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ResearchCycleError(f"{name} must be an object")
    return dict(value)


def _validate_common(record: Any) -> None:
    record_id = record.record_id
    _identifier(record_id, "record_id")
    _identifier(record.cycle_id, "cycle_id")
    evidence = record.evidence_class.value if isinstance(record.evidence_class, Enum) else record.evidence_class
    if evidence not in {item.value for item in EvidenceClass}:
        raise ResearchCycleError(f"unknown evidence class: {evidence!r}")
    _text(record.claim_scope, "claim_scope")
    _strings(record.scientific_limitations, "scientific_limitations")
    _strings(record.parent_ids, "parent_ids", required=False)
    _strings(record.child_ids, "child_ids", required=False)
    status = _text(record.status, "status")
    if status not in VALID_STATUSES:
        raise ResearchCycleError(f"unknown status: {status!r}")
    if record.schema_version != SCHEMA_VERSION:
        raise ResearchCycleError(f"schema_version must be {SCHEMA_VERSION!r}")
    if isinstance(record, Claim) and record.evidence_class == EvidenceClass.PROXY_INFERENCE:
        lowered = record.statement.lower()
        if any(term in lowered for term in ("causal", "causation", "mechanism")):
            raise ResearchCycleError("proxy inference cannot be written as a causal or mechanistic claim")
    if isinstance(record, SourceSnapshot) and record.data_mode == "synthetic_demo":
        if record.evidence_class != EvidenceClass.SYNTHETIC_DEMONSTRATION:
            raise ResearchCycleError("synthetic data cannot become empirical evidence")
    if isinstance(record, SourceSnapshot) and record.data_mode == "empirical" and record.evidence_class == EvidenceClass.SYNTHETIC_DEMONSTRATION:
        raise ResearchCycleError("empirical data cannot be labeled synthetic")
    if isinstance(record, EvidenceRecord) and record.data_mode == "synthetic_demo":
        if record.evidence_class != EvidenceClass.SYNTHETIC_DEMONSTRATION:
            raise ResearchCycleError("synthetic data cannot become empirical evidence")
    if isinstance(record, EvidenceRecord) and record.data_mode == "empirical" and record.evidence_class == EvidenceClass.SYNTHETIC_DEMONSTRATION:
        raise ResearchCycleError("empirical data cannot be labeled synthetic")


class RecordMixin:
    record_type: ClassVar[str]

    @property
    def record_id(self) -> str:
        names = {
            "source_snapshot": "snapshot_id",
            "evidence_record": "evidence_id",
            "claim": "claim_id",
            "hypothesis": "hypothesis_id",
            "experiment_spec": "experiment_id",
            "run_record": "run_record_id",
            "artifact_manifest": "artifact_manifest_id",
            "validation_report": "validation_report_id",
            "theory_revision": "revision_id",
        }
        name = names.get(self.record_type)
        if name is None or not hasattr(self, name):
            raise ResearchCycleError("record has no stable identifier")
        return getattr(self, name)

    def to_dict(self, *, include_checksum: bool = True) -> dict[str, Any]:
        result = {"record_type": self.record_type}
        for item in fields(self):
            result[item.name] = json_safe(getattr(self, item.name))
        result["record_id"] = self.record_id
        if include_checksum:
            result["checksum"] = sha256_json(result)
        return result

    @property
    def checksum(self) -> str:
        return sha256_json(self.to_dict(include_checksum=False))


@dataclass(frozen=True)
class SourceSnapshot(RecordMixin):
    snapshot_id: str
    cycle_id: str
    source_uri: str
    source_sha256: str
    data_mode: str
    evidence_class: EvidenceClass
    claim_scope: str
    scientific_limitations: tuple[str, ...]
    source_format: str = "unknown"
    captured_at: str = ""
    parent_ids: tuple[str, ...] = ()
    child_ids: tuple[str, ...] = ()
    status: str = "COMPLETED"
    metadata: Mapping[str, Any] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION
    record_type: ClassVar[str] = "source_snapshot"

    def __post_init__(self) -> None:
        object.__setattr__(self, "parent_ids", _strings(self.parent_ids, "parent_ids", required=False))
        object.__setattr__(self, "child_ids", _strings(self.child_ids, "child_ids", required=False))
        object.__setattr__(self, "scientific_limitations", _strings(self.scientific_limitations, "scientific_limitations"))
        object.__setattr__(self, "evidence_class", EvidenceClass(self.evidence_class))
        object.__setattr__(self, "metadata", dict(_mapping(self.metadata, "metadata")))
        _identifier(self.snapshot_id, "snapshot_id")
        _text(self.source_uri, "source_uri")
        _checksum(self.source_sha256, "source_sha256")
        _text(self.data_mode, "data_mode")
        _validate_common(self)


@dataclass(frozen=True)
class EvidenceRecord(RecordMixin):
    evidence_id: str
    cycle_id: str
    source_snapshot_ids: tuple[str, ...]
    observation: str
    data_mode: str
    evidence_class: EvidenceClass
    claim_scope: str
    scientific_limitations: tuple[str, ...]
    metrics: Mapping[str, Any] = field(default_factory=dict)
    parent_ids: tuple[str, ...] = ()
    child_ids: tuple[str, ...] = ()
    status: str = "COMPLETED"
    schema_version: str = SCHEMA_VERSION
    record_type: ClassVar[str] = "evidence_record"

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_snapshot_ids", _strings(self.source_snapshot_ids, "source_snapshot_ids"))
        object.__setattr__(self, "parent_ids", _strings(self.parent_ids, "parent_ids", required=False))
        object.__setattr__(self, "child_ids", _strings(self.child_ids, "child_ids", required=False))
        object.__setattr__(self, "scientific_limitations", _strings(self.scientific_limitations, "scientific_limitations"))
        object.__setattr__(self, "evidence_class", EvidenceClass(self.evidence_class))
        object.__setattr__(self, "metrics", dict(_mapping(self.metrics, "metrics")))
        _identifier(self.evidence_id, "evidence_id")
        _text(self.observation, "observation")
        _text(self.data_mode, "data_mode")
        _validate_common(self)


@dataclass(frozen=True)
class Claim(RecordMixin):
    claim_id: str
    cycle_id: str
    statement: str
    evidence_ids: tuple[str, ...]
    evidence_class: EvidenceClass
    claim_scope: str
    scientific_limitations: tuple[str, ...]
    status: str = "REVIEW_REQUIRED"
    parent_ids: tuple[str, ...] = ()
    child_ids: tuple[str, ...] = ()
    schema_version: str = SCHEMA_VERSION
    record_type: ClassVar[str] = "claim"

    def __post_init__(self) -> None:
        object.__setattr__(self, "evidence_ids", _strings(self.evidence_ids, "evidence_ids"))
        object.__setattr__(self, "parent_ids", _strings(self.parent_ids, "parent_ids", required=False))
        object.__setattr__(self, "child_ids", _strings(self.child_ids, "child_ids", required=False))
        object.__setattr__(self, "scientific_limitations", _strings(self.scientific_limitations, "scientific_limitations"))
        object.__setattr__(self, "evidence_class", EvidenceClass(self.evidence_class))
        _identifier(self.claim_id, "claim_id")
        _text(self.statement, "statement")
        _validate_common(self)


@dataclass(frozen=True)
class Hypothesis(RecordMixin):
    hypothesis_id: str
    cycle_id: str
    statement: str
    claim_ids: tuple[str, ...]
    evidence_class: EvidenceClass = EvidenceClass.HYPOTHESIS
    claim_scope: str = ""
    scientific_limitations: tuple[str, ...] = ("A hypothesis is not evidence until independently tested.",)
    status: str = "PENDING"
    parent_ids: tuple[str, ...] = ()
    child_ids: tuple[str, ...] = ()
    schema_version: str = SCHEMA_VERSION
    record_type: ClassVar[str] = "hypothesis"

    def __post_init__(self) -> None:
        object.__setattr__(self, "claim_ids", _strings(self.claim_ids, "claim_ids"))
        object.__setattr__(self, "parent_ids", _strings(self.parent_ids, "parent_ids", required=False))
        object.__setattr__(self, "child_ids", _strings(self.child_ids, "child_ids", required=False))
        object.__setattr__(self, "scientific_limitations", _strings(self.scientific_limitations, "scientific_limitations"))
        object.__setattr__(self, "evidence_class", EvidenceClass(self.evidence_class))
        _identifier(self.hypothesis_id, "hypothesis_id")
        _text(self.statement, "statement")
        _validate_common(self)


@dataclass(frozen=True)
class ExperimentSpec(RecordMixin):
    experiment_id: str
    cycle_id: str
    hypothesis_ids: tuple[str, ...]
    method: str
    parameters: Mapping[str, Any]
    evidence_class: EvidenceClass = EvidenceClass.ENGINEERING_FACT
    claim_scope: str = "Method specification only; not an outcome."
    scientific_limitations: tuple[str, ...] = ("A method specification does not establish its result.",)
    status: str = "PENDING"
    parent_ids: tuple[str, ...] = ()
    child_ids: tuple[str, ...] = ()
    schema_version: str = SCHEMA_VERSION
    record_type: ClassVar[str] = "experiment_spec"

    def __post_init__(self) -> None:
        object.__setattr__(self, "hypothesis_ids", _strings(self.hypothesis_ids, "hypothesis_ids"))
        object.__setattr__(self, "parent_ids", _strings(self.parent_ids, "parent_ids", required=False))
        object.__setattr__(self, "child_ids", _strings(self.child_ids, "child_ids", required=False))
        object.__setattr__(self, "scientific_limitations", _strings(self.scientific_limitations, "scientific_limitations"))
        object.__setattr__(self, "evidence_class", EvidenceClass(self.evidence_class))
        object.__setattr__(self, "parameters", dict(_mapping(self.parameters, "parameters")))
        _identifier(self.experiment_id, "experiment_id")
        _text(self.method, "method")
        _validate_common(self)


@dataclass(frozen=True)
class RunRecordLink(RecordMixin):
    run_record_id: str
    cycle_id: str
    experiment_id: str
    run_record_schema_version: str
    run_record_sha256: str
    run_status: str
    evidence_class: EvidenceClass
    claim_scope: str
    scientific_limitations: tuple[str, ...]
    status: str = "COMPLETED"
    parent_ids: tuple[str, ...] = ()
    child_ids: tuple[str, ...] = ()
    schema_version: str = SCHEMA_VERSION
    record_type: ClassVar[str] = "run_record"

    def __post_init__(self) -> None:
        object.__setattr__(self, "parent_ids", _strings(self.parent_ids, "parent_ids", required=False))
        object.__setattr__(self, "child_ids", _strings(self.child_ids, "child_ids", required=False))
        object.__setattr__(self, "scientific_limitations", _strings(self.scientific_limitations, "scientific_limitations"))
        object.__setattr__(self, "evidence_class", EvidenceClass(self.evidence_class))
        _identifier(self.run_record_id, "run_record_id")
        _identifier(self.experiment_id, "experiment_id")
        _text(self.run_record_schema_version, "run_record_schema_version")
        _checksum(self.run_record_sha256, "run_record_sha256")
        _text(self.run_status, "run_status")
        _validate_common(self)


@dataclass(frozen=True)
class ArtifactManifest(RecordMixin):
    artifact_manifest_id: str
    cycle_id: str
    run_record_id: str
    artifacts: Mapping[str, Mapping[str, Any]]
    evidence_class: EvidenceClass
    claim_scope: str
    scientific_limitations: tuple[str, ...]
    status: str = "COMPLETED"
    parent_ids: tuple[str, ...] = ()
    child_ids: tuple[str, ...] = ()
    schema_version: str = SCHEMA_VERSION
    record_type: ClassVar[str] = "artifact_manifest"

    def __post_init__(self) -> None:
        object.__setattr__(self, "parent_ids", _strings(self.parent_ids, "parent_ids", required=False))
        object.__setattr__(self, "child_ids", _strings(self.child_ids, "child_ids", required=False))
        object.__setattr__(self, "scientific_limitations", _strings(self.scientific_limitations, "scientific_limitations"))
        object.__setattr__(self, "evidence_class", EvidenceClass(self.evidence_class))
        object.__setattr__(self, "artifacts", {str(k): dict(_mapping(v, "artifact")) for k, v in _mapping(self.artifacts, "artifacts").items()})
        _identifier(self.artifact_manifest_id, "artifact_manifest_id")
        _identifier(self.run_record_id, "run_record_id")
        _validate_common(self)


@dataclass(frozen=True)
class ValidationReport(RecordMixin):
    validation_report_id: str
    cycle_id: str
    artifact_manifest_ids: tuple[str, ...]
    run_record_id: str
    validation_status: str
    checks: Mapping[str, Any]
    evidence_class: EvidenceClass
    claim_scope: str
    scientific_limitations: tuple[str, ...]
    status: str = "REVIEW_REQUIRED"
    parent_ids: tuple[str, ...] = ()
    child_ids: tuple[str, ...] = ()
    schema_version: str = SCHEMA_VERSION
    record_type: ClassVar[str] = "validation_report"

    def __post_init__(self) -> None:
        object.__setattr__(self, "artifact_manifest_ids", _strings(self.artifact_manifest_ids, "artifact_manifest_ids"))
        object.__setattr__(self, "parent_ids", _strings(self.parent_ids, "parent_ids", required=False))
        object.__setattr__(self, "child_ids", _strings(self.child_ids, "child_ids", required=False))
        object.__setattr__(self, "scientific_limitations", _strings(self.scientific_limitations, "scientific_limitations"))
        object.__setattr__(self, "evidence_class", EvidenceClass(self.evidence_class))
        object.__setattr__(self, "checks", dict(_mapping(self.checks, "checks")))
        _identifier(self.validation_report_id, "validation_report_id")
        _identifier(self.run_record_id, "run_record_id")
        _text(self.validation_status, "validation_status")
        _validate_common(self)


@dataclass(frozen=True)
class TheoryRevision(RecordMixin):
    revision_id: str
    cycle_id: str
    hypothesis_ids: tuple[str, ...]
    validation_report_ids: tuple[str, ...]
    revision_summary: str
    evidence_class: EvidenceClass
    claim_scope: str
    scientific_limitations: tuple[str, ...]
    status: str = "REVIEW_REQUIRED"
    parent_ids: tuple[str, ...] = ()
    child_ids: tuple[str, ...] = ()
    schema_version: str = SCHEMA_VERSION
    record_type: ClassVar[str] = "theory_revision"

    def __post_init__(self) -> None:
        object.__setattr__(self, "hypothesis_ids", _strings(self.hypothesis_ids, "hypothesis_ids"))
        object.__setattr__(self, "validation_report_ids", _strings(self.validation_report_ids, "validation_report_ids"))
        object.__setattr__(self, "parent_ids", _strings(self.parent_ids, "parent_ids", required=False))
        object.__setattr__(self, "child_ids", _strings(self.child_ids, "child_ids", required=False))
        object.__setattr__(self, "scientific_limitations", _strings(self.scientific_limitations, "scientific_limitations"))
        object.__setattr__(self, "evidence_class", EvidenceClass(self.evidence_class))
        _identifier(self.revision_id, "revision_id")
        _text(self.revision_summary, "revision_summary")
        _validate_common(self)


# These names describe references to the canonical runs/run_record.py contract;
# they intentionally do not define or replace RunRecordV1.
RunRecordReference = RunRecordLink
RunRecordRef = RunRecordLink


RECORD_TYPES = {
    SourceSnapshot.record_type: SourceSnapshot,
    EvidenceRecord.record_type: EvidenceRecord,
    Claim.record_type: Claim,
    Hypothesis.record_type: Hypothesis,
    ExperimentSpec.record_type: ExperimentSpec,
    RunRecordLink.record_type: RunRecordLink,
    ArtifactManifest.record_type: ArtifactManifest,
    ValidationReport.record_type: ValidationReport,
    TheoryRevision.record_type: TheoryRevision,
}
Record = TypeVar("Record", bound=RecordMixin)


def record_from_dict(value: Mapping[str, Any]) -> RecordMixin:
    """Rehydrate one typed record and verify its serialized checksum."""
    data = dict(value)
    record_type = data.pop("record_type", None)
    checksum = data.pop("checksum", None)
    if record_type not in RECORD_TYPES:
        raise ResearchCycleError(f"unknown record_type: {record_type!r}")
    if not isinstance(checksum, str) or checksum != sha256_json({"record_type": record_type, **data}):
        raise ResearchCycleError("record checksum is missing or invalid")
    cls = RECORD_TYPES[record_type]
    id_fields = {
        "source_snapshot": "snapshot_id", "evidence_record": "evidence_id", "claim": "claim_id",
        "hypothesis": "hypothesis_id", "experiment_spec": "experiment_id", "run_record": "run_record_id",
        "artifact_manifest": "artifact_manifest_id", "validation_report": "validation_report_id", "theory_revision": "revision_id",
    }
    if data.get("record_id") != data.get(id_fields[record_type]):
        raise ResearchCycleError("record_id does not match the typed record identifier")
    data.pop("record_id", None)
    names = {item.name for item in fields(cls)}
    data = {key: item for key, item in data.items() if key in names}
    if "evidence_class" in data:
        data["evidence_class"] = EvidenceClass(data["evidence_class"])
    for name in ("parent_ids", "child_ids", "source_snapshot_ids", "evidence_ids", "claim_ids", "hypothesis_ids", "artifact_manifest_ids", "validation_report_ids"):
        if name in data and isinstance(data[name], list):
            data[name] = tuple(data[name])
    return cls(**data)


__all__ = [
    "ADAPTER_VERSION", "ArtifactManifest", "Claim", "EvidenceClass", "EvidenceRecord",
    "ExperimentSpec", "FEATURE_SCHEMA_VERSION", "Hypothesis", "Record", "RecordMixin",
    "ResearchCycleError", "RunRecordLink", "RunRecordReference", "RunRecordRef", "SCHEMA_VERSION", "SourceSnapshot",
    "TheoryRevision", "ValidationReport", "VALID_STATUSES", "canonical_json", "json_safe",
    "record_from_dict", "sha256_json", "stable_id",
]
