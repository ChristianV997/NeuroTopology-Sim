"""Fixture-only research-cycle contract consumer.

Inspects versioned JSON stage files. Does not execute solvers, download data,
or call the network. Missing Batch 1 producers are represented by fixtures;
this module only reads and checks declared contracts.
"""
from __future__ import annotations

import ast
import hashlib
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from .contracts import (
    COMPLETE_STATUSES,
    DATA_MODES,
    PIPELINE_COMPATIBLE,
    STAGE_ORDER,
    STATUSES,
    compatible_versions,
    envelope_field_errors,
    is_scientific_pass,
    parent_stage,
    version_is_compatible,
)

NONFINITE_TOKENS = frozenset({"NaN", "Infinity", "-Infinity", "+Infinity", "Inf", "-Inf", "+Inf", "nan", "inf"})
SOLVER_MODULES = frozenset(
    {
        "numpy",
        "scipy",
        "sklearn",
        "mne",
        "torch",
        "ripser",
        "gudhi",
        "networkx",
        "nilearn",
        "pandas",
    }
)
NETWORK_MODULES = frozenset({"socket", "requests", "urllib", "http", "httplib", "httpx", "aiohttp"})


class ContractError(ValueError):
    """Raised when a consumer must reject a stage document."""


@dataclass
class StageDocument:
    path: str
    stage: str
    record_id: str
    schema_version: str
    checksum: str
    expected_checksum: str
    parent_ids: list[str]
    parent_checksums: list[str]
    data_mode: str
    evidence_class: str
    claim_scope: str
    status: str
    scientific_verdict: Any
    payload: dict[str, Any]
    diagnostics: dict[str, list[str]]
    raw: dict[str, Any]


@dataclass
class InspectionReport:
    status: str
    documents: list[StageDocument] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    missing_artifacts: list[str] = field(default_factory=list)
    duplicate_record_ids: list[str] = field(default_factory=list)
    duplicate_checksums: list[dict[str, Any]] = field(default_factory=list)
    incompatible_versions: list[str] = field(default_factory=list)
    label_mutations: list[str] = field(default_factory=list)
    blocked_claims: list[str] = field(default_factory=list)
    upstream_failures: list[str] = field(default_factory=list)
    solver_executed: bool = False
    network_accessed: bool = False
    finite_json: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "record_ids": [doc.record_id for doc in self.documents],
            "stages": [doc.stage for doc in self.documents],
            "errors": list(self.errors),
            "missing_artifacts": list(self.missing_artifacts),
            "duplicate_record_ids": list(self.duplicate_record_ids),
            "duplicate_checksums": list(self.duplicate_checksums),
            "incompatible_versions": list(self.incompatible_versions),
            "label_mutations": list(self.label_mutations),
            "blocked_claims": list(self.blocked_claims),
            "upstream_failures": list(self.upstream_failures),
            "solver_executed": self.solver_executed,
            "network_accessed": self.network_accessed,
            "finite_json": self.finite_json,
        }


def normalize_path(value: str) -> str:
    """Accept Windows or POSIX path forms; compare as POSIX relative paths."""
    text = str(value).strip().replace("\\", "/")
    while "//" in text:
        text = text.replace("//", "/")
    if len(text) >= 2 and text[1] == ":":
        text = text[2:]
        if text.startswith("/"):
            text = text[1:]
    return text.lstrip("/")


def canonical_checksum(document: Mapping[str, Any]) -> str:
    canonical = {str(key): document[key] for key in document if key != "checksum"}
    payload = json.dumps(
        canonical,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def stamp_checksum(document: dict[str, Any]) -> dict[str, Any]:
    stamped = dict(document)
    stamped["checksum"] = canonical_checksum(stamped)
    return stamped


def dumps_finite(value: Any, *, indent: int = 2) -> str:
    return json.dumps(_finite_value(value), sort_keys=True, indent=indent, allow_nan=False) + "\n"


def _finite_value(value: Any, path: str = "$") -> Any:
    if value is None or isinstance(value, (str, bool)):
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ContractError(f"{path} contains a non-finite number")
        return value
    if isinstance(value, Path):
        return normalize_path(str(value))
    if isinstance(value, Mapping):
        return {str(key): _finite_value(item, f"{path}.{key}") for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_finite_value(item, f"{path}[{index}]") for index, item in enumerate(value)]
    raise ContractError(f"{path} is not JSON-serializable ({type(value).__name__})")


def _reject_nonfinite_constant(token: str) -> Any:
    raise ContractError(f"non-finite JSON token {token!r} is rejected")


def load_json_file(path: str | Path) -> dict[str, Any]:
    raw_path = Path(path)
    text = raw_path.read_text(encoding="utf-8")
    lowered = text.lower()
    for token in ("nan", "infinity", "+infinity", "-infinity"):
        # Token-level guard so Python's default JSON parser cannot quietly coerce.
        if token in lowered.split():
            raise ContractError(f"{raw_path.name} contains non-finite token {token!r}")
    try:
        loaded = json.loads(text, parse_constant=_reject_nonfinite_constant)
    except json.JSONDecodeError as exc:
        raise ContractError(f"invalid JSON in {raw_path.name}: {exc}") from exc
    if not isinstance(loaded, dict):
        raise ContractError(f"{raw_path.name} root must be a JSON object")
    return loaded


def parse_stage_document(path: str | Path, document: Mapping[str, Any] | None = None) -> StageDocument:
    raw_path = Path(path)
    raw = dict(document) if document is not None else load_json_file(raw_path)
    field_errors = envelope_field_errors(raw)
    if field_errors:
        raise ContractError("; ".join(field_errors))

    stage = str(raw["stage"])
    if stage not in STAGE_ORDER:
        raise ContractError(f"unknown stage {stage!r}")

    schema_version = str(raw.get("schema_version") or "")
    pipeline_contract = str(raw.get("pipeline_contract") or "")
    if pipeline_contract not in PIPELINE_COMPATIBLE:
        raise ContractError(
            f"incompatible pipeline_contract {pipeline_contract!r}; "
            f"consumer accepts {sorted(PIPELINE_COMPATIBLE)}"
        )
    if not version_is_compatible(stage, schema_version):
        raise ContractError(
            f"incompatible schema_version {schema_version!r} for stage {stage}; "
            f"consumer accepts {sorted(compatible_versions(stage))}"
        )

    status = str(raw["status"])
    if status not in STATUSES:
        raise ContractError(f"unknown status {status!r}")

    data_mode = str(raw["data_mode"])
    if data_mode not in DATA_MODES:
        raise ContractError(f"unknown data_mode {data_mode!r}")

    payload = raw["payload"]
    if not isinstance(payload, Mapping):
        raise ContractError("payload must be a JSON object")

    diagnostics = raw.get("diagnostics") or {}
    if not isinstance(diagnostics, Mapping):
        raise ContractError("diagnostics must be a JSON object")
    normalized_diagnostics = {
        key: list(value) if isinstance(value, list) else [str(value)]
        for key, value in diagnostics.items()
    }

    expected = canonical_checksum(raw)
    reported = str(raw.get("checksum") or "")
    if reported != expected:
        raise ContractError(
            f"checksum mismatch for {raw.get('record_id')!r}: "
            f"reported {reported} != expected {expected}"
        )

    return StageDocument(
        path=normalize_path(str(raw_path)),
        stage=stage,
        record_id=str(raw["record_id"]),
        schema_version=schema_version,
        checksum=reported,
        expected_checksum=expected,
        parent_ids=[str(item) for item in raw.get("parent_ids") or []],
        parent_checksums=[str(item) for item in raw.get("parent_checksums") or []],
        data_mode=data_mode,
        evidence_class=str(raw["evidence_class"]),
        claim_scope=str(raw["claim_scope"]),
        status=status,
        scientific_verdict=raw.get("scientific_verdict"),
        payload=dict(payload),
        diagnostics=normalized_diagnostics,
        raw=dict(raw),
    )


def discover_stage_files(root: str | Path) -> list[Path]:
    root_path = Path(root)
    files = [
        path
        for path in root_path.rglob("*.json")
        if path.is_file()
    ]
    return sorted(files, key=lambda item: normalize_path(str(item.relative_to(root_path))))


def _collect_paths(value: Any) -> list[str]:
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            key_l = str(key).lower()
            if key_l in {"path", "relative_path", "artifact_path", "local_root"} and isinstance(item, str):
                found.append(item)
            elif key_l in {"paths", "artifacts", "missing", "missing_artifacts"}:
                found.extend(_collect_paths(item))
            else:
                found.extend(_collect_paths(item))
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, str) and ("/" in item or "\\" in item or item.endswith(".json")):
                found.append(item)
            else:
                found.extend(_collect_paths(item))
    return found


def _duplicate_record_ids(documents: Iterable[StageDocument]) -> list[str]:
    seen: dict[str, int] = {}
    for doc in documents:
        seen[doc.record_id] = seen.get(doc.record_id, 0) + 1
    return sorted(record_id for record_id, count in seen.items() if count > 1)


def inspect_directory(root: str | Path, *, artifact_root: str | Path | None = None) -> InspectionReport:
    """Consume a directory of stage files. Never runs a solver or touches the network."""
    report = InspectionReport(status="COMPLETE")
    root_path = Path(root)
    files = discover_stage_files(root_path)
    parsed: list[StageDocument] = []
    rejected: list[str] = []

    for path in files:
        try:
            parsed.append(parse_stage_document(path))
        except ContractError as exc:
            rejected.append(f"{path.name}: {exc}")
            message = str(exc)
            if "incompatible" in message:
                report.incompatible_versions.append(message)
            if "non-finite" in message:
                report.finite_json = False
            report.errors.append(message)

    report.documents = parsed
    report.duplicate_record_ids = _duplicate_record_ids(parsed)
    if report.duplicate_record_ids:
        report.errors.append(
            "duplicate records detected: " + ", ".join(report.duplicate_record_ids)
        )

    checksum_index: dict[str, list[str]] = {}
    for doc in parsed:
        checksum_index.setdefault(doc.checksum, []).append(doc.record_id)
    report.duplicate_checksums = [
        {"checksum": digest, "record_ids": ids}
        for digest, ids in sorted(checksum_index.items())
        if len(ids) > 1
    ]

    by_id = {doc.record_id: doc for doc in parsed}
    by_stage: dict[str, list[StageDocument]] = {}
    for doc in parsed:
        by_stage.setdefault(doc.stage, []).append(doc)

    for doc in parsed:
        expected_parent = parent_stage(doc.stage)
        if expected_parent is None:
            continue
        if not doc.parent_ids:
            report.errors.append(
                f"{doc.record_id}: provenance missing; parent stage {expected_parent} is not linked"
            )
            continue
        for parent_id, parent_checksum in zip(doc.parent_ids, doc.parent_checksums or [""] * len(doc.parent_ids)):
            parent = by_id.get(parent_id)
            if parent is None:
                report.errors.append(
                    f"{doc.record_id}: parent {parent_id!r} is not present (missing provenance ≠ evidence)"
                )
                continue
            if parent.checksum != parent_checksum:
                report.errors.append(
                    f"{doc.record_id}: parent checksum {parent_checksum} does not match {parent.checksum}"
                )
            if parent.stage != expected_parent and parent.stage not in STAGE_ORDER:
                report.errors.append(
                    f"{doc.record_id}: parent stage {parent.stage!r} is not the declared predecessor"
                )
            if parent.data_mode != doc.data_mode:
                report.label_mutations.append(
                    f"{doc.record_id}: data_mode mutated {parent.data_mode!r} -> {doc.data_mode!r}"
                )
            if (
                parent.evidence_class == "synthetic_demo_only"
                and doc.evidence_class not in {"synthetic_demo_only", "research_plan_audit", "performance_only"}
            ):
                report.label_mutations.append(
                    f"{doc.record_id}: synthetic evidence_class mutated to {doc.evidence_class!r}"
                )
            if parent.status in {"PARTIAL", "FAILED", "BLOCKED", "INCOMPLETE"} and doc.status in COMPLETE_STATUSES:
                report.upstream_failures.append(
                    f"{doc.record_id} claimed COMPLETE while upstream {parent.record_id} is {parent.status}"
                )

        if doc.data_mode in {"synthetic", "proxy"} and is_scientific_pass(doc.scientific_verdict):
            report.blocked_claims.append(
                f"{doc.record_id}: scientific PASS is forbidden for {doc.data_mode} fixtures"
            )
        if doc.data_mode == "synthetic" and str(doc.payload.get("origin") or doc.data_mode) == "empirical":
            report.blocked_claims.append(
                f"{doc.record_id}: synthetic origin silently relabeled empirical"
            )
        if doc.payload.get("data_type") == "proxy_bayes_factor" and is_scientific_pass(doc.scientific_verdict):
            report.blocked_claims.append(
                f"{doc.record_id}: proxy K treated as formal Bayes PASS"
            )

        artifact_base = Path(artifact_root) if artifact_root is not None else root_path
        check_artifacts = bool(doc.payload.get("check_artifacts"))
        for raw_path in _collect_paths(doc.payload.get("artifacts") or []):
            if len(raw_path) >= 2 and raw_path[1] == ":":
                continue
            normalized = normalize_path(raw_path)
            candidate = artifact_base / normalized
            if check_artifacts and not candidate.is_file():
                report.missing_artifacts.append(normalized)
                if doc.status in COMPLETE_STATUSES:
                    report.errors.append(
                        f"{doc.record_id}: artifact {normalized!r} is missing"
                    )

        declared_missing = doc.diagnostics.get("missing") or doc.payload.get("missing_artifacts") or []
        for item in declared_missing:
            report.missing_artifacts.append(normalize_path(str(item)))

        if doc.status in {"FAILED", "PARTIAL", "BLOCKED"}:
            report.upstream_failures.append(f"{doc.record_id}:{doc.status}")

    if report.blocked_claims:
        report.errors.extend(report.blocked_claims)
    if report.label_mutations:
        report.errors.extend(report.label_mutations)
    if report.upstream_failures:
        # Failed/partial upstream is diagnosable, not a silent COMPLETE chain.
        complete_downstream = [
            doc.record_id
            for doc in parsed
            if doc.status in COMPLETE_STATUSES
            and any(
                parent_id in {item.split(":")[0] for item in report.upstream_failures}
                for parent_id in doc.parent_ids
            )
        ]
        for record_id in complete_downstream:
            report.errors.append(
                f"{record_id}: downstream COMPLETE after failed/partial upstream is not diagnosable"
            )

    if rejected or report.errors or report.incompatible_versions:
        if any("incompatible" in item for item in report.incompatible_versions):
            report.status = "BLOCKED"
        elif any(doc.status == "FAILED" for doc in parsed):
            report.status = "FAILED"
        elif any(doc.status == "PARTIAL" for doc in parsed):
            report.status = "PARTIAL"
        elif report.missing_artifacts:
            report.status = "INCOMPLETE"
        else:
            report.status = "BLOCKED"
    elif any(doc.status == "PARTIAL" for doc in parsed):
        report.status = "PARTIAL"
    elif any(doc.status == "FAILED" for doc in parsed):
        report.status = "FAILED"
    elif any(doc.status in {"INCOMPLETE", "PENDING"} for doc in parsed):
        report.status = "INCOMPLETE"
    else:
        report.status = "COMPLETE"

    report.solver_executed = False
    report.network_accessed = False
    return report


def imported_module_roots(source: str) -> set[str]:
    tree = ast.parse(source)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module.split(".")[0])
    return names


def owned_python_files() -> list[Path]:
    return sorted(
        path
        for path in Path(__file__).resolve().parent.glob("*.py")
        if path.name != "__init__.py" and not path.name.startswith("test_")
    )


def scan_owned_imports() -> dict[str, list[str]]:
    hits: dict[str, list[str]] = {"solver": [], "network": []}
    for path in owned_python_files():
        names = imported_module_roots(path.read_text(encoding="utf-8"))
        for name in sorted(names & SOLVER_MODULES):
            hits["solver"].append(f"{path.name}:{name}")
        for name in sorted(names & NETWORK_MODULES):
            hits["network"].append(f"{path.name}:{name}")
    return hits


def write_document(path: str | Path, document: Mapping[str, Any]) -> Path:
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    stamped = stamp_checksum(dict(document))
    out.write_text(dumps_finite(stamped), encoding="utf-8")
    return out
