"""Read-only AST/static scanner for data-access policy violations."""

from __future__ import annotations

import ast
import hashlib
import json
import re
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Mapping

from .policy import DEFAULT_POLICY, DataAccessPolicy

SCHEMA_VERSION = "NeuroTopology.DataAccessPolicyAudit.v1"

_DEFAULT_PRODUCTION_ROOTS = ("tools", "scripts", "dataset_acquisition", "adapters", "pipelines")
_EXCLUDED_PARTS = {".git", "__pycache__", ".pytest_cache", "tests", "docs", "generated_artifacts"}
_SELF_PATHS = {"tools/data_access/policy_enforcement", "scripts/validate_data_access_policy.py"}


@dataclass(frozen=True)
class PolicyFinding:
    file: str
    line: int
    rule: str
    severity: str
    category: str
    remediation: str
    approved: bool = False
    source: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "line": self.line,
            "rule": self.rule,
            "severity": self.severity,
            "category": self.category,
            "remediation": self.remediation,
            "approved": self.approved,
            "source": self.source,
        }


@dataclass
class PolicyReport:
    schema_version: str
    repository_root: str
    scanned_files: list[str]
    findings: list[PolicyFinding]
    policy: DataAccessPolicy
    network_calls_performed: bool = False
    compliant: bool = False
    migration_inventory: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        findings = [finding.to_dict() for finding in self.findings]
        return {
            "schema_version": self.schema_version,
            "repository_root": self.repository_root,
            "scanned_files": list(self.scanned_files),
            "scanned_file_count": len(self.scanned_files),
            "findings": findings,
            "finding_count": len(findings),
            "legacy_violation_count": sum(1 for item in findings if not item["approved"]),
            "compliant": self.compliant,
            "network_calls_performed": self.network_calls_performed,
            "policy": self.policy.to_dict(),
            "migration_inventory": list(self.migration_inventory),
        }

    def to_json(self, *, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, indent=indent, allow_nan=False) + "\n"

    def human_summary(self) -> str:
        counts: dict[str, int] = defaultdict(int)
        for item in self.findings:
            counts[item.severity] += 1
        status = "COMPLIANT" if self.compliant else "BLOCKED_LEGACY_VIOLATIONS"
        count_text = ", ".join(f"{key}={counts[key]}" for key in sorted(counts)) or "none"
        return f"{status}: scanned={len(self.scanned_files)} findings={len(self.findings)} severities={count_text} network_calls=0"


def _relative(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def _allowlisted(path: str, function: str | None, operation: str, policy: DataAccessPolicy) -> bool:
    for item in policy.approved_adapters:
        if path == item.get("path"):
            symbols = item.get("symbols", [])
            if not symbols or function is None or any(function == str(symbol).split(".")[-1] for symbol in symbols):
                return operation in {"bounded", "metadata"}
    for item in policy.approved_metadata_operations:
        if path != item.get("path"):
            continue
        symbols = item.get("symbols", [])
        symbol = item.get("symbol")
        if (symbol and function == symbol) or (symbols and function in symbols):
            return operation == "metadata"
    return False


def _path_allowlisted(path: str, policy: DataAccessPolicy) -> bool:
    return any(path == item.get("path") for item in (*policy.approved_adapters, *policy.approved_metadata_operations))


def _exception_for(path: str, rule: str, policy: DataAccessPolicy) -> bool:
    exception = (policy.reviewed_exceptions or {}).get(path)
    return bool(exception and exception.get("rule") == rule and exception.get("reviewer") and exception.get("justification"))


def _constant_text(node: ast.AST) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, (ast.List, ast.Tuple)):
        return " ".join(_constant_text(item) for item in node.elts)
    if isinstance(node, ast.JoinedStr):
        return " ".join(_constant_text(item.value) for item in node.values if isinstance(item, ast.Constant))
    return ""


def _qualified_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        prefix = _qualified_name(node.value)
        return f"{prefix}.{node.attr}" if prefix else node.attr
    return ""


def _parents(tree: ast.AST) -> dict[int, ast.AST]:
    parents: dict[int, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parents[id(child)] = parent
    return parents


def _function_name(node: ast.AST, parents: Mapping[int, ast.AST]) -> str | None:
    current = parents.get(id(node))
    while current is not None:
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return current.name
        current = parents.get(id(current))
    return None


def _finding(
    path: str,
    line: int,
    rule: str,
    severity: str,
    category: str,
    remediation: str,
    *,
    approved: bool = False,
    source: str | None = None,
    policy: DataAccessPolicy,
) -> PolicyFinding | None:
    if _exception_for(path, rule, policy):
        return None
    return PolicyFinding(path, max(1, line), rule, severity, category, remediation, approved, source)


def _scan_source_patterns(source: str, path: str, policy: DataAccessPolicy) -> list[PolicyFinding]:
    findings: list[PolicyFinding] = []
    emitted: set[tuple[int, str]] = set()
    patterns = (
        (r"(?i)\bopenneuro\s+download\b", "UNAUTHORIZED_OPENNEURO_DOWNLOAD", "critical", "full_dataset_download", "Replace with manifest-first planning and an approved bounded adapter."),
        (r"(?i)\baws\s+s3\s+(?:cp|sync)\b", "UNAUTHORIZED_AWS_FULL_TRANSFER", "critical", "full_dataset_download", "Use the approved chunk-cache adapter; do not execute aws s3 cp/sync for data."),
        (r"(?i)\b(?:wget|curl)\s+(?:https?://|s3://)", "UNAUTHORIZED_SHELL_TRANSFER", "critical", "full_dataset_download", "Remove shell downloads and route through an approved bounded adapter."),
        (r"(?i)\bdatalad\s+install\b", "UNBOUNDED_REMOTE_MATERIALIZATION", "error", "full_dataset_download", "Declare a manifest and bounded transfer plan before any materialization."),
    )
    for line_number, line in enumerate(source.splitlines(), 1):
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        code_context = re.search(r"(?i)subprocess|popen|check_call|check_output|os\.system|system\(|^\s*(?:command|cmd|args)\s*=", line)
        if path.lower().endswith((".sh", ".ps1", ".bat", ".cmd")):
            code_context = True
        if not code_context:
            continue
        normalized = re.sub(r"[\[\],\"'()]", " ", line)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        for pattern, rule, severity, category, remediation in patterns:
            match = re.search(pattern, line) or re.search(pattern, normalized)
            if match and (line_number, rule) not in emitted and not _exception_for(path, rule, policy):
                emitted.add((line_number, rule))
                findings.append(PolicyFinding(path, line_number, rule, severity, category, remediation, False, line.strip()))
    return findings


def scan_file(path: str | Path, *, repository_root: str | Path, policy: DataAccessPolicy = DEFAULT_POLICY) -> list[PolicyFinding]:
    """Scan one Python production file without importing or executing it."""
    file_path = Path(path)
    root = Path(repository_root)
    relative = _relative(file_path, root)
    if relative in _SELF_PATHS or relative.startswith("tools/data_access/policy_enforcement/"):
        return []
    try:
        source = file_path.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as exc:
        return [PolicyFinding(relative, 1, "POLICY_READ_FAILURE", "critical", "scanner_failure", f"Make the production source readable: {exc}", False, None)]
    findings = _scan_source_patterns(source, relative, policy)
    if not relative.lower().endswith(".py"):
        return sorted(findings, key=lambda item: (item.file, item.line, item.rule))
    try:
        tree = ast.parse(source, filename=relative)
    except SyntaxError as exc:
        findings.append(PolicyFinding(relative, exc.lineno or 1, "POLICY_PARSE_FAILURE", "critical", "scanner_failure", "Repair the syntax or add a reviewed exception; policy cannot pass an unparseable production path.", False, str(exc)))
        return findings

    parents = _parents(tree)
    seen = {(item.line, item.rule) for item in findings}

    def add(node: ast.AST, rule: str, severity: str, category: str, remediation: str, *, approved: bool = False, source_text: str | None = None) -> None:
        key = (getattr(node, "lineno", 1), rule)
        if key in seen:
            return
        if _exception_for(relative, rule, policy):
            return
        seen.add(key)
        findings.append(PolicyFinding(relative, key[0], rule, severity, category, remediation, approved, source_text))

    for node in ast.walk(tree):
        function = _function_name(node, parents)
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            modules = [alias.name for alias in node.names]
            direct_http = any(module == "requests" or module.startswith(("urllib", "httpx")) for module in modules)
            if direct_http and not _path_allowlisted(relative, policy) and not _allowlisted(relative, function, "metadata", policy):
                add(node, "UNAUTHORIZED_DIRECT_HTTP_RETRIEVAL", "error", "remote_reader", "Use an approved metadata-only or bounded adapter with explicit network opt-in.", source_text="import " + ", ".join(modules))
        if not isinstance(node, ast.Call):
            continue
        text = _constant_text(node)
        if isinstance(node, ast.Call):
            argument_text = " ".join(_constant_text(argument) for argument in node.args)
            text = " ".join(part for part in (text, argument_text, ast.get_source_segment(source, node) or "") if part)
        lowered = text.lower()
        approved_metadata = _allowlisted(relative, function, "metadata", policy)
        approved_bounded = _allowlisted(relative, function, "bounded", policy)
        func_name = ""
        qualified_name = ""
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
            qualified_name = func_name
        elif isinstance(node.func, ast.Attribute):
            func_name = node.func.attr
            qualified_name = _qualified_name(node.func)
        http_call = func_name == "urlopen" or qualified_name.lower().startswith(("urllib.", "requests.", "httpx."))
        if http_call:
            if not approved_metadata and not approved_bounded:
                add(node, "UNAUTHORIZED_DIRECT_HTTP_RETRIEVAL", "error", "remote_reader", "Use an approved metadata-only or bounded adapter with explicit network opt-in.", source_text=ast.get_source_segment(source, node))
        if func_name in {"download_file", "download_fileobj"}:
            if not approved_bounded:
                add(node, "UNAUTHORIZED_BOTO3_FULL_OBJECT", "critical", "full_dataset_download", "Replace direct full-object boto3 transfer with an approved bounded adapter.", source_text=ast.get_source_segment(source, node))
        if func_name == "get_object":
            has_range = any(keyword.arg == "Range" for keyword in node.keywords)
            if not has_range or not approved_bounded:
                add(node, "UNBOUNDED_REMOTE_MATERIALIZATION" if not has_range else "UNAUTHORIZED_BOUNDED_TRANSFER", "critical" if not has_range else "error", "full_dataset_download" if not has_range else "remote_reader", "Declare a byte range, manifest size, checksum, and approved adapter before reading object bytes.", source_text=ast.get_source_segment(source, node))
        if func_name == "copyfileobj" and not approved_bounded:
            add(node, "UNBOUNDED_REMOTE_MATERIALIZATION", "error", "unbounded_materialization", "Read bounded chunks into a partial file and verify completion before rename.", source_text=ast.get_source_segment(source, node))
        receiver = _qualified_name(node.func.value) if isinstance(node.func, ast.Attribute) else ""
        remote_receiver = receiver.rsplit(".", 1)[-1].lower() in {"response", "resp", "body", "stream", "remote", "payload"}
        if func_name == "read" and remote_receiver and not node.args and not approved_metadata and not approved_bounded:
            add(node, "UNBOUNDED_REMOTE_MATERIALIZATION", "error", "unbounded_materialization", "Read bounded chunks into a partial file and verify completion before rename.", source_text=ast.get_source_segment(source, node))
        if func_name in {"run", "Popen", "call", "check_call", "check_output", "system"} and any(token in lowered for token in ("openneuro download", "aws s3 cp", "aws s3 sync", " wget ", " curl ")):
            if "openneuro download" in lowered:
                add(node, "UNAUTHORIZED_OPENNEURO_DOWNLOAD", "critical", "full_dataset_download", "Replace with manifest-first planning and an approved bounded adapter.", source_text=ast.get_source_segment(source, node))
            elif "aws s3 cp" in lowered or "aws s3 sync" in lowered:
                add(node, "UNAUTHORIZED_AWS_FULL_TRANSFER", "critical", "full_dataset_download", "Use the approved chunk-cache adapter; do not execute aws s3 cp/sync for data.", source_text=ast.get_source_segment(source, node))
            else:
                add(node, "UNAUTHORIZED_SHELL_TRANSFER", "critical", "full_dataset_download", "Do not launch download shells; use the manifest-first bounded adapter.", source_text=ast.get_source_segment(source, node))

    return sorted(findings, key=lambda item: (item.file, item.line, item.rule))


def _iter_files(root: Path, paths: Iterable[str | Path] | None) -> list[Path]:
    candidates: list[Path] = []
    if paths is None:
        paths = _DEFAULT_PRODUCTION_ROOTS
    for item in paths:
        candidate = root / item if not Path(item).is_absolute() else Path(item)
        if candidate.is_file() and candidate.suffix.lower() in {".py", ".sh", ".ps1", ".bat", ".cmd"}:
            candidates.append(candidate)
        elif candidate.is_dir():
            candidates.extend(sorted(path for path in candidate.rglob("*") if path.is_file() and path.suffix.lower() in {".py", ".sh", ".ps1", ".bat", ".cmd"} and not (_EXCLUDED_PARTS & set(path.parts))))
    unique = {}
    for path in candidates:
        relative = _relative(path, root)
        if relative in _SELF_PATHS or relative.startswith("tools/data_access/policy_enforcement/"):
            continue
        unique[relative] = path
    return [unique[key] for key in sorted(unique)]


def _inventory(findings: Iterable[PolicyFinding]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for finding in findings:
        item = grouped.setdefault(finding.rule, {"rule": finding.rule, "severity": finding.severity, "files": [], "count": 0, "remediation": finding.remediation})
        item["count"] += 1
        if finding.file not in item["files"]:
            item["files"].append(finding.file)
    return [grouped[key] for key in sorted(grouped)]


def scan_paths(paths: Iterable[str | Path], *, repository_root: str | Path, policy: DataAccessPolicy = DEFAULT_POLICY) -> PolicyReport:
    root = Path(repository_root).resolve()
    files = _iter_files(root, paths)
    findings: list[PolicyFinding] = []
    for path in files:
        findings.extend(scan_file(path, repository_root=root, policy=policy))
    findings.sort(key=lambda item: (item.file, item.line, item.rule))
    return PolicyReport(SCHEMA_VERSION, str(root), [_relative(path, root) for path in files], findings, policy, False, not findings, _inventory(findings))


def scan_repository(repository_root: str | Path, *, paths: Iterable[str | Path] | None = None, policy: DataAccessPolicy = DEFAULT_POLICY) -> PolicyReport:
    return scan_paths(_DEFAULT_PRODUCTION_ROOTS if paths is None else paths, repository_root=repository_root, policy=policy)
