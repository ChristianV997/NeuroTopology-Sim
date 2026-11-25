"""Read-only loaders for local promotion-gate artifacts.

Parses RunRecords, claim-gate JSON, RAG Markdown, command-center JSON,
Airtable-shaped cards, research-cycle snapshots, and literature records.
Never writes production artifacts and never contacts a network.
"""

from __future__ import annotations

import ast
import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from tools.evidence_promotion_gate.fingerprints import fingerprint_files
from tools.evidence_promotion_gate.schema import ARTIFACT_KINDS, SYNTHETIC_TOKENS
from tools.research_claim_gate.gate import CLAIM_CLASSES

_JSON_SUFFIXES = {".json", ".jsonl"}
_TEXT_SUFFIXES = {".md", ".markdown"}


class AdapterError(ValueError):
    """Raised when a local input cannot be represented safely."""


def _finite(value: Any, path: str = "$") -> None:
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise AdapterError(f"non-finite value at {path}")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            _finite(item, f"{path}.{key}")
        return
    if isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _finite(item, f"{path}[{index}]")
        return
    raise AdapterError(f"unsupported value type at {path}: {type(value).__name__}")


def load_json(path: Path) -> Any:
    text = path.read_text(encoding="utf-8")
    payload = json.loads(text)
    _finite(payload)
    return payload


def parse_markdown_frontmatter(text: str) -> dict[str, Any]:
    if not text.lstrip().startswith("---"):
        return {}
    stripped = text.lstrip()
    parts = stripped.split("---", 2)
    if len(parts) < 3:
        return {}
    fields: dict[str, Any] = {}
    for line in parts[1].splitlines():
        line = line.strip()
        if not line or ":" not in line:
            continue
        key, raw = line.split(":", 1)
        value = raw.strip()
        try:
            parsed = ast.literal_eval(value)
        except (SyntaxError, ValueError):
            parsed = value
        fields[key.strip()] = parsed
    _finite(fields, "$.frontmatter")
    return fields


def _lower(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return "true" if value else "false"
    text = str(value).strip()
    return text.lower() if text else None


def _first_present(mapping: dict[str, Any], keys: tuple[str, ...]) -> Any:
    for key in keys:
        if key in mapping and mapping[key] not in (None, ""):
            return mapping[key]
    return None


def classify_payload(payload: Any, *, filename: str = "") -> str:
    name = filename.lower()
    if name.endswith(".md") or name.endswith(".markdown"):
        return "rag_markdown"
    if not isinstance(payload, dict):
        return "unknown"
    if "decision" in payload and str(payload.get("schema_version", "")).endswith("ResearchClaimGate.v1"):
        return "claim_gate_result"
    if isinstance(payload.get("decision"), str) and str(payload["decision"]).startswith("CLAIM_"):
        return "claim_gate_result"
    if "claim_id" in payload and ("text" in payload or "claim" in payload):
        return "claim"
    if "run_id" in payload and ("run_kind" in payload or "schema_version" in payload):
        return "run_record"
    if "claim_kind" in payload or "publication_type" in payload or "identifier_type" in payload:
        return "literature"
    if "fields" in payload and isinstance(payload.get("fields"), dict):
        return "airtable_card"
    if "experiment_status" in payload or "cycle_id" in payload or payload.get("record_type") in {
        "research_cycle",
        "RunRecordLink",
        "SourceSnapshot",
    }:
        return "research_cycle"
    if "schema_version" in payload and "command-center" in str(payload.get("schema_version", "")).lower():
        return "command_center"
    if any(token in name for token in ("command_center", "command-center")):
        return "command_center"
    if "airtable" in name:
        return "airtable_card"
    if "literature" in name:
        return "literature"
    if "claim_gate" in name:
        return "claim_gate_result"
    if "runrecord" in name.replace("_", "").replace("-", ""):
        return "run_record"
    return "unknown"


@dataclass
class ParsedArtifact:
    kind: str
    path: Path
    payload: Any
    verdict: str | None = None
    evidence_class: str | None = None
    data_mode: str | None = None
    evidence_method: str | None = None
    claim_kind: str | None = None
    claim_class: str | None = None
    n_tests: int | None = None
    multiplicity_correction: str | None = None
    null_controls: tuple[str, ...] = ()
    provenance: dict[str, Any] | None = None
    synthetic_flag: bool | None = None
    network_access_requested: bool = False
    proxy_status: str | None = None
    declared_k: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "path": str(self.path),
            "verdict": self.verdict,
            "evidence_class": self.evidence_class,
            "data_mode": self.data_mode,
            "evidence_method": self.evidence_method,
            "claim_kind": self.claim_kind,
            "claim_class": self.claim_class,
            "n_tests": self.n_tests,
            "multiplicity_correction": self.multiplicity_correction,
            "null_controls": list(self.null_controls),
            "synthetic_flag": self.synthetic_flag,
            "network_access_requested": self.network_access_requested,
            "proxy_status": self.proxy_status,
            "declared_k": self.declared_k,
        }


def _as_controls(value: Any) -> tuple[str, ...]:
    if value is None or value is False:
        return ()
    if isinstance(value, str):
        return (value,) if value.strip() else ()
    if isinstance(value, dict):
        return tuple(str(key) for key, item in value.items() if item not in (None, False, ""))
    if isinstance(value, (list, tuple)):
        return tuple(str(item) for item in value if str(item).strip())
    return ()


def _as_int(value: Any) -> int | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _as_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        number = float(value)
        return number if math.isfinite(number) else None
    return None


def extract_fields(kind: str, payload: Any) -> dict[str, Any]:
    data = payload if isinstance(payload, dict) else {}
    nested = data.get("fields") if isinstance(data.get("fields"), dict) else {}
    merged = {**nested, **data}

    verdict = _first_present(merged, ("verdict", "Verdict", "status"))
    evidence_class = _first_present(
        merged,
        ("evidence_class", "Evidence Class", "evidenceClass", "declared_evidence_class"),
    )
    data_mode = _first_present(merged, ("data_mode", "dataMode", "empirical_synthetic_status"))
    evidence_method = _first_present(merged, ("evidence_method", "likelihood_method", "method"))
    claim_kind = _first_present(merged, ("claim_kind", "claimKind"))
    claim_class = _first_present(merged, ("claim_class", "claim_type", "claim_category"))
    n_tests = _as_int(_first_present(merged, ("n_tests", "number_of_tests")))
    multiplicity = _first_present(
        merged, ("multiplicity_correction", "multiplicity_status", "multiple_comparison_correction")
    )
    controls = _as_controls(_first_present(merged, ("null_controls", "controls", "null_control_status")))
    provenance = merged.get("provenance") if isinstance(merged.get("provenance"), dict) else None
    synthetic_flag = merged.get("synthetic") if isinstance(merged.get("synthetic"), bool) else None
    if synthetic_flag is None and isinstance(merged.get("synthetic_demo"), bool):
        synthetic_flag = merged["synthetic_demo"]
    network = merged.get("network_access_requested") is True
    proxy_status = _first_present(merged, ("proxy_status", "proxy_formal_status"))
    declared_k = _as_float(
        _first_present(
            merged,
            ("formal_bayes_factor", "declared_formal_bayes_factor", "k_value", "bayes_factor"),
        )
    )
    if kind == "claim_gate_result":
        evidence_class = evidence_class or data.get("evidence_class")
        data_mode = data_mode or data.get("data_mode")
    return {
        "verdict": str(verdict) if verdict is not None else None,
        "evidence_class": str(evidence_class) if evidence_class is not None else None,
        "data_mode": str(data_mode) if data_mode is not None else None,
        "evidence_method": str(evidence_method) if evidence_method is not None else None,
        "claim_kind": str(claim_kind) if claim_kind is not None else None,
        "claim_class": str(claim_class) if claim_class is not None else None,
        "n_tests": n_tests,
        "multiplicity_correction": str(multiplicity) if multiplicity is not None else None,
        "null_controls": controls,
        "provenance": provenance,
        "synthetic_flag": synthetic_flag,
        "network_access_requested": network,
        "proxy_status": str(proxy_status) if proxy_status is not None else None,
        "declared_k": declared_k,
    }


def parse_artifact(path: Path) -> ParsedArtifact:
    suffix = path.suffix.lower()
    if suffix in _TEXT_SUFFIXES:
        text = path.read_text(encoding="utf-8")
        payload = parse_markdown_frontmatter(text)
        payload.setdefault("_markdown_body", text)
        kind = "rag_markdown"
    elif suffix in _JSON_SUFFIXES:
        payload = load_json(path)
        kind = classify_payload(payload, filename=path.name)
    else:
        raise AdapterError(f"unsupported input suffix: {path.suffix}")
    if kind not in ARTIFACT_KINDS:
        kind = "unknown"
    fields = extract_fields(kind, payload)
    return ParsedArtifact(kind=kind, path=path, payload=payload, **fields)


@dataclass
class LoadedCase:
    case_id: str
    root: Path
    artifacts: list[ParsedArtifact] = field(default_factory=list)
    load_errors: list[str] = field(default_factory=list)

    @property
    def paths(self) -> list[Path]:
        return [artifact.path for artifact in self.artifacts]

    def fingerprints(self) -> dict[str, Any]:
        return fingerprint_files(self.paths, root=self.root)

    def of_kind(self, kind: str) -> list[ParsedArtifact]:
        return [artifact for artifact in self.artifacts if artifact.kind == kind]


def _candidate_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in sorted(root.iterdir()):
        if path.is_file() and path.suffix.lower() in _JSON_SUFFIXES | _TEXT_SUFFIXES:
            files.append(path)
    return files


def load_case_dir(root: Path) -> LoadedCase:
    case = LoadedCase(case_id=root.name, root=root)
    files = _candidate_files(root)
    if not files:
        case.load_errors.append("EMPTY_INPUT")
        return case
    for path in files:
        try:
            case.artifacts.append(parse_artifact(path))
        except (OSError, json.JSONDecodeError, AdapterError) as exc:
            case.load_errors.append(f"{path.name}: {exc}")
    return case


def load_case_file(path: Path) -> LoadedCase:
    case = LoadedCase(case_id=path.stem, root=path.parent)
    try:
        case.artifacts.append(parse_artifact(path))
    except (OSError, json.JSONDecodeError, AdapterError) as exc:
        case.load_errors.append(f"{path.name}: {exc}")
    return case


def discover_cases(input_path: Path) -> list[LoadedCase]:
    path = Path(input_path)
    if path.is_file():
        return [load_case_file(path)]
    if not path.is_dir():
        raise AdapterError(f"input path does not exist: {path}")
    subdirs = [item for item in sorted(path.iterdir()) if item.is_dir() and not item.name.startswith(".")]
    if subdirs:
        return [load_case_dir(item) for item in subdirs]
    return [load_case_dir(path)]


def map_claim_vocab(value: str | None, *, default: str = "hypothesis") -> str:
    """Map undeclared labels onto the claim-gate closed vocabulary without inferring EMPIRICAL."""
    if value in CLAIM_CLASSES:
        return value
    token = (value or "").strip().lower()
    if token in SYNTHETIC_TOKENS or token == "performance_only":
        return "synthetic_demonstration"
    if token in {"empirical", "confirmed"}:
        return "unsupported_claim"
    if token in {"engineering", "not_applicable"}:
        return "engineering_fact"
    if token == "benchmark":
        return "benchmark_result"
    if token in {"literature", "theoretical", "review_required"}:
        return "hypothesis"
    return default


def claim_payload_from_case(case: LoadedCase) -> dict[str, Any] | None:
    """Build a claim-gate input from the first claim or RunRecord without fabricating labels."""
    for artifact in case.of_kind("claim"):
        if isinstance(artifact.payload, dict):
            payload = dict(artifact.payload)
            if "claim_class" in payload:
                payload["claim_class"] = map_claim_vocab(str(payload.get("claim_class")), default="hypothesis")
            if "evidence_class" in payload:
                payload["evidence_class"] = map_claim_vocab(
                    str(payload.get("evidence_class")), default=payload.get("claim_class") or "hypothesis"
                )
            return payload
    for artifact in case.of_kind("run_record"):
        payload = artifact.payload if isinstance(artifact.payload, dict) else {}
        run_id = str(payload.get("run_id") or case.case_id)
        notes = payload.get("notes")
        text = notes if isinstance(notes, str) and notes.strip() else (
            f"Run {run_id} recorded local metrics for reporting only."
        )
        claim_class = map_claim_vocab(artifact.claim_class, default="engineering_fact")
        evidence_class = map_claim_vocab(artifact.evidence_class, default=claim_class)
        data_mode = artifact.data_mode or ("synthetic" if artifact.synthetic_flag else "unknown")
        record = {
            "claim_id": run_id,
            "text": text,
            "claim_class": claim_class,
            "evidence_class": evidence_class,
            "data_mode": data_mode,
        }
        if artifact.provenance is not None:
            record["provenance"] = artifact.provenance
        if artifact.n_tests is not None:
            record["n_tests"] = artifact.n_tests
        if artifact.multiplicity_correction is not None:
            record["multiplicity_correction"] = artifact.multiplicity_correction
        if artifact.null_controls:
            record["null_controls"] = list(artifact.null_controls)
        if artifact.evidence_method:
            record["evidence_method"] = artifact.evidence_method
        if artifact.proxy_status:
            record["proxy_status"] = artifact.proxy_status
        if artifact.network_access_requested:
            record["network_access_requested"] = True
        if "uncertainty" in payload:
            record["uncertainty"] = payload["uncertainty"]
        if "effect_size" in payload:
            record["effect_size"] = payload["effect_size"]
        if "labels_verified" in payload:
            record["labels_verified"] = payload["labels_verified"]
        return record
    for artifact in case.of_kind("literature"):
        payload = artifact.payload if isinstance(artifact.payload, dict) else {}
        source_id = str(payload.get("source_id") or case.case_id)
        title = payload.get("title") or "literature record"
        claim_kind = artifact.claim_kind or "hypothesis"
        evidence_class = artifact.evidence_class or "hypothesis"
        return {
            "claim_id": source_id,
            "text": str(title),
            "claim_class": "hypothesis",
            "evidence_class": evidence_class if evidence_class in {"hypothesis", "proxy_inference"} else "hypothesis",
            "data_mode": artifact.data_mode or "literature",
            "claim_kind": claim_kind,
        }
    return None
