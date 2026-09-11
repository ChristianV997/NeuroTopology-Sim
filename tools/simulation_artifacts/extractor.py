"""Deterministic, read-only extraction of simulation-run evidence lineage.

The extractor intentionally uses only Python's standard library. It indexes
existing files, parses small metadata artifacts, and never imports or executes
simulation solvers. Input paths are local paths; URLs are rejected.
"""
from __future__ import annotations

import csv
import hashlib
import json
import re
from pathlib import Path
from typing import Any, Iterable, Mapping

from .models import SCHEMA_VERSION, dumps_finite

_JSON_NAMES = {"runrecord.json", "summary.json", "metrics.json"}
_JSON_SUFFIXES = {".json", ".jsonl"}
_ROLE_PATTERNS = (
    ("run_record", re.compile(r"runrecord", re.I)),
    ("summary", re.compile(r"summary", re.I)),
    ("metrics", re.compile(r"metrics?", re.I)),
    ("checkpoint_manifest", re.compile(r"checkpoint|resume", re.I)),
    ("validation_report", re.compile(r"validat|quality|audit", re.I)),
    ("resource_telemetry", re.compile(r"resource|telemetry|memory|runtime", re.I)),
    ("null_model", re.compile(r"null|surrogate|permutation", re.I)),
)
_PARTIAL_RE = re.compile(r"(^|[_.-])(partial|incomplete|interrupted|resumable)([_.-]|$)", re.I)
_FAILED_RE = re.compile(r"(^|[_.-])(failed|failure|error)([_.-]|$)", re.I)
_NONFINITE_RE = re.compile(r"\b(?:nan|[+-]?inf(?:inity)?)\b", re.I)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _canonical_hash(value: Any) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _local_path(value: str | Path, *, must_exist: bool = True) -> Path:
    raw = str(value).strip()
    if "://" in raw or raw.startswith(("http:", "https:", "s3:", "gs:")):
        raise ValueError("network and cloud URLs are not accepted")
    path = Path(raw).expanduser().resolve()
    if must_exist and not path.is_dir():
        raise FileNotFoundError(f"run directory does not exist: {path}")
    return path


def _read_json(path: Path) -> tuple[Any | None, str | None]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        return None, f"unreadable artifact: {exc}"
    if _NONFINITE_RE.search(text):
        return None, "non-finite token (NaN or Infinity) is not permitted"
    try:
        value = json.loads(text, parse_constant=lambda token: (_ for _ in ()).throw(ValueError(f"non-finite token {token}")))
    except (json.JSONDecodeError, ValueError) as exc:
        return None, f"invalid JSON: {exc}"
    return value, None


def _read_csv_diagnostic(path: Path) -> str | None:
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            for row in csv.reader(handle):
                for token in row:
                    if _NONFINITE_RE.fullmatch(token.strip()):
                        return "non-finite token (NaN or Infinity) is not permitted"
    except (OSError, UnicodeDecodeError) as exc:
        return f"unreadable CSV: {exc}"
    return None


def _iter_files(run_dir: Path, excluded: set[Path]) -> Iterable[Path]:
    for path in sorted(run_dir.rglob("*"), key=lambda item: item.relative_to(run_dir).as_posix()):
        if path.is_file() and path.resolve() not in excluded:
            yield path


def _role(path: Path) -> str:
    name = path.name
    for role, pattern in _ROLE_PATTERNS:
        if pattern.search(name):
            return role
    return "other"


def _status_markers(path: Path, payload: Any | None) -> list[str]:
    markers: list[str] = []
    if _PARTIAL_RE.search(path.name):
        markers.append("partial_filename")
    if _FAILED_RE.search(path.name):
        markers.append("failed_filename")
    if isinstance(payload, Mapping):
        for key in ("status", "run_status", "state"):
            value = str(payload.get(key, "")).lower()
            if value in {"partial", "incomplete", "interrupted", "resumable"}:
                markers.append(f"{key}={value}")
            if value in {"failed", "failure", "error"}:
                markers.append(f"{key}={value}")
        for key in ("complete", "completed", "success", "successful"):
            if key in payload and payload[key] is False:
                markers.append(f"{key}=false")
    return sorted(set(markers))


def _metadata_path(path: Path, base: Path) -> str:
    return path.relative_to(base).as_posix()


def _previous_entries(previous_manifest: Path | None) -> dict[str, dict[str, Any]]:
    if previous_manifest is None or not previous_manifest.is_file():
        return {}
    payload, error = _read_json(previous_manifest)
    if error or not isinstance(payload, Mapping):
        return {}
    artifact_manifest = payload.get("artifact_manifest") if isinstance(payload.get("artifact_manifest"), Mapping) else payload
    entries = artifact_manifest.get("artifacts") if isinstance(artifact_manifest, Mapping) else None
    if not isinstance(entries, list):
        return {}
    return {str(item.get("relative_path")): dict(item) for item in entries if isinstance(item, Mapping) and item.get("relative_path")}


def _extract_provenance(metadata: list[tuple[str, Any]]) -> dict[str, Any]:
    records = [(name, payload) for name, payload in metadata if name.lower() == "runrecord.json" and isinstance(payload, Mapping)]
    record = records[0][1] if records else {}
    input_payload = record.get("input") if isinstance(record.get("input"), Mapping) else {}
    dependencies = record.get("dependencies") or record.get("dependency_versions") or record.get("environment") or {}
    provenance = {
        "run_id": record.get("run_id"),
        "run_kind": record.get("run_kind") or record.get("mode"),
        "created_at": record.get("created_at"),
        "dataset_id": record.get("dataset_id"),
        "data_mode": record.get("data_mode"),
        "source": record.get("source"),
        "repo": record.get("repo"),
        "git_commit": record.get("git_commit"),
        "synthetic": bool(record.get("synthetic") or record.get("data_mode") in {"synthetic", "synthetic_demo"}),
        "claim_scope": record.get("claim_scope") or record.get("claim_type") or "unspecified",
        "evidence_class": record.get("evidence_class") or "simulation_artifact",
        "input_fingerprint": _canonical_hash(input_payload),
        "configuration_fingerprint": _canonical_hash(record.get("config") or input_payload),
        "dependency_fingerprint": _canonical_hash(dependencies),
    }
    return provenance


def _relationships(entries: list[dict[str, Any]], metadata: list[tuple[str, Any]]) -> list[dict[str, str]]:
    by_role: dict[str, list[str]] = {}
    for entry in entries:
        by_role.setdefault(str(entry["role"]), []).append(str(entry["relative_path"]))
    links: list[dict[str, str]] = []
    for child_role, parent_role, relation in (
        ("summary", "run_record", "describes"),
        ("metrics", "summary", "quantifies"),
        ("checkpoint_manifest", "run_record", "resumes"),
        ("validation_report", "summary", "validates"),
        ("resource_telemetry", "run_record", "profiles"),
        ("null_model", "metrics", "tests"),
    ):
        for child in by_role.get(child_role, []):
            for parent in by_role.get(parent_role, []):
                links.append({"source": child, "target": parent, "relationship": relation})
    for name, payload in metadata:
        if not isinstance(payload, Mapping):
            continue
        for key in ("parent", "parent_artifact", "parent_path", "parent_checkpoint"):
            target = payload.get(key)
            if isinstance(target, str):
                links.append({"source": name, "target": target.replace("\\", "/"), "relationship": "parent"})
    return sorted({tuple(sorted(link.items())) for link in links}) and [dict(item) for item in sorted({tuple(sorted(link.items())) for link in links})] or []


def extract_run(run_dir: str | Path, *, previous_manifest: str | Path | None = None, ledger_reference: str | Path | None = None) -> dict[str, Any]:
    """Scan one existing run directory without executing any simulation code."""
    root = _local_path(run_dir)
    previous = _previous_entries(_local_path(previous_manifest, must_exist=False) if previous_manifest else None)
    excluded: set[Path] = set()
    ledger = None
    if ledger_reference:
        ledger_path = _local_path(ledger_reference, must_exist=False)
        ledger = {"path": str(ledger_path), "exists": ledger_path.is_file()}
    entries: list[dict[str, Any]] = []
    metadata: list[tuple[str, Any]] = []
    diagnostics: dict[str, list[str]] = {"missing": [], "stale": [], "partial": [], "failed": [], "conflicting": [], "errors": []}
    for path in _iter_files(root, excluded):
        relative = _metadata_path(path, root)
        stat = path.stat()
        old = previous.get(relative)
        reused = bool(old and old.get("size_bytes") == stat.st_size and old.get("mtime_ns") == stat.st_mtime_ns and old.get("sha256"))
        digest = str(old["sha256"]) if reused else _sha256(path)
        payload = None
        error = None
        if path.suffix.lower() in _JSON_SUFFIXES:
            payload, error = _read_json(path)
            if payload is not None:
                metadata.append((relative, payload))
        elif path.suffix.lower() == ".csv":
            error = _read_csv_diagnostic(path)
        markers = _status_markers(path, payload)
        entry = {
            "relative_path": relative,
            "role": _role(path),
            "sha256": digest,
            "size_bytes": stat.st_size,
            "mtime_ns": stat.st_mtime_ns,
            "checksum_reused": reused,
            "status_markers": markers,
            "parse_error": error,
        }
        entries.append(entry)
        diagnostics["partial"].append(relative) if any("partial" in marker or "incomplete" in marker or "interrupted" in marker or "resumable" in marker for marker in markers) else None
        diagnostics["failed"].append(relative) if any("failed" in marker or "failure" in marker or "error" in marker for marker in markers) else None
        diagnostics["errors"].append(f"{relative}: {error}") if error else None
    entries.sort(key=lambda item: item["relative_path"])
    current_names = {entry["relative_path"] for entry in entries}
    diagnostics["stale"].extend(sorted(set(previous).difference(current_names)))
    names = {entry["relative_path"].lower() for entry in entries}
    if "runrecord.json" not in names:
        diagnostics["missing"].append("RunRecord.json")
    if not ("summary.json" in names or "metrics.json" in names or "metrics.csv" in names):
        diagnostics["missing"].append("summary.json or metrics artifact")
    run_records = [payload for name, payload in metadata if name.lower() == "runrecord.json" and isinstance(payload, Mapping)]
    run_ids = {str(payload.get("run_id")) for payload in run_records if payload.get("run_id") is not None}
    if len(run_ids) > 1:
        diagnostics["conflicting"].append("multiple RunRecord.json payloads declare different run_id values")
    by_hash: dict[str, list[str]] = {}
    for entry in entries:
        by_hash.setdefault(entry["sha256"], []).append(entry["relative_path"])
    duplicates = [{"sha256": digest, "paths": sorted(paths)} for digest, paths in sorted(by_hash.items()) if len(paths) > 1]
    provenance = _extract_provenance(metadata)
    synthetic = bool(provenance["synthetic"])
    if synthetic:
        provenance["evidence_class"] = "synthetic_demo_only"
    if not provenance.get("run_id") or not provenance.get("created_at") or not provenance.get("source"):
        diagnostics["errors"].append("missing provenance in RunRecord.json: run_id, created_at, and source are required")
    if any(entry["parse_error"] for entry in entries):
        status = "BLOCKED"
    elif diagnostics["conflicting"]:
        status = "CONFLICTING"
    elif diagnostics["failed"]:
        status = "FAILED"
    elif diagnostics["partial"]:
        status = "PARTIAL"
    elif diagnostics["missing"] or diagnostics["errors"]:
        status = "INCOMPLETE"
    else:
        status = "COMPLETE"
    artifact_manifest = {
        "schema_version": SCHEMA_VERSION,
        "run_directory": str(root),
        "artifacts": entries,
        "duplicate_content": duplicates,
    }
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": status,
        "artifact_manifest": artifact_manifest,
        "provenance": provenance,
        "evidence": {
            "evidence_class": provenance["evidence_class"],
            "claim_scope": provenance["claim_scope"],
            "synthetic": synthetic,
        },
        "diagnostics": diagnostics,
        "relationships": _relationships(entries, metadata),
        "ledger_reference": ledger,
        "incremental_scan": {"previous_manifest_used": bool(previous), "checksums_reused": sum(1 for item in entries if item["checksum_reused"])},
        "read_only": True,
        "solver_executed": False,
        "heavy_runtime_imported": False,
    }
    report["report_sha256"] = hashlib.sha256(dumps_finite(report).encode("utf-8")).hexdigest()
    return report


def render_markdown(report: Mapping[str, Any]) -> str:
    """Render a concise deterministic lineage report."""
    provenance = report.get("provenance", {})
    diagnostics = report.get("diagnostics", {})
    lines = [
        "# Simulation Artifact Lineage",
        "",
        f"- Status: `{report.get('status')}`",
        f"- Run directory: `{report.get('artifact_manifest', {}).get('run_directory')}`",
        f"- Run ID: `{provenance.get('run_id') or 'unknown'}`",
        f"- Evidence class: `{provenance.get('evidence_class')}`",
        f"- Claim scope: `{provenance.get('claim_scope')}`",
        f"- Synthetic: `{provenance.get('synthetic')}`",
        "",
        "## Artifact manifest",
        "",
        "| Path | Role | SHA-256 | Bytes | Markers |",
        "| --- | --- | --- | ---: | --- |",
    ]
    for entry in report.get("artifact_manifest", {}).get("artifacts", []):
        lines.append(f"| `{entry['relative_path']}` | `{entry['role']}` | `{entry['sha256']}` | {entry['size_bytes']} | {', '.join(entry['status_markers']) or '—'} |")
    lines.extend(["", "## Diagnostics", ""])
    for key in ("missing", "stale", "partial", "failed", "conflicting", "errors"):
        values = diagnostics.get(key, [])
        lines.append(f"- {key}: {', '.join(f'`{value}`' for value in values) if values else 'none'}")
    lines.extend(["", "## Guardrails", "", "- Read-only scan: `true`", "- Solver executed: `false`", "- Heavy scientific runtime imported: `false`", "- Non-finite JSON values: blocked explicitly", ""])
    return "\n".join(lines)
