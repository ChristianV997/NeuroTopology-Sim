"""Bounded, read-only joins over existing run and provenance contracts.

The implementation parses only explicitly supplied JSON documents and hashes
explicitly referenced local files. It never imports or executes a producer,
solver, archive, or inspected artifact.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Iterable, Mapping, Sequence

from configs.empirical_sources.manifest import ORIGIN_LABELS as SOURCE_MANIFEST_ORIGIN_LABELS

from .models import (
    INTEGRATION_MANIFEST_SCHEMA,
    LEDGER_EVENT_SCHEMA_VERSION,
    LEDGER_SCHEMA_VERSION,
    REPORT_SCHEMA_VERSION,
    RUN_RECORD_SCHEMA_VERSIONS,
    SIMULATION_LINEAGE_SCHEMA,
    SOURCE_MANIFEST_SCHEMA,
    AuditLimits,
    Finding,
    ReferenceKey,
    run_configuration_fingerprint,
    sha256_json,
    simulation_report_checksum,
)

_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")
_GATE_EVENT_TYPES = frozenset({"validation_outcome", "release_review"})
_POSITIVE_GATE_WORDS = frozenset({
    "PASS", "PASSED", "VALID", "VALIDATED", "READY", "ADMISSIBLE",
    "CLAIM_ADMISSIBLE", "EVIDENCE_ADMISSIBLE", "SUPPORTED",
})
_UNSUPPORTED_SOURCE_REFERENCE_KEYS = frozenset({
    "source_id", "source_snapshot_id", "source_manifest_id", "snapshot_id",
    "dataset_identifier",
})
_UNSUPPORTED_LICENSE_FIELDS = frozenset({"license_id", "license_ref"})
_CONFIG_REFERENCE_KEYS = {"configuration_id", "config_id"}
_CONFIG_VERSION_KEYS = {"configuration_version", "config_version"}
_CONFIG_DIGEST_KEYS = {"configuration_sha256", "config_sha256", "configuration_fingerprint"}
_LEDGER_TYPED_REFERENCE_FIELDS: dict[str, dict[str, str]] = {
    "evidence_record": {"source_snapshot_ids": "source_snapshot"},
    "claim": {"evidence_ids": "evidence_record"},
    "hypothesis": {"claim_ids": "claim"},
    "experiment_spec": {"hypothesis_ids": "hypothesis"},
    "run_record": {"experiment_id": "experiment_spec"},
    "artifact_manifest": {"run_record_id": "run_record"},
    "validation_report": {
        "artifact_manifest_ids": "artifact_manifest",
        "run_record_id": "run_record",
    },
    "theory_revision": {
        "hypothesis_ids": "hypothesis",
        "validation_report_ids": "validation_report",
    },
}
_KNOWN_LEDGER_RECORD_TYPES = frozenset({
    "source_snapshot", "evidence_record", "claim", "hypothesis",
    "experiment_spec", "run_record", "artifact_manifest",
    "validation_report", "theory_revision",
})


class AuditInputError(ValueError):
    """The declared root or manifest list cannot be safely audited."""


class _DuplicateKeyError(ValueError):
    pass


@dataclass
class _Document:
    relative_path: str
    kind: str
    raw: dict[str, Any]
    raw_sha256: str
    size_bytes: int


@dataclass
class _Context:
    root: Path
    limits: AuditLimits
    findings: list[Finding] = field(default_factory=list)
    documents: list[_Document] = field(default_factory=list)
    referenced_paths: set[str] = field(default_factory=set)
    input_paths: set[str] = field(default_factory=set)
    source_tree_prefixes: set[str] = field(default_factory=set)
    output_entries_by_run: dict[str, dict[str, dict[str, Any]]] = field(default_factory=dict)
    file_cache: dict[str, tuple[str, int, tuple[int, int, int, int]]] = field(default_factory=dict)
    json_cache: dict[str, tuple[Mapping[str, Any], str, tuple[int, int, int, int]]] = field(default_factory=dict)
    total_bytes: int = 0
    inventory: list[dict[str, Any]] = field(default_factory=list)

    def add(self, code: str, subject: str, detail: str, severity: str = "warning") -> None:
        self.findings.append(Finding(code, subject, detail, severity))

    def charge(self, amount: int, *, subject: str) -> bool:
        if amount < 0 or self.total_bytes + amount > self.limits.max_total_bytes:
            self.add(
                "total_size_limit_exceeded",
                subject,
                f"cumulative bytes would exceed {self.limits.max_total_bytes}",
                "error",
            )
            return False
        self.total_bytes += amount
        return True


def _json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise _DuplicateKeyError(f"duplicate JSON object key {key!r}")
        result[key] = value
    return result


def _reject_constant(token: str) -> Any:
    raise ValueError(f"non-finite JSON token {token!r} is not permitted")


def _is_link(path: Path) -> bool:
    if path.is_symlink():
        return True
    junction_check = getattr(path, "is_junction", None)
    return bool(junction_check()) if callable(junction_check) else False


def _root_path(value: str | Path) -> Path:
    raw = Path(value)
    windows_drive = PureWindowsPath(str(value)).drive
    if windows_drive.startswith("\\\\"):
        raise AuditInputError("network/UNC artifact roots are not permitted")
    if _is_link(raw):
        raise AuditInputError("artifact root must not be a symlink or junction")
    try:
        root = raw.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise AuditInputError(f"artifact root is unavailable: {exc}") from exc
    if not root.is_dir():
        raise AuditInputError("artifact root must be a directory")
    return root


def _same_file_version(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        left.st_dev == right.st_dev
        and left.st_ino == right.st_ino
        and left.st_size == right.st_size
        and left.st_mtime_ns == right.st_mtime_ns
    )


def _file_signature(info: os.stat_result) -> tuple[int, int, int, int]:
    return info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns


def _read_stable_file(path: Path, *, maximum: int) -> tuple[bytes, os.stat_result]:
    """Read a bounded file; reject detectable symlink and replacement races.

    O_NOFOLLOW protects the final path component on platforms that provide it.
    The stat/fstat comparisons detect ordinary replacements and concurrent
    writes. They are not a portable defense against a hostile process that
    can race parent-directory components or restore file metadata.
    """
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode):
        raise ValueError("referenced path is not a regular, non-symlink file")
    if before.st_size > maximum:
        raise ValueError(f"file size {before.st_size} exceeds limit {maximum}")
    chunks: list[bytes] = []
    remaining = before.st_size
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "rb") as handle:
        opened = os.fstat(handle.fileno())
        if not stat.S_ISREG(opened.st_mode) or not _same_file_version(before, opened):
            raise ValueError("file changed between validation and open")
        while remaining:
            block = handle.read(min(1024 * 1024, remaining))
            if not block:
                raise ValueError("file became shorter while being read")
            chunks.append(block)
            remaining -= len(block)
        opened_after = os.fstat(handle.fileno())
    after = path.lstat()
    if not stat.S_ISREG(after.st_mode) or not _same_file_version(before, opened_after) or not _same_file_version(before, after):
        raise ValueError("file changed while being read")
    return b"".join(chunks), before


def _path_parts(raw: str) -> tuple[str, ...]:
    if not raw or "\x00" in raw:
        raise ValueError("path is empty or contains NUL")
    windows = PureWindowsPath(raw)
    if windows.drive or windows.root or windows.is_absolute():
        raise ValueError("absolute and drive-qualified references are not allowed")
    normalized = raw.replace("\\", "/")
    posix = PurePosixPath(normalized)
    if posix.is_absolute():
        raise ValueError("absolute references are not allowed")
    parts = tuple(part for part in posix.parts if part not in {"", "."})
    if not parts or any(part == ".." for part in parts):
        raise ValueError("path traversal or empty path is not allowed")
    return parts


def _resolve_relative(root: Path, raw: str | Path, *, allow_absolute_input: bool = False) -> tuple[Path, str]:
    text = str(raw)
    candidate = Path(text)
    if candidate.is_absolute():
        if not allow_absolute_input:
            raise ValueError("absolute paths are not permitted in embedded references")
        try:
            lexical = Path(os.path.abspath(candidate))
            relative = lexical.relative_to(root)
        except (OSError, ValueError) as exc:
            raise ValueError("absolute path is outside artifact root") from exc
        parts = _path_parts(relative.as_posix())
    else:
        parts = _path_parts(text)

    current = root
    for part in parts:
        current = current / part
        if _is_link(current):
            raise ValueError("symlink or junction path components are not permitted")
    try:
        resolved = current.resolve(strict=True)
        relative = resolved.relative_to(root)
    except (OSError, ValueError, RuntimeError) as exc:
        raise ValueError("path is missing or escapes artifact root") from exc
    return resolved, relative.as_posix()


def _classify(raw: Mapping[str, Any]) -> str:
    schema = raw.get("schema")
    version = raw.get("schema_version")
    if (
        version == LEDGER_SCHEMA_VERSION
        and isinstance(raw.get("cycle"), Mapping)
        and isinstance(raw.get("records"), list)
        and isinstance(raw.get("events"), list)
        and isinstance(raw.get("links"), list)
    ):
        return "research_cycle_export"
    if schema == SOURCE_MANIFEST_SCHEMA:
        return "source_manifest"
    if schema == INTEGRATION_MANIFEST_SCHEMA:
        return "integration_artifact_manifest"
    if version == SIMULATION_LINEAGE_SCHEMA and isinstance(raw.get("artifact_manifest"), Mapping):
        return "simulation_artifact_lineage"
    if version == "1" and isinstance(raw.get("bundle_id"), str):
        return "evidence_bundle"
    if isinstance(version, str) and version in RUN_RECORD_SCHEMA_VERSIONS and isinstance(raw.get("run_id"), str):
        return "run_record"
    return "unknown"


def _load_document(ctx: _Context, raw_path: str | Path) -> _Document | None:
    subject = str(raw_path)
    try:
        path, relative = _resolve_relative(ctx.root, raw_path, allow_absolute_input=True)
    except (OSError, ValueError, RuntimeError) as exc:
        ctx.add("unsafe_or_missing_path", subject, str(exc), "error")
        return None
    if not path.is_file():
        ctx.add("invalid_manifest_path", relative, "declared input manifest is not a regular file", "error")
        return None
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode):
            ctx.add("invalid_manifest_path", relative, "declared input manifest is not a regular, non-symlink file", "error")
            return None
        size = info.st_size
    except OSError as exc:
        ctx.add("manifest_read_error", relative, str(exc), "error")
        return None
    if size > ctx.limits.max_manifest_bytes:
        ctx.add("manifest_size_limit_exceeded", relative, f"{size} > {ctx.limits.max_manifest_bytes}", "error")
        return None
    if not ctx.charge(size, subject=relative):
        return None
    try:
        data, info = _read_stable_file(path, maximum=ctx.limits.max_manifest_bytes)
        if len(data) != size:
            ctx.add("file_changed_during_scan", relative, "manifest size changed while being read", "error")
            return None
        raw = json.loads(
            data.decode("utf-8"),
            parse_constant=_reject_constant,
            object_pairs_hook=_json_object,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, _DuplicateKeyError, RecursionError) as exc:
        ctx.add("malformed_manifest", relative, str(exc), "error")
        return None
    if not isinstance(raw, dict):
        ctx.add("malformed_manifest", relative, "manifest root must be a JSON object", "error")
        return None
    kind = _classify(raw)
    if kind == "unknown":
        schema = raw.get("schema", raw.get("schema_version", "<absent>"))
        ctx.add(
            "unverifiable_manifest_schema",
            relative,
            f"embedded schema {schema!r} is not supported by this auditor; no relationships or checksums were inferred",
        )
        _report_unverifiable_fields(ctx, raw, relative)
        return None
    digest = hashlib.sha256(data).hexdigest()
    ctx.file_cache[relative] = (digest, size, _file_signature(info))
    return _Document(relative, kind, raw, digest, size)


def _is_sha256(value: Any) -> bool:
    return isinstance(value, str) and bool(_SHA256_RE.fullmatch(value))


def _hash_file(ctx: _Context, raw_path: str, *, subject: str) -> tuple[str, int, str] | None:
    try:
        path, relative = _resolve_relative(ctx.root, raw_path)
    except (OSError, ValueError, RuntimeError) as exc:
        ctx.add("unsafe_or_missing_reference", subject, f"{raw_path!r}: {exc}", "error")
        return None
    cached = ctx.file_cache.get(relative)
    if cached is not None:
        try:
            current = path.lstat()
        except OSError as exc:
            ctx.add("artifact_read_error", subject, f"{relative}: {exc}", "error")
            return None
        if not stat.S_ISREG(current.st_mode) or _file_signature(current) != cached[2]:
            ctx.add("file_changed_during_scan", subject, f"{relative} changed after its first read/hash", "error")
            return None
        ctx.referenced_paths.add(relative)
        return cached[0], cached[1], relative
    try:
        before = path.lstat()
    except OSError as exc:
        ctx.add("artifact_read_error", subject, f"{relative}: {exc}", "error")
        return None
    if not stat.S_ISREG(before.st_mode):
        ctx.add("invalid_artifact_type", subject, f"{relative} is not a regular, non-symlink file", "error")
        return None
    if before.st_size > ctx.limits.max_artifact_bytes:
        ctx.add("artifact_size_limit_exceeded", subject, f"{relative}: {before.st_size} > {ctx.limits.max_artifact_bytes}", "error")
        return None
    if not ctx.charge(before.st_size, subject=relative):
        return None
    digest = hashlib.sha256()
    observed = 0
    try:
        flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
        descriptor = os.open(path, flags)
        with os.fdopen(descriptor, "rb") as handle:
            opened = os.fstat(handle.fileno())
            if not stat.S_ISREG(opened.st_mode) or not _same_file_version(before, opened):
                ctx.add("file_changed_during_scan", subject, f"{relative} changed between validation and open", "error")
                return None
            remaining = before.st_size
            while remaining:
                block = handle.read(min(1024 * 1024, remaining))
                if not block:
                    break
                observed += len(block)
                remaining -= len(block)
                digest.update(block)
            opened_after = os.fstat(handle.fileno())
        after = path.lstat()
    except OSError as exc:
        ctx.add("artifact_read_error", subject, f"{relative}: {exc}", "error")
        return None
    if observed != before.st_size or not stat.S_ISREG(after.st_mode) or not _same_file_version(before, opened_after) or not _same_file_version(before, after):
        ctx.add("file_changed_during_scan", subject, f"{relative} changed while being hashed", "error")
        return None
    ctx.referenced_paths.add(relative)
    actual_hash = digest.hexdigest()
    ctx.file_cache[relative] = (actual_hash, observed, _file_signature(after))
    return actual_hash, observed, relative


def _read_json_reference(ctx: _Context, raw_path: str, *, subject: str) -> tuple[Mapping[str, Any], str] | None:
    try:
        path, relative = _resolve_relative(ctx.root, raw_path)
    except (OSError, ValueError, RuntimeError) as exc:
        ctx.add("unsafe_or_missing_reference", subject, f"{raw_path!r}: {exc}", "error")
        return None
    cached_json = ctx.json_cache.get(relative)
    if cached_json is not None:
        try:
            current = path.lstat()
        except OSError as exc:
            ctx.add("artifact_read_error", subject, str(exc), "error")
            return None
        if not stat.S_ISREG(current.st_mode) or _file_signature(current) != cached_json[2]:
            ctx.add("file_changed_during_scan", relative, "referenced JSON changed after its first read", "error")
            return None
        ctx.referenced_paths.add(relative)
        return cached_json[0], cached_json[1]
    try:
        info = path.lstat()
        if not stat.S_ISREG(info.st_mode):
            ctx.add("invalid_artifact_type", subject, f"{relative} is not a regular, non-symlink file", "error")
            return None
        size = info.st_size
    except OSError as exc:
        ctx.add("artifact_read_error", subject, str(exc), "error")
        return None
    if size > ctx.limits.max_manifest_bytes:
        ctx.add("manifest_size_limit_exceeded", relative, f"{size} > {ctx.limits.max_manifest_bytes}", "error")
        return None
    if not ctx.charge(size, subject=relative):
        return None
    try:
        data, info = _read_stable_file(path, maximum=ctx.limits.max_manifest_bytes)
        if len(data) != size:
            ctx.add("file_changed_during_scan", relative, "referenced JSON size changed while being read", "error")
            return None
        payload = json.loads(
            data.decode("utf-8"),
            parse_constant=_reject_constant,
            object_pairs_hook=_json_object,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError, _DuplicateKeyError, RecursionError) as exc:
        ctx.add("malformed_evidence_reference", relative, str(exc), "error")
        return None
    if not isinstance(payload, Mapping):
        ctx.add("malformed_evidence_reference", relative, "referenced JSON must be an object", "error")
        return None
    digest = hashlib.sha256(data).hexdigest()
    signature = _file_signature(info)
    cached_file = ctx.file_cache.get(relative)
    if cached_file is not None and (cached_file[0] != digest or cached_file[2] != signature):
        ctx.add("file_changed_during_scan", relative, "referenced JSON differs from bytes already read or hashed", "error")
        return None
    ctx.file_cache[relative] = (digest, len(data), signature)
    ctx.referenced_paths.add(relative)
    result = (payload, relative, signature)
    ctx.json_cache[relative] = result
    return payload, relative


def _artifact_entry(ctx: _Context, entry: Mapping[str, Any], *, subject: str) -> dict[str, Any] | None:
    path_value = entry.get("relative_path")
    expected_hash = entry.get("sha256")
    expected_size = entry.get("size_bytes")
    if not isinstance(path_value, str) or not path_value:
        ctx.add("malformed_artifact_entry", subject, "relative_path is required", "error")
        return None
    if not _is_sha256(expected_hash):
        ctx.add("malformed_artifact_entry", subject, f"{path_value}: sha256 is missing or invalid", "error")
        return None
    if isinstance(expected_size, bool) or not isinstance(expected_size, int) or expected_size < 0:
        ctx.add("malformed_artifact_entry", subject, f"{path_value}: size_bytes must be a non-negative integer", "error")
        return None
    result = _hash_file(ctx, path_value, subject=subject)
    if result is None:
        return None
    actual_hash, actual_size, relative = result
    if actual_hash.lower() != expected_hash.lower():
        ctx.add("checksum_mismatch", subject, f"{relative}: declared {expected_hash}, observed {actual_hash}", "error")
    if actual_size != expected_size:
        ctx.add("size_mismatch", subject, f"{relative}: declared {expected_size}, observed {actual_size}", "error")
    return {"relative_path": relative, "sha256": actual_hash, "size_bytes": actual_size}


def _entries_from_manifest(ctx: _Context, doc: _Document) -> dict[str, dict[str, Any]]:
    raw = doc.raw
    if doc.kind == "integration_artifact_manifest":
        values = raw.get("artifacts")
        run_id = raw.get("run_id")
    else:
        manifest = raw.get("artifact_manifest")
        values = manifest.get("artifacts") if isinstance(manifest, Mapping) else None
        provenance = raw.get("provenance")
        run_id = provenance.get("run_id") if isinstance(provenance, Mapping) else None
        declared_report_hash = raw.get("report_sha256")
        if declared_report_hash is None:
            ctx.add("missing_report_checksum", doc.relative_path, "simulation artifact lineage report requires report_sha256", "error")
        else:
            without_hash = {key: value for key, value in raw.items() if key != "report_sha256"}
            try:
                expected_report_hash = simulation_report_checksum(without_hash)
            except (TypeError, ValueError) as exc:
                ctx.add("malformed_report_checksum", doc.relative_path, str(exc), "error")
            else:
                if not _is_sha256(declared_report_hash) or declared_report_hash.lower() != expected_report_hash:
                    ctx.add("checksum_mismatch", doc.relative_path, "simulation artifact report checksum does not match its documented finite-JSON serialization", "error")
        diagnostics = raw.get("diagnostics")
        if not isinstance(diagnostics, Mapping):
            ctx.add("malformed_producer_diagnostics", doc.relative_path, "diagnostics must be an object", "error")
        else:
            for source_key, code in (("stale", "producer_reports_stale_artifact"), ("missing", "producer_reports_missing_artifact"), ("partial", "partial_input"), ("failed", "failed_input"), ("conflicting", "conflicting_input"), ("errors", "producer_reports_error")):
                values_with_state = diagnostics.get(source_key)
                if not isinstance(values_with_state, list):
                    ctx.add("malformed_producer_diagnostics", doc.relative_path, f"diagnostics.{source_key} must be a list", "error")
                    continue
                for value in values_with_state:
                    if isinstance(value, str):
                        ctx.add(code, doc.relative_path, value, "error" if source_key in {"failed", "conflicting", "errors"} else "warning")
                    else:
                        ctx.add("malformed_producer_diagnostics", doc.relative_path, f"diagnostics.{source_key} entries must be strings", "error")
        status = raw.get("status")
        if not isinstance(status, str) or not status:
            ctx.add("malformed_producer_status", doc.relative_path, "producer status must be a non-empty string", "error")
        elif status in {"PARTIAL", "INCOMPLETE"}:
            ctx.add("partial_input", doc.relative_path, f"producer status is {status}")
        elif status in {"FAILED", "BLOCKED", "CONFLICTING"}:
            ctx.add("failed_input", doc.relative_path, f"producer status is {status}", "error")
    if not isinstance(run_id, str) or not run_id:
        ctx.add("missing_run_identity", doc.relative_path, "output manifest does not declare a run_id", "error")
        return {}
    if not isinstance(values, list):
        ctx.add("malformed_artifact_manifest", doc.relative_path, "artifacts must be an array", "error")
        return {}
    seen_paths: set[str] = set()
    entries: dict[str, dict[str, Any]] = {}
    for index, value in enumerate(values):
        subject = f"{doc.relative_path}#{index}"
        if not isinstance(value, Mapping):
            ctx.add("malformed_artifact_entry", subject, "artifact entry must be an object", "error")
            continue
        verified = _artifact_entry(ctx, value, subject=subject)
        if verified is None:
            continue
        relative = verified["relative_path"]
        if relative in seen_paths:
            ctx.add("duplicate_artifact_reference", subject, f"{relative} is listed more than once", "error")
        seen_paths.add(relative)
        entries[relative] = verified
    current = ctx.output_entries_by_run.setdefault(run_id, {})
    for path, entry in entries.items():
        prior = current.get(path)
        if prior is not None and prior["sha256"] != entry["sha256"]:
            ctx.add("contradictory_artifact_manifests", doc.relative_path, f"run {run_id} declares different content for {path}", "error")
        current[path] = entry
    return entries


def _walk_mappings(value: Any) -> Iterable[Mapping[str, Any]]:
    stack = [value]
    while stack:
        current = stack.pop()
        if isinstance(current, Mapping):
            yield current
            stack.extend(reversed(list(current.values())))
        elif isinstance(current, list):
            stack.extend(reversed(current))


def _walk_mappings_with_paths(value: Any, path: str = "") -> Iterable[tuple[str, Mapping[str, Any]]]:
    stack: list[tuple[str, Any]] = [(path, value)]
    while stack:
        current_path, current = stack.pop()
        if isinstance(current, Mapping):
            yield current_path, current
            for key, item in reversed(list(current.items())):
                escaped_key = str(key).replace("~", "~0").replace("/", "~1")
                stack.append((f"{current_path}/{escaped_key}", item))
        elif isinstance(current, list):
            for index in range(len(current) - 1, -1, -1):
                stack.append((f"{current_path}/{index}", current[index]))


def _report_unverifiable_fields(ctx: _Context, raw: Mapping[str, Any], source: str) -> None:
    """Report present values whose field contracts are absent or unclassified."""
    for path, mapping in _walk_mappings_with_paths(raw):
        for field_name in ("origin", "data_mode"):
            if field_name in mapping and _declared_origin_class(mapping[field_name]) is None:
                value = mapping[field_name]
                if isinstance(value, str) and value in SOURCE_MANIFEST_ORIGIN_LABELS:
                    detail = (
                        f"{field_name} {value!r} is recognized by the source-manifest schema but is not "
                        "classifiable as synthetic or empirical for this join; no origin equivalence was inferred"
                    )
                else:
                    detail = f"{field_name} {value!r} is not classified by the supported synthetic/empirical vocabulary"
                ctx.add(
                    "unverifiable_origin",
                    f"{source}#{path}/{field_name}",
                    detail,
                )
        if "artifact_type" in mapping:
            ctx.add(
                "unverifiable_artifact_type",
                f"{source}#{path}/artifact_type",
                f"artifact_type {mapping['artifact_type']!r} has no declared type contract in the supplied current-main schemas",
            )
        for field_name in sorted(_UNSUPPORTED_LICENSE_FIELDS & mapping.keys()):
            code = "unverifiable_license_reference" if field_name == "license_ref" else "unverifiable_license_identity"
            ctx.add(
                code,
                f"{source}#{path}/{field_name}",
                f"field {field_name!r} has no typed license record contract on current main; it is not used to resolve another identifier by string equality",
            )


def _explicit_configuration_pins(value: Any) -> list[tuple[ReferenceKey, str | None, str | None]]:
    """Return only explicit config ID/version/digest triples from one document."""
    pins: list[tuple[ReferenceKey, str | None, str | None]] = []
    for mapping in _walk_mappings(value):
        config_id = next((mapping[key] for key in sorted(_CONFIG_REFERENCE_KEYS) if isinstance(mapping.get(key), str) and mapping[key]), None)
        if not isinstance(config_id, str):
            continue
        version_value = next((mapping[key] for key in sorted(_CONFIG_VERSION_KEYS) if isinstance(mapping.get(key), (str, int)) and not isinstance(mapping[key], bool)), None)
        digest_value = next((mapping[key] for key in sorted(_CONFIG_DIGEST_KEYS) if isinstance(mapping.get(key), str) and mapping[key]), None)
        version = str(version_value) if version_value is not None else None
        digest = digest_value.lower() if digest_value is not None else None
        if version is not None or digest is not None:
            pins.append((ReferenceKey("configuration", "configuration_id", config_id), version, digest))
    return pins


def _record_type_id(record: Mapping[str, Any]) -> str | None:
    value = record.get("record_id")
    if isinstance(value, str) and value:
        return value
    for key in ("snapshot_id", "evidence_id", "claim_id", "hypothesis_id", "experiment_id", "run_record_id", "artifact_manifest_id", "validation_report_id", "revision_id"):
        value = record.get(key)
        if isinstance(value, str) and value:
            return value
    return None


def _verify_ledger_export(ctx: _Context, doc: _Document) -> dict[str, Any] | None:
    raw = doc.raw
    required = {"cycle", "records", "events", "links", "export_checksum"}
    missing = sorted(required - set(raw))
    if missing:
        ctx.add("malformed_ledger_export", doc.relative_path, f"missing fields {missing}", "error")
        return None
    expected_export = raw.get("export_checksum")
    body = {key: value for key, value in raw.items() if key != "export_checksum"}
    try:
        actual_export = sha256_json(body)
    except (TypeError, ValueError) as exc:
        ctx.add("malformed_ledger_export", doc.relative_path, str(exc), "error")
        return None
    if not _is_sha256(expected_export) or expected_export.lower() != actual_export:
        ctx.add("checksum_mismatch", doc.relative_path, "ledger export checksum differs under ResearchCycleLedger canonical_json", "error")
    cycle = raw.get("cycle")
    records = raw.get("records")
    events = raw.get("events")
    links = raw.get("links")
    if not isinstance(cycle, Mapping) or not isinstance(cycle.get("cycle_id"), str):
        ctx.add("malformed_ledger_export", doc.relative_path, "cycle.cycle_id is required", "error")
        return None
    if not all(isinstance(items, list) for items in (records, events, links)):
        ctx.add("malformed_ledger_export", doc.relative_path, "records, events, and links must be arrays", "error")
        return None
    cycle_id = cycle["cycle_id"]
    record_index: dict[str, dict[str, Any]] = {}
    record_ids_seen: set[str] = set()
    for index, record in enumerate(records):
        subject = f"{doc.relative_path}:record[{index}]"
        if not isinstance(record, Mapping):
            ctx.add("malformed_ledger_record", subject, "record must be an object", "error")
            continue
        record_id = _record_type_id(record)
        record_type = record.get("record_type")
        if not record_id or not isinstance(record_type, str):
            ctx.add("malformed_ledger_record", subject, "record_type and stable record identifier are required", "error")
            continue
        if record_type not in _KNOWN_LEDGER_RECORD_TYPES:
            ctx.add("unverifiable_ledger_record_type", subject, f"record_type {record_type!r} is not part of the supported research-cycle record contract; typed relationships are not inferred")
        if record_id in record_ids_seen:
            ctx.add("duplicate_record_id", record_id, "ledger export contains this record ID more than once", "error")
        record_ids_seen.add(record_id)
        if record.get("cycle_id") != cycle_id:
            ctx.add("record_cycle_mismatch", record_id, f"record cycle_id {record.get('cycle_id')!r} differs from export cycle {cycle_id!r}", "error")
        checksum = record.get("checksum")
        checksum_basis = {key: value for key, value in record.items() if key != "checksum"}
        try:
            actual = sha256_json(checksum_basis)
        except (TypeError, ValueError) as exc:
            ctx.add("malformed_ledger_record", record_id, str(exc), "error")
            actual = None
        if actual is None or not _is_sha256(checksum) or checksum.lower() != actual:
            ctx.add("checksum_mismatch", record_id, "record checksum differs under ResearchCycleLedger canonical_json", "error")
        normalized = dict(record)
        normalized["record_id"] = record_id
        record_index[record_id] = normalized

    _verify_ledger_events(ctx, doc.relative_path, cycle_id, events)
    _verify_ledger_links(ctx, doc.relative_path, cycle_id, records, record_index, links)
    _verify_ledger_cycle_hash(ctx, doc.relative_path, cycle)
    return {"cycle_id": cycle_id, "records": record_index, "events": events, "links": links}


def _verify_ledger_cycle_hash(ctx: _Context, source: str, cycle: Mapping[str, Any]) -> None:
    created = cycle.get("created_hash")
    basis = {key: cycle.get(key) for key in ("cycle_id", "parent_cycle_id", "metadata")}
    try:
        expected = sha256_json(basis)
    except (TypeError, ValueError) as exc:
        ctx.add("malformed_cycle_record", source, str(exc), "error")
        return
    if not _is_sha256(created) or created.lower() != expected:
        ctx.add("checksum_mismatch", str(cycle.get("cycle_id")), "cycle created_hash differs under ResearchCycleLedger canonical_json", "error")


def _verify_ledger_events(ctx: _Context, source: str, cycle_id: str, events: list[Any]) -> None:
    parsed: list[Mapping[str, Any]] = []
    seen: set[str] = set()
    for index, event in enumerate(events):
        subject = f"{source}:event[{index}]"
        if not isinstance(event, Mapping):
            ctx.add("malformed_ledger_event", subject, "event must be an object", "error")
            continue
        event_id = event.get("event_id")
        if not isinstance(event_id, str) or not event_id:
            ctx.add("malformed_ledger_event", subject, "event_id is required", "error")
            continue
        if event_id in seen:
            ctx.add("duplicate_event_id", event_id, "ledger export contains this event ID more than once", "error")
        seen.add(event_id)
        if event.get("cycle_id") != cycle_id or event.get("schema_version") != LEDGER_EVENT_SCHEMA_VERSION:
            ctx.add("malformed_ledger_event", event_id, "event cycle or schema version is inconsistent", "error")
        basis = {key: event.get(key) for key in ("cycle_id", "event_id", "sequence", "event_type", "producer", "status", "payload", "previous_hash", "schema_version")}
        try:
            expected = sha256_json(basis)
        except (TypeError, ValueError) as exc:
            ctx.add("malformed_ledger_event", event_id, str(exc), "error")
            expected = None
        actual = event.get("event_hash")
        if expected is None or not _is_sha256(actual) or actual.lower() != expected:
            ctx.add("checksum_mismatch", event_id, "event_hash differs under ResearchCycleLedger canonical_json", "error")
        parsed.append(event)
    ordered = sorted(parsed, key=lambda event: (event.get("sequence") if isinstance(event.get("sequence"), int) else -1, str(event.get("event_id"))))
    previous: str | None = None
    for expected_sequence, event in enumerate(ordered, 1):
        if event.get("sequence") != expected_sequence or event.get("previous_hash") != previous:
            ctx.add("ledger_event_chain_mismatch", str(event.get("event_id")), "event sequence or previous_hash does not follow the declared hash chain", "error")
        event_hash = event.get("event_hash")
        previous = event_hash if isinstance(event_hash, str) else None


def _verify_ledger_links(
    ctx: _Context,
    source: str,
    cycle_id: str,
    records: list[Any],
    record_index: Mapping[str, Mapping[str, Any]],
    links: list[Any],
) -> None:
    expected_links: set[tuple[str, str]] = set()
    for record in records:
        if not isinstance(record, Mapping):
            continue
        record_id = _record_type_id(record)
        if not record_id:
            continue
        for parent_id in record.get("parent_ids", []) if isinstance(record.get("parent_ids"), list) else []:
            if isinstance(parent_id, str):
                expected_links.add((parent_id, record_id))
        for child_id in record.get("child_ids", []) if isinstance(record.get("child_ids"), list) else []:
            if isinstance(child_id, str):
                expected_links.add((record_id, child_id))
    actual_links: set[tuple[str, str]] = set()
    for index, link in enumerate(links):
        if not isinstance(link, Mapping):
            ctx.add("malformed_ledger_link", f"{source}:link[{index}]", "link must be an object", "error")
            continue
        parent = link.get("parent_id")
        child = link.get("child_id")
        if not isinstance(parent, str) or not isinstance(child, str):
            ctx.add("malformed_ledger_link", f"{source}:link[{index}]", "parent_id and child_id are required", "error")
            continue
        actual_links.add((parent, child))
        if child not in record_index:
            ctx.add("unresolved_ledger_link", f"{parent}->{child}", "record_links child is absent from this cycle export", "error")
    local_expected = {item for item in expected_links if item[0] in record_index and item[1] in record_index}
    local_actual = {item for item in actual_links if item[0] in record_index and item[1] in record_index}
    if local_actual != local_expected:
        missing = sorted(local_expected - local_actual)
        extra = sorted(local_actual - local_expected)
        ctx.add("ledger_link_index_mismatch", source, f"record_links differ from declared record refs; missing={missing}, extra={extra}", "error")


def _ledger_refs(ctx: _Context, exports: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    all_records: list[dict[str, Any]] = []
    all_events: list[dict[str, Any]] = []
    all_links: list[Mapping[str, Any]] = []
    for export in exports:
        all_records.extend(export["records"].values())
        all_events.extend(event for event in export["events"] if isinstance(event, Mapping))
        all_links.extend(link for link in export["links"] if isinstance(link, Mapping))
    generic_index: dict[ReferenceKey, list[dict[str, Any]]] = {}
    typed_index: dict[ReferenceKey, list[dict[str, Any]]] = {}
    duplicate_ids: set[str] = set()
    for record in all_records:
        record_id = record.get("record_id")
        record_type = record.get("record_type")
        if not isinstance(record_id, str) or not record_id:
            continue
        generic_key = ReferenceKey("research_cycle_record", "record_id", record_id)
        prior = generic_index.setdefault(generic_key, [])
        if prior:
            duplicate_ids.add(record_id)
        prior.append(record)
        if isinstance(record_type, str) and record_type:
            typed_key = ReferenceKey(record_type, "record_id", record_id)
            typed_index.setdefault(typed_key, []).append(record)
    for record_id in sorted(duplicate_ids):
        ctx.add("duplicate_record_id", record_id, "record ID is repeated across declared ledger exports", "error")

    cycles = {item["cycle_id"]: item for item in exports}
    cycle_parents: dict[str, str | None] = {}
    for export in exports:
        # A compact export stores one cycle object; retain parent metadata from the record.
        cycle_id = export["cycle_id"]
        cycle_parent = export.get("parent_cycle_id")
        if cycle_id in cycle_parents and cycle_parents[cycle_id] != cycle_parent:
            ctx.add("contradictory_cycle_export", cycle_id, "same cycle has conflicting parent-cycle declarations", "error")
        cycle_parents[cycle_id] = cycle_parent

    for cycle_id, parent_id in cycle_parents.items():
        if parent_id is not None and parent_id not in cycle_parents:
            ctx.add("unresolved_parent_cycle", cycle_id, f"parent cycle {parent_id!r} was not among declared ledger exports")
        cursor = parent_id
        visited = {cycle_id}
        while isinstance(cursor, str) and cursor in cycle_parents:
            if cursor in visited:
                ctx.add("cycle_parent_loop", cycle_id, "cycle parent references contain a loop", "error")
                break
            visited.add(cursor)
            cursor = cycle_parents[cursor]
    for link in all_links:
        parent_id = link.get("parent_id")
        child_id = link.get("child_id")
        if not isinstance(parent_id, str) or not isinstance(child_id, str):
            continue
        parent_matches = generic_index.get(ReferenceKey("research_cycle_record", "record_id", parent_id), [])
        child_matches = generic_index.get(ReferenceKey("research_cycle_record", "record_id", child_id), [])
        if not parent_matches or not child_matches:
            ctx.add("unresolved_ledger_link", f"{parent_id}->{child_id}", "record_links endpoint was not included in explicitly supplied cycle exports")
            continue
        if len(parent_matches) != 1 or len(child_matches) != 1:
            ctx.add("ambiguous_ledger_link", f"{parent_id}->{child_id}", "record_links endpoint ID is duplicated; the endpoint was not selected", "error")
            continue
        parent = parent_matches[0]
        child = child_matches[0]
        source_cycle = child.get("cycle_id")
        target_cycle = parent.get("cycle_id")
        cursor = source_cycle
        visited: set[str] = set()
        allowed = False
        while isinstance(cursor, str) and cursor not in visited:
            if cursor == target_cycle:
                allowed = True
                break
            visited.add(cursor)
            cursor = cycle_parents.get(cursor)
        if not allowed:
            ctx.add("cross_cycle_reference_invalid", child_id, f"record_links parent {parent_id!r} belongs to unrelated or descendant cycle {target_cycle!r}", "error")
    for record in all_records:
        record_id = record.get("record_id")
        record_type = record.get("record_type")
        if not isinstance(record_id, str) or not record_id:
            continue
        source_cycle = record.get("cycle_id")
        refs: list[str] = []
        for field_name in ("parent_ids", "child_ids"):
            value = record.get(field_name, [])
            if not isinstance(value, list):
                ctx.add("malformed_ledger_reference", f"{record_id}.{field_name}", "generic record references must be arrays of record_id strings", "error")
                continue
            for target_id in value:
                if not isinstance(target_id, str) or not target_id:
                    ctx.add("malformed_ledger_reference", f"{record_id}.{field_name}", "generic record references must contain non-empty strings", "error")
                else:
                    refs.append(target_id)
        for target_id in sorted(set(refs)):
            generic_key = ReferenceKey("research_cycle_record", "record_id", target_id)
            matches = generic_index.get(generic_key, [])
            if not matches:
                if target_id not in duplicate_ids:
                    ctx.add("unresolved_ledger_reference", f"{record_id}.parent_ids/child_ids", f"generic record_id reference {target_id!r} is not in the supplied cycle lineage")
                continue
            if len(matches) != 1:
                ctx.add("ambiguous_ledger_reference", f"{record_id}.parent_ids/child_ids", f"generic record_id {target_id!r} is duplicated; no target was selected", "error")
                continue
            target = matches[0]
            target_cycle = target.get("cycle_id")
            cursor = source_cycle
            seen_cycles: set[str] = set()
            allowed = False
            while isinstance(cursor, str) and cursor not in seen_cycles:
                if cursor == target_cycle:
                    allowed = True
                    break
                seen_cycles.add(cursor)
                cursor = cycle_parents.get(cursor)
            if not allowed:
                ctx.add("cross_cycle_reference_invalid", record_id, f"generic record_id reference {target_id!r} crosses from {source_cycle!r} to unrelated or descendant cycle {target_cycle!r}", "error")

        field_targets = _LEDGER_TYPED_REFERENCE_FIELDS.get(str(record_type), {})
        for field_name, expected_type in field_targets.items():
            value = record.get(field_name)
            is_plural = field_name.endswith("_ids")
            if (is_plural and not isinstance(value, list)) or (not is_plural and not isinstance(value, str)):
                ctx.add("malformed_ledger_reference", f"{record_id}.{field_name}", f"typed reference must be {'an array' if is_plural else 'a string'} for target record type {expected_type!r}", "error")
                continue
            values = value if isinstance(value, list) else [value]
            for target_id in values:
                if not isinstance(target_id, str) or not target_id:
                    ctx.add("malformed_ledger_reference", f"{record_id}.{field_name}", f"typed reference to {expected_type!r} must contain non-empty strings", "error")
                    continue
                expected_key = ReferenceKey(expected_type, "record_id", target_id)
                matches = typed_index.get(expected_key, [])
                if len(matches) > 1:
                    ctx.add("ambiguous_ledger_reference", f"{record_id}.{field_name}", f"typed {expected_type!r} record_id {target_id!r} is duplicated; no target was selected", "error")
                    continue
                if not matches:
                    generic_matches = generic_index.get(ReferenceKey("research_cycle_record", "record_id", target_id), [])
                    found_types = sorted({str(item.get("record_type")) for item in generic_matches})
                    if found_types:
                        ctx.add("typed_reference_type_mismatch", f"{record_id}.{field_name}", f"expected {expected_type!r} record_id {target_id!r}, but supplied records have type(s) {found_types}", "error")
                    elif target_id not in duplicate_ids:
                        ctx.add("unresolved_ledger_reference", f"{record_id}.{field_name}", f"typed reference to {expected_type!r} record_id {target_id!r} is not in the supplied cycle lineage")
                    continue
                target = matches[0]
                target_cycle = target.get("cycle_id")
                cursor = source_cycle
                seen_cycles: set[str] = set()
                allowed = False
                while isinstance(cursor, str) and cursor not in seen_cycles:
                    if cursor == target_cycle:
                        allowed = True
                        break
                    seen_cycles.add(cursor)
                    cursor = cycle_parents.get(cursor)
                if not allowed:
                    ctx.add("cross_cycle_reference_invalid", f"{record_id}.{field_name}", f"typed {expected_type!r} reference {target_id!r} crosses from {source_cycle!r} to unrelated or descendant cycle {target_cycle!r}", "error")
    return all_records, all_events


def _verify_evidence_bundle(ctx: _Context, doc: _Document) -> None:
    raw = doc.raw
    bundle_id = raw.get("bundle_id")
    if not isinstance(bundle_id, str) or not bundle_id:
        ctx.add("malformed_evidence_bundle", doc.relative_path, "bundle_id is required", "error")
        return
    artifact_ids = raw.get("artifact_ids")
    if not isinstance(artifact_ids, list) or any(not isinstance(value, str) or not value for value in artifact_ids):
        ctx.add("malformed_evidence_bundle", doc.relative_path, "artifact_ids must be a list of non-empty strings", "error")
        return
    if len(artifact_ids) != len(set(artifact_ids)):
        ctx.add("duplicate_evidence_artifact_id", bundle_id, "artifact_ids contains duplicates", "error")
    transition_ids = raw.get("transition_record_ids") or []
    coordinate_ids = raw.get("phase_space_coordinate_ids") or []
    if not isinstance(transition_ids, list) or any(not isinstance(value, str) or not value for value in transition_ids):
        ctx.add("malformed_evidence_bundle", doc.relative_path, "transition_record_ids must be a list of non-empty strings", "error")
        return
    if not isinstance(coordinate_ids, list) or any(not isinstance(value, str) or not value for value in coordinate_ids):
        ctx.add("malformed_evidence_bundle", doc.relative_path, "phase_space_coordinate_ids must be a list of non-empty strings", "error")
        return
    if not isinstance(raw.get("dataset_id"), str) or not raw.get("dataset_id"):
        ctx.add("malformed_evidence_bundle", doc.relative_path, "dataset_id must be a non-empty string", "error")
        return
    if not isinstance(raw.get("requested_use"), str) or not raw.get("requested_use"):
        ctx.add("malformed_evidence_bundle", doc.relative_path, "requested_use must be a non-empty string", "error")
        return
    identity = {
        "dataset_id": raw.get("dataset_id"),
        "artifact_ids": sorted(artifact_ids),
        "requested_use": raw.get("requested_use"),
        "transition_record_ids": sorted(transition_ids),
        "phase_space_coordinate_ids": sorted(coordinate_ids),
    }
    try:
        expected = sha256_json(identity, ensure_ascii=True)[:16]
    except (TypeError, ValueError) as exc:
        ctx.add("malformed_evidence_bundle", doc.relative_path, str(exc), "error")
        return
    if expected != bundle_id:
        ctx.add("checksum_mismatch", bundle_id, "bundle_id differs under EvidenceBundleV1 identity canonicalization", "error")
    paths = raw.get("artifact_paths")
    if not isinstance(paths, Mapping):
        ctx.add("malformed_evidence_bundle", doc.relative_path, "artifact_paths must be an object keyed by artifact ID", "error")
        paths = {}
    decisions = raw.get("registry_decisions")
    if isinstance(decisions, list):
        decided_artifacts = {
            item.get("id") for item in decisions
            if isinstance(item, Mapping) and item.get("kind") == "artifact" and isinstance(item.get("id"), str)
        }
        for artifact_id in sorted(set(artifact_ids) - decided_artifacts):
            ctx.add("evidence_artifact_decision_missing", bundle_id, f"artifact ID {artifact_id!r} has no exact artifact-kind registry decision in the bundle")
    elif artifact_ids:
        ctx.add("evidence_artifact_decisions_unverifiable", bundle_id, "artifact_ids are present but registry_decisions is absent or malformed")
    for artifact_id, value in sorted(paths.items(), key=lambda pair: str(pair[0])):
        if not isinstance(value, str):
            ctx.add("malformed_evidence_reference", bundle_id, f"artifact_paths[{artifact_id!r}] must be a relative path", "error")
            continue
        result = _hash_file(ctx, value, subject=f"{bundle_id}:artifact:{artifact_id}")
        if result is None:
            continue
        ctx.input_paths.add(result[2])
    for id_field, path_field, id_key in (
        ("transition_record_ids", "transition_record_paths", "transition_id"),
        ("phase_space_coordinate_ids", "phase_space_coordinate_paths", "coordinate_id"),
    ):
        ids = raw.get(id_field) if isinstance(raw.get(id_field), list) else []
        paths_list = raw.get(path_field) if isinstance(raw.get(path_field), list) else []
        if len(ids) != len(paths_list):
            ctx.add("evidence_reference_cardinality_mismatch", bundle_id, f"{id_field} and {path_field} are not parallel lists", "error")
            continue
        for expected_id, path_value in zip(ids, paths_list):
            if not isinstance(expected_id, str) or not isinstance(path_value, str):
                ctx.add("malformed_evidence_reference", bundle_id, f"invalid {id_field}/{path_field} entry", "error")
                continue
            parsed = _read_json_reference(ctx, path_value, subject=f"{bundle_id}:{path_field}")
            if parsed is None:
                continue
            payload, relative = parsed
            if payload.get(id_key) != expected_id:
                ctx.add("evidence_identity_mismatch", relative, f"declared {expected_id!r}, referenced document {id_key}={payload.get(id_key) if isinstance(payload, Mapping) else None!r}", "error")
            ctx.input_paths.add(relative)


def _check_source_and_config_links(ctx: _Context, docs: list[_Document], ledger_records: list[dict[str, Any]]) -> None:
    source_docs = [doc for doc in docs if doc.kind == "source_manifest"]
    source_snapshots = [record for record in ledger_records if record.get("record_type") == "source_snapshot"]
    source_catalog: dict[ReferenceKey, list[_Document]] = {}

    def add_unverifiable_refs(raw: Mapping[str, Any], *, subject: str, allowed: set[tuple[str, str]]) -> None:
        for path, mapping in _walk_mappings_with_paths(raw):
            for key in sorted(_UNSUPPORTED_SOURCE_REFERENCE_KEYS):
                value = mapping.get(key)
                if value is None or (path, key) in allowed:
                    continue
                ctx.add(
                    "unverifiable_source_reference",
                    f"{subject}#{path}/{key}",
                    f"field {key!r} contains {value!r}, but the current record contract does not define its target type/namespace; no join was attempted",
                )

    for doc in source_docs:
        dataset_identifier = doc.raw.get("dataset_identifier")
        if not isinstance(dataset_identifier, str) or not dataset_identifier:
            ctx.add("missing_source_identity", doc.relative_path, "EmpiricalSourceManifest.v1 requires dataset_identifier", "error")
        else:
            key = ReferenceKey("EmpiricalSourceManifest.v1", "dataset_identifier", dataset_identifier)
            source_catalog.setdefault(key, []).append(doc)
        if "origin" not in doc.raw:
            ctx.add("source_origin_unverifiable", f"{doc.relative_path}#/origin", "source origin is absent; synthetic versus empirical origin cannot be joined")
        add_unverifiable_refs(
            doc.raw,
            subject=doc.relative_path,
            allowed={("", "dataset_identifier")},
        )
        local_root = doc.raw.get("local_root")
        if isinstance(local_root, str) and local_root:
            try:
                local_path = Path(local_root)
                if local_path.is_absolute():
                    raise ValueError("absolute local_root is not accepted for artifact-root joins")
                parts = _path_parts(local_root)
                relative = PurePosixPath(*parts).as_posix()
                ctx.source_tree_prefixes.add(relative)
                resolved, _ = _resolve_relative(ctx.root, relative)
                if not resolved.is_dir():
                    ctx.add("missing_source_root", doc.relative_path, f"declared local_root {relative!r} is not a directory")
            except (OSError, ValueError, RuntimeError) as exc:
                ctx.add("source_root_unverifiable", doc.relative_path, str(exc))
        declared_source_checksum = doc.raw.get("source_checksum")
        if declared_source_checksum is not None:
            if not _is_sha256(declared_source_checksum):
                ctx.add("malformed_source_checksum", doc.relative_path, "source_checksum must be a 64-character SHA-256 hex digest", "error")
            else:
                ctx.add("source_manifest_checksum_unverifiable", doc.relative_path, "source_checksum is not part of EmpiricalSourceManifest.v1 and its byte/canonicalization scope is undocumented")
    for record in source_snapshots:
        metadata = record.get("metadata") if isinstance(record.get("metadata"), Mapping) else {}
        record_id = str(record.get("record_id", "source_snapshot"))
        if "metadata" in record and not isinstance(record.get("metadata"), Mapping):
            ctx.add("malformed_source_snapshot", record_id, "metadata must be an object", "error")
        if not isinstance(record.get("data_mode"), str) or not record.get("data_mode"):
            ctx.add("malformed_source_snapshot", record_id, "data_mode is required", "error")
        for path, mapping in _walk_mappings_with_paths(metadata, "/metadata"):
            for key in sorted(_UNSUPPORTED_SOURCE_REFERENCE_KEYS):
                value = mapping.get(key)
                if value is not None:
                    ctx.add(
                        "unverifiable_source_reference",
                        f"ledger record {record_id}#{path}/{key}",
                        f"metadata field {key!r} contains {value!r}, but SourceSnapshot.metadata has no typed source-reference contract; no join was attempted",
                    )
        ctx.add("license_not_declared", record_id, "SourceSnapshot has no typed license-reference field; metadata values cannot supply one")
        uri = record.get("source_uri")
        source_hash = record.get("source_sha256")
        if not isinstance(uri, str) or not uri:
            ctx.add("source_uri_missing", record_id, "SourceSnapshot source_uri is required", "error")
        if not _is_sha256(source_hash):
            ctx.add("malformed_source_checksum", record_id, "SourceSnapshot source_sha256 must be a 64-character SHA-256 hex digest", "error")
        else:
            ctx.add("source_checksum_scope_unverifiable", record_id, "SourceSnapshot defines source_sha256 format but not whether it hashes raw URI bytes, normalized text, or an excerpt; source_uri is not resolved or fetched")

    # Dataset identities are joined only across the contract-defined
    # RunRecordV1.dataset_id / EvidenceBundleV1.dataset_id and
    # EmpiricalSourceManifestV1.dataset_identifier fields. SourceSnapshot IDs
    # and arbitrary metadata strings occupy different typed namespaces.
    source_refs: list[tuple[ReferenceKey, str, str]] = []
    run_fingerprints: dict[ReferenceKey, tuple[str, str]] = {}
    for doc in docs:
        if doc.kind == "run_record":
            for location, value in (("dataset_id", doc.raw.get("dataset_id")),):
                if isinstance(value, str) and value:
                    source_refs.append((ReferenceKey("EmpiricalSourceManifest.v1", "dataset_identifier", value), doc.relative_path, location))
            input_value = doc.raw.get("input")
            if isinstance(input_value, Mapping):
                value = input_value.get("dataset_id")
                if isinstance(value, str) and value:
                    source_refs.append((ReferenceKey("EmpiricalSourceManifest.v1", "dataset_identifier", value), doc.relative_path, "input/dataset_id"))
            allowed = {("", "dataset_id"), ("/input", "dataset_id")}
            add_unverifiable_refs(doc.raw, subject=doc.relative_path, allowed=allowed)
        elif doc.kind == "evidence_bundle":
            dataset_id = doc.raw.get("dataset_id")
            if isinstance(dataset_id, str) and dataset_id:
                source_refs.append((ReferenceKey("EmpiricalSourceManifest.v1", "dataset_identifier", dataset_id), doc.relative_path, "dataset_id"))
    for key, location, field_name in source_refs:
        candidates = source_catalog.get(key, [])
        if not candidates:
            ctx.add("unresolved_source_reference", f"{location}#/{field_name}", f"typed dataset reference {key.identifier!r} has no supplied EmpiricalSourceManifest.v1.dataset_identifier")
        elif len(candidates) > 1:
            ctx.add("ambiguous_source_reference", f"{location}#/{field_name}", f"dataset identity {key.identifier!r} is declared by multiple source manifests", "error")

    for doc in (item for item in docs if item.kind == "run_record"):
        run_id = doc.raw.get("run_id")
        input_value = doc.raw.get("input") if isinstance(doc.raw.get("input"), Mapping) else {}
        run_mode = _declared_origin_class(doc.raw.get("data_mode") or input_value.get("data_mode"))
        dataset_values = {value for value in (doc.raw.get("dataset_id"), input_value.get("dataset_id")) if isinstance(value, str) and value}
        for dataset_id in sorted(dataset_values):
            key = ReferenceKey("EmpiricalSourceManifest.v1", "dataset_identifier", dataset_id)
            candidates = source_catalog.get(key, [])
            if run_mode is None or len(candidates) != 1:
                continue
            source_mode = _declared_origin_class(candidates[0].raw.get("origin"))
            if source_mode is not None and source_mode != run_mode:
                ctx.add("source_data_mode_conflict", str(run_id), f"RunRecord origin class {run_mode!r} conflicts with EmpiricalSourceManifest.v1 origin class {source_mode!r} for dataset {dataset_id!r}")

    for doc in (item for item in docs if item.kind == "run_record"):
        input_value = doc.raw.get("input")
        if not isinstance(input_value, Mapping):
            continue
        for path, mapping in _walk_mappings_with_paths(input_value, "/input"):
            if mapping.get("source_version") is not None:
                ctx.add("source_version_unverifiable", f"{doc.relative_path}#{path}/source_version", "RunRecordV1 does not define a typed source-version reference, and SourceSnapshot metadata is not a version index; no stale-version join was attempted")
            if mapping.get("source_sha256") is not None:
                ctx.add("run_source_checksum_scope_unverifiable", f"{doc.relative_path}#{path}/source_sha256", "RunRecordV1 does not define a typed source-checksum scope; it is not compared with SourceSnapshot.source_sha256")

    for doc in source_docs:
        ctx.add("license_not_declared", doc.relative_path, "current empirical-source manifest schema has no typed license identity or reference field")

    run_docs = [doc for doc in docs if doc.kind == "run_record"]
    lineage_docs = [doc for doc in docs if doc.kind == "simulation_artifact_lineage"]
    runs_by_id: dict[ReferenceKey, list[_Document]] = {}
    for doc in run_docs:
        run_id = doc.raw.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            ctx.add("missing_run_identity", doc.relative_path, "run_id is required", "error")
            continue
        run_key = ReferenceKey("run_identity", "run_id", run_id)
        runs_by_id.setdefault(run_key, []).append(doc)
        config = doc.raw.get("config")
        input_data = doc.raw.get("input")
        config_basis = config if isinstance(config, Mapping) and config else (input_data if isinstance(input_data, Mapping) else {})
        input_basis = input_data if isinstance(input_data, Mapping) else {}
        try:
            config_fp = run_configuration_fingerprint(config_basis)
            input_fp = run_configuration_fingerprint(input_basis)
        except (TypeError, ValueError) as exc:
            ctx.add("invalid_configuration_fingerprint", run_id, str(exc), "error")
            continue
        run_fingerprints[run_key] = (config_fp, input_fp)
        declared_fingerprint = doc.raw.get("configuration_fingerprint")
        if declared_fingerprint is not None and declared_fingerprint != config_fp:
            ctx.add("stale_configuration_fingerprint", run_id, "RunRecord-declared configuration_fingerprint differs from its explicit config/input", "error")
    for run_key, copies in sorted(runs_by_id.items()):
        if len(copies) > 1:
            ctx.add("duplicate_run_id", run_key.identifier, f"{len(copies)} RunRecord documents declare the same run_id", "error")
    for doc in lineage_docs:
        provenance = doc.raw.get("provenance") if isinstance(doc.raw.get("provenance"), Mapping) else {}
        run_id = provenance.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            continue
        run_key = ReferenceKey("run_identity", "run_id", run_id)
        candidates = runs_by_id.get(run_key, [])
        if not candidates:
            ctx.add("unresolved_run_reference", doc.relative_path, f"lineage report run_id {run_id!r} has no explicit RunRecord")
            continue
        if len(candidates) != 1:
            continue
        run = candidates[0].raw
        expected_config, expected_input = run_fingerprints.get(run_key, (None, None))
        actual_config = provenance.get("configuration_fingerprint")
        actual_input = provenance.get("input_fingerprint")
        if actual_config is not None and expected_config != actual_config:
            ctx.add("stale_configuration_fingerprint", run_id, "lineage configuration fingerprint differs from the explicit RunRecord config/input")
        if actual_input is not None and expected_input != actual_input:
            ctx.add("input_fingerprint_mismatch", run_id, "lineage input fingerprint differs from the explicit RunRecord input")

    # RunRecordV1 does not define a canonical config ID/version contract. When
    # explicit IDs and pins happen to be present, compare only exact values to
    # an explicit ExperimentSpec/config declaration; never infer from content.
    declarations: dict[ReferenceKey, list[tuple[str | None, str | None, str]]] = {}
    run_pins: dict[ReferenceKey, list[tuple[str | None, str | None, str]]] = {}
    for doc in docs:
        if doc.kind != "run_record":
            continue
        run_id = doc.raw.get("run_id")
        if isinstance(run_id, str):
            for config_id, version, digest in _explicit_configuration_pins(doc.raw):
                run_pins.setdefault(config_id, []).append((version, digest, run_id))
    for record in ledger_records:
        if record.get("record_type") != "experiment_spec":
            continue
        for config_id, version, digest in _explicit_configuration_pins(record):
            declarations.setdefault(config_id, []).append((version, digest, str(record.get("record_id", "experiment_spec"))))
    for config_key, pinned_values in sorted(run_pins.items()):
        declared_values = declarations.get(config_key, [])
        if not declared_values:
            ctx.add("configuration_reference_unresolved", config_key.identifier, "RunRecord declares a configuration ID/version but no explicit ExperimentSpec configuration pin was supplied")
        for run_version, run_digest, run_id in pinned_values:
            for declared_version, declared_digest, experiment_id in declared_values:
                if (
                    (run_version is not None and declared_version is not None and run_version != declared_version)
                    or (run_digest is not None and declared_digest is not None and run_digest != declared_digest)
                ):
                    ctx.add(
                        "stale_configuration_version",
                        run_id,
                        f"RunRecord pin for configuration {config_key.identifier!r} differs from explicit ExperimentSpec {experiment_id!r}; this is a declared mismatch, not a selection of the current version",
                    )


def _declared_origin_class(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    if value in {"synthetic", "synthetic_demo", "synthetic_demonstration"}:
        return "synthetic"
    if value in {"empirical", "empirical_local", "local_empirical"}:
        return "empirical"
    return None


def _check_run_manifest_consistency(ctx: _Context, docs: list[_Document], ledger_records: list[dict[str, Any]]) -> None:
    run_docs: dict[ReferenceKey, list[_Document]] = {}
    manifest_docs: dict[ReferenceKey, list[_Document]] = {}
    for doc in docs:
        if doc.kind == "run_record" and isinstance(doc.raw.get("run_id"), str):
            key = ReferenceKey("run_identity", "run_id", doc.raw["run_id"])
            run_docs.setdefault(key, []).append(doc)
        if doc.kind == "integration_artifact_manifest":
            run_id = doc.raw.get("run_id")
            if isinstance(run_id, str):
                key = ReferenceKey("run_identity", "run_id", run_id)
                manifest_docs.setdefault(key, []).append(doc)
        if doc.kind == "simulation_artifact_lineage":
            provenance = doc.raw.get("provenance") if isinstance(doc.raw.get("provenance"), Mapping) else {}
            run_id = provenance.get("run_id")
            if isinstance(run_id, str):
                key = ReferenceKey("run_identity", "run_id", run_id)
                manifest_docs.setdefault(key, []).append(doc)

    for run_key, manifests in sorted(manifest_docs.items()):
        run_id = run_key.identifier
        if run_key not in run_docs:
            ctx.add("unresolved_run_reference", run_id, "output manifest declares a typed run_identity.run_id with no matching explicit RunRecordV1.run_id")
        if len(manifests) > 1:
            entries_by_path = ctx.output_entries_by_run.get(run_id, {})
            # Multiple manifests are allowed only when they make no contradictory path/hash claim.
            if not entries_by_path:
                ctx.add("duplicate_output_manifest", run_id, f"{len(manifests)} manifests have no verifiable entries")

    for run_key, runs in sorted(run_docs.items()):
        run_id = run_key.identifier
        if not manifest_docs.get(run_key):
            ctx.add("run_missing_output_manifest", run_id, "RunRecord has no explicitly supplied output manifest")
        if len(runs) != 1:
            continue
        artifacts = runs[0].raw.get("artifacts")
        if not isinstance(artifacts, Mapping):
            continue
        manifested = set(ctx.output_entries_by_run.get(run_id, {}))
        for key, value in artifacts.items():
            if not isinstance(value, str) or not value:
                continue
            result = _hash_file(ctx, value, subject=f"{run_id}:RunRecord.artifacts.{key}")
            if result is None:
                continue
            relative = result[2]
            if manifest_docs.get(run_key) and relative not in manifested:
                ctx.add("run_artifact_unmanifested", run_id, f"RunRecord artifact {relative!r} is not listed by its output manifest")

    for record in ledger_records:
        record_type = record.get("record_type")
        record_id = record.get("record_id", "unknown")
        if record_type == "run_record":
            run_id = record.get("run_record_id")
            if not isinstance(run_id, str) or not run_id:
                ctx.add("malformed_run_record_link", record_id, "run_record_id is required", "error")
                run_id = record_id
            experiment_id = record.get("experiment_id")
            if not isinstance(experiment_id, str) or not experiment_id:
                ctx.add("malformed_run_record_link", record_id, "experiment_id is required", "error")
            elif not any(item.get("record_type") == "experiment_spec" and item.get("experiment_id", item.get("record_id")) == experiment_id for item in ledger_records):
                ctx.add("unresolved_experiment_reference", record_id, f"RunRecordLink references absent ExperimentSpec {experiment_id!r}")
            expected_schema = record.get("run_record_schema_version")
            if not isinstance(expected_schema, str) or expected_schema not in RUN_RECORD_SCHEMA_VERSIONS:
                ctx.add("malformed_run_record_link", record_id, "run_record_schema_version is missing or unsupported", "error")
            run_status = record.get("run_status")
            if not isinstance(run_status, str) or not run_status:
                ctx.add("malformed_run_record_link", record_id, "run_status is required", "error")
            run_key = ReferenceKey("run_identity", "run_id", run_id) if isinstance(run_id, str) else None
            if run_key is None or run_key not in run_docs:
                ctx.add("unresolved_run_reference", record_id, f"ledger run reference {run_id!r} has no explicit RunRecord")
            else:
                for run_doc in run_docs[run_key]:
                    if expected_schema is not None and str(run_doc.raw.get("schema_version")) != str(expected_schema):
                        ctx.add("run_schema_version_mismatch", run_id, f"ledger expects {expected_schema!r}, RunRecord declares {run_doc.raw.get('schema_version')!r}", "error")
                # The main schema requires this digest but does not document whether it hashes raw
                # bytes or canonical RunRecord JSON. Do not guess at a verification scope.
                run_hash = record.get("run_record_sha256")
                if _is_sha256(run_hash):
                    ctx.add("run_record_checksum_scope_unverifiable", run_id, "RunRecordLink.run_record_sha256 has no documented byte/canonicalization scope", "warning")
                else:
                    ctx.add("malformed_run_record_link", record_id, "run_record_sha256 is required and must be a 64-character SHA-256 hex digest", "error")
        elif record_type == "artifact_manifest":
            run_id = record.get("run_record_id")
            run_key = ReferenceKey("run_identity", "run_id", run_id) if isinstance(run_id, str) else None
            if isinstance(run_id, str) and (run_key is None or not manifest_docs.get(run_key)):
                ctx.add("ledger_manifest_without_output", record_id, f"ledger artifact manifest references run {run_id!r}, but no output manifest was supplied")
            payload_artifacts = record.get("artifacts")
            if isinstance(payload_artifacts, Mapping) and isinstance(run_id, str):
                actual_entries = ctx.output_entries_by_run.get(run_id, {})
                for path, metadata in payload_artifacts.items():
                    if not isinstance(path, str) or not isinstance(metadata, Mapping):
                        continue
                    try:
                        _, normalized = _resolve_relative(ctx.root, path)
                    except (OSError, ValueError, RuntimeError) as exc:
                        ctx.add("unsafe_or_missing_reference", record_id, f"ledger artifact path {path!r}: {exc}", "error")
                        continue
                    matched = actual_entries.get(normalized)
                    declared = metadata.get("sha256")
                    if matched is None:
                        ctx.add("ledger_artifact_unmatched", record_id, f"{normalized!r} is not in the run's output manifest")
                    elif isinstance(declared, str) and declared.lower() != matched["sha256"].lower():
                        ctx.add("artifact_manifest_checksum_conflict", record_id, f"{normalized!r} differs between ledger and file manifest", "error")
        elif record_type == "validation_report":
            for manifest_id in record.get("artifact_manifest_ids", []) if isinstance(record.get("artifact_manifest_ids"), list) else []:
                if not any(item.get("record_type") == "artifact_manifest" and item.get("artifact_manifest_id", item.get("record_id")) == manifest_id for item in ledger_records):
                    ctx.add("unresolved_validation_manifest", record_id, f"validation report references absent artifact manifest {manifest_id!r}")


def _check_gate_claims(ctx: _Context, docs: list[_Document], ledger_records: list[dict[str, Any]], events: list[dict[str, Any]]) -> None:
    """Do not treat free-form event payload IDs as record references.

    ResearchCycleLedger currently types event identity and status, but its
    payload is an unrestricted mapping without a typed target-reference
    contract. Consequently no gate event can establish that its status belongs
    to a particular record or artifact.
    """
    def check(subject: str, status: Any, cycle_id: str | None = None) -> None:
        if not isinstance(status, str) or status.strip().upper() not in _POSITIVE_GATE_WORDS:
            return
        has_gate_event = any(
            event.get("event_type") in _GATE_EVENT_TYPES
            and (cycle_id is None or event.get("cycle_id") == cycle_id)
            for event in events
        )
        if has_gate_event:
            detail = (
                f"status {status!r} cannot be linked to a validation_outcome/release_review event: "
                "the current event contract has no typed target-reference field"
            )
        else:
            detail = f"status {status!r} has no matching validation_outcome/release_review event"
        ctx.add("unsupported_status_claim", subject, detail, "warning")

    for record in ledger_records:
        record_id = record.get("record_id")
        record_type = record.get("record_type")
        if isinstance(record_id, str) and isinstance(record_type, str):
            for field_name in ("status", "validation_status", "decision", "gate_status", "run_status"):
                check(f"{record_id}.{record_type}#/{field_name}", record.get(field_name), record.get("cycle_id"))
    for doc in docs:
        for field_name in ("status", "decision", "validation_status", "gate_status", "verdict"):
            check(f"{doc.relative_path}#/{field_name}", doc.raw.get(field_name))


def _inventory_root(ctx: _Context) -> None:
    if not ctx.root.exists():
        return
    count = 0
    def on_walk_error(exc: OSError) -> None:
        filename = getattr(exc, "filename", None)
        subject = str(filename) if filename else "."
        try:
            subject = Path(subject).relative_to(ctx.root).as_posix()
        except ValueError:
            subject = "."
        ctx.add("inventory_read_error", subject, str(exc), "error")

    for current, directories, filenames in os.walk(ctx.root, topdown=True, onerror=on_walk_error, followlinks=False):
        current_path = Path(current)
        current_rel = current_path.relative_to(ctx.root).as_posix()
        if current_rel == ".":
            current_rel = ""
        skip_tree = any(current_rel == prefix or current_rel.startswith(prefix + "/") for prefix in ctx.source_tree_prefixes)
        if skip_tree:
            directories[:] = []
            continue
        kept_dirs: list[str] = []
        for name in sorted(directories):
            path = current_path / name
            rel = path.relative_to(ctx.root).as_posix()
            if _is_link(path):
                ctx.add("symlink_rejected", rel, "directory symlinks and junctions are not followed", "error")
                continue
            if any(rel == prefix or rel.startswith(prefix + "/") for prefix in ctx.source_tree_prefixes):
                # local_root is a declared input subtree; do not enumerate or read its contents.
                continue
            kept_dirs.append(name)
        directories[:] = kept_dirs
        for name in sorted(filenames):
            path = current_path / name
            relative = path.relative_to(ctx.root).as_posix()
            if _is_link(path):
                ctx.add("symlink_rejected", relative, "file symlinks and junctions are not followed", "error")
                continue
            try:
                info = path.lstat()
            except OSError as exc:
                ctx.add("inventory_read_error", relative, str(exc), "error")
                continue
            if not stat.S_ISREG(info.st_mode):
                continue
            count += 1
            if count > ctx.limits.max_files:
                ctx.add("file_count_limit_exceeded", relative, f"inventory exceeds {ctx.limits.max_files} files", "error")
                directories[:] = []
                return
            if info.st_size > ctx.limits.max_artifact_bytes:
                ctx.add("artifact_size_limit_exceeded", relative, f"{info.st_size} > {ctx.limits.max_artifact_bytes}", "error")
                continue
            ctx.inventory.append({"relative_path": relative, "size_bytes": info.st_size})


def _finalize_findings(ctx: _Context) -> list[Finding]:
    # A finding's identity is its exact code, subject, detail, and severity.
    return sorted(set(ctx.findings))


def audit_provenance(
    artifact_root: str | Path,
    input_manifests: Sequence[str | Path],
    *,
    limits: AuditLimits | None = None,
) -> dict[str, Any]:
    """Join supplied producer documents without discovering producer inputs.

    ``input_manifests`` are existing JSON outputs identified by their embedded
    schema, not by filename. Every file reference is resolved beneath
    ``artifact_root`` and every referenced byte stream is bounded and hashed.
    """
    selected_limits = limits or AuditLimits()
    root = _root_path(artifact_root)
    if not input_manifests:
        raise AuditInputError("at least one explicit input manifest is required")
    ctx = _Context(root=root, limits=selected_limits)
    seen_declared_paths: set[str] = set()
    for raw_path in input_manifests:
        doc = _load_document(ctx, raw_path)
        if doc is None:
            continue
        if doc.relative_path in seen_declared_paths:
            ctx.add("duplicate_declared_manifest", doc.relative_path, "same input manifest was supplied more than once")
            continue
        seen_declared_paths.add(doc.relative_path)
        ctx.input_paths.add(doc.relative_path)
        ctx.documents.append(doc)
    docs = sorted(ctx.documents, key=lambda item: item.relative_path)
    for doc in docs:
        _report_unverifiable_fields(ctx, doc.raw, doc.relative_path)

    # Verify every explicitly declared, supported output manifest.
    for doc in docs:
        if doc.kind in {"integration_artifact_manifest", "simulation_artifact_lineage"}:
            _entries_from_manifest(ctx, doc)
        elif doc.kind == "evidence_bundle":
            _verify_evidence_bundle(ctx, doc)

    artifact_paths_by_hash: dict[str, set[str]] = {}
    for entries in ctx.output_entries_by_run.values():
        for path, entry in entries.items():
            artifact_paths_by_hash.setdefault(entry["sha256"], set()).add(path)
    for digest, paths_for_hash in sorted(artifact_paths_by_hash.items()):
        if len(paths_for_hash) > 1:
            ctx.add("duplicate_artifact_content", digest, f"the same raw-byte SHA-256 is declared at {sorted(paths_for_hash)}")

    bundles_by_id: dict[str, int] = {}
    for doc in docs:
        if doc.kind == "evidence_bundle" and isinstance(doc.raw.get("bundle_id"), str):
            bundle_id = doc.raw["bundle_id"]
            bundles_by_id[bundle_id] = bundles_by_id.get(bundle_id, 0) + 1
    for bundle_id, count in sorted(bundles_by_id.items()):
        if count > 1:
            ctx.add("duplicate_bundle_id", bundle_id, f"{count} evidence bundle documents declare this bundle_id", "error")

    ledger_exports: list[dict[str, Any]] = []
    for doc in docs:
        if doc.kind == "research_cycle_export":
            parsed = _verify_ledger_export(ctx, doc)
            if parsed is not None:
                cycle = doc.raw["cycle"]
                parsed["parent_cycle_id"] = cycle.get("parent_cycle_id")
                ledger_exports.append(parsed)

    ledger_records, ledger_events = _ledger_refs(ctx, ledger_exports)
    _check_source_and_config_links(ctx, docs, ledger_records)
    _check_run_manifest_consistency(ctx, docs, ledger_records)
    _check_gate_claims(ctx, docs, ledger_records, ledger_events)

    _inventory_root(ctx)
    declared_or_referenced = ctx.input_paths | ctx.referenced_paths
    orphan_paths = sorted(
        item["relative_path"]
        for item in ctx.inventory
        if item["relative_path"] not in declared_or_referenced
        and not any(item["relative_path"].startswith(prefix + "/") for prefix in ctx.source_tree_prefixes)
    )
    for path in orphan_paths:
        ctx.add("orphan_artifact", path, "regular file in the explicit artifact root is not referenced by a supplied manifest")

    schema_gaps = [
        {
            "field": "source_license",
            "status": "not_typed_on_current_main",
            "detail": "SourceSnapshot has no typed license field and EmpiricalSourceManifest.v1 does not define a license-record relationship; license_id/license_ref strings are reported unverifiable and never cross-joined.",
        },
        {
            "field": "origin_equivalence",
            "status": "partially_classifiable_on_current_main",
            "detail": "The source-manifest schema declares external_solver and unavailable origins, but neither can be equated to the auditor's synthetic/empirical comparison classes; they are reported UNVERIFIABLE for origin joins.",
        },
        {
            "field": "source_snapshot_checksum_scope",
            "status": "not_documented_on_current_main",
            "detail": "SourceSnapshot validates source_sha256 as hex but does not document whether it covers raw source bytes, normalized text, or an excerpt; the audit verifies format and does not hash source_uri.",
        },
        {
            "field": "run_record_input_checksum_scope",
            "status": "not_typed_on_current_main",
            "detail": "RunRecordV1 has no typed input-source checksum field; arbitrary input.source_sha256 values are not compared with SourceSnapshot hashes.",
        },
        {
            "field": "run_record_source_version_reference",
            "status": "not_typed_on_current_main",
            "detail": "RunRecordV1 has no typed source-version reference and SourceSnapshot.metadata is not a version index; source-version mismatch checks are intentionally not inferred.",
        },
        {
            "field": "empirical_source_manifest_checksum",
            "status": "not_typed_on_current_main",
            "detail": "EmpiricalSourceManifest.v1 has no source_checksum field or documented checksum scope; such extension values are not verified or interpreted.",
        },
        {
            "field": "remote_source_retrieval",
            "status": "not_performed",
            "detail": "Declared remote source URLs are never fetched; remote content identity remains unverifiable unless an existing in-root SourceSnapshot byte reference is supplied.",
        },
        {
            "field": "run_record_checksum_scope",
            "status": "not_documented_on_current_main",
            "detail": "RunRecordLink.run_record_sha256 is required, but current docs do not specify raw-byte versus canonical-JSON scope; the auditor does not guess.",
        },
        {
            "field": "configuration_identity",
            "status": "partially_typed_on_current_main",
            "detail": "RunRecordV1 has input fields but no canonical configuration ID/version field; fingerprints are compared only when an existing lineage report explicitly carries them.",
        },
        {
            "field": "evidence_bundle_artifact_registry",
            "status": "external_registry_not_joined",
            "detail": "EvidenceBundleV1 carries registry artifact IDs and embedded decisions, but this audit does not load or treat those embedded decisions as an authoritative external registry snapshot.",
        },
        {
            "field": "source_pack_manifest",
            "status": "unsupported_until_schema_is_on_main",
            "detail": "The source-pack manifest contract associated with open PR #391 is not present in the checked-in main schemas and is not integrated; an unrecognized document is reported UNVERIFIABLE without inferred joins.",
        },
        {
            "field": "source_snapshot_manifest_reference",
            "status": "not_typed_on_current_main",
            "detail": "SourceSnapshot has no typed reference to EmpiricalSourceManifest.v1; metadata strings are reported unverifiable rather than joined to dataset identity.",
        },
        {
            "field": "gate_event_target_reference",
            "status": "not_typed_on_current_main",
            "detail": "ResearchCycleLedger event payloads are free-form and define no typed target-reference contract; gate event status cannot be attached to an arbitrary record ID.",
        },
    ]
    findings = _finalize_findings(ctx)
    errors = any(item.severity == "error" for item in findings)
    incomplete = any(item.severity == "warning" for item in findings)
    status = "INVALID" if errors else ("INCOMPLETE" if incomplete else "CLEAN")
    report: dict[str, Any] = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "status": status,
        "scope": "structural_lineage_only",
        "scientific_validation": False,
        "artifact_root": ".",
        "limits": {
            "max_manifest_bytes": selected_limits.max_manifest_bytes,
            "max_artifact_bytes": selected_limits.max_artifact_bytes,
            "max_total_bytes": selected_limits.max_total_bytes,
            "max_files": selected_limits.max_files,
            "bytes_read_or_hashed": ctx.total_bytes,
        },
        "input_manifests": [
            {
                "relative_path": doc.relative_path,
                "schema_kind": doc.kind,
                "schema_version": doc.raw.get("schema_version") or doc.raw.get("schema"),
                "sha256_raw_bytes": doc.raw_sha256,
                "size_bytes": doc.size_bytes,
            }
            for doc in docs
        ],
        "verified_output_entries": [
            {"run_id": run_id, **entry}
            for run_id, entries in sorted(ctx.output_entries_by_run.items())
            for _, entry in sorted(entries.items())
        ],
        "orphan_artifacts": orphan_paths,
        "findings": [item.to_dict() for item in findings],
        "schema_gaps": schema_gaps,
        "checksum_rules": {
            "research_cycle_export_records_events": "SHA-256 of compact sorted UTF-8 JSON; ensure_ascii=false; allow_nan=false; record checksum excludes checksum field.",
            "integration_artifact_manifest_entries": "SHA-256 of referenced file bytes; size_bytes is checked against observed bytes.",
            "source_snapshot_source_sha256": "UNVERIFIED: current SourceSnapshot schema does not document checksum scope; only its SHA-256 format is validated.",
            "simulation_artifact_report": "SHA-256 of finite sorted-key indented JSON (indent=2) plus one LF, excluding report_sha256.",
            "simulation_artifact_configuration_fingerprint": "SHA-256 of compact sorted-key JSON, ensure_ascii=true, allow_nan=false; matches tools.simulation_artifacts.extractor.",
            "evidence_bundle_id": "First 16 hex characters of SHA-256 over compact sorted-key UTF-8 JSON identity fields; bundle ID is not an artifact checksum.",
            "run_record_link_checksum": "UNVERIFIED: current schema does not document checksum scope.",
        },
        "not_established": [
            "source authenticity",
            "data-use rights or legal clearance",
            "cohort or participant identity",
            "physical or statistical model correctness",
            "scientific truth, biological validity, or causation",
        ],
        "note": "A clean structural audit is not scientific validation, evidence promotion, data-rights clearance, cohort identity verification, model correctness, or a truth/causation decision.",
    }
    report["report_sha256"] = sha256_json(report)
    return report
