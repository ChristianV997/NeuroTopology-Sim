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

_DEFAULT_PRODUCTION_ROOTS = (".",)
_EXCLUDED_PARTS = {".git", "__pycache__", ".pytest_cache", ".serena", ".venv", "venv", "node_modules", "dist", "build", "tests", "docs", "generated_artifacts"}
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


def _allowlisted(
    path: str,
    function: str | None,
    operation: str,
    policy: DataAccessPolicy,
    *,
    qualified_function: str | None = None,
) -> bool:
    candidates = {value for value in (function, qualified_function) if value}
    for item in policy.approved_adapters:
        if path == item.get("path"):
            symbols = item.get("symbols", [])
            # Match an explicitly declared short symbol or its complete
            # enclosing symbol.  Do not split a qualified declaration and
            # thereby authorize an unrelated method with the same basename.
            if not symbols or bool(candidates.intersection(str(symbol) for symbol in symbols)):
                return operation in {"bounded", "metadata"}
    for item in policy.approved_metadata_operations:
        if path != item.get("path"):
            continue
        symbols = item.get("symbols", [])
        symbol = item.get("symbol")
        if (symbol and symbol in candidates) or (symbols and bool(candidates.intersection(str(item) for item in symbols))):
            return operation == "metadata"
    for item in policy.approved_lazy_readers:
        if path != item.get("path"):
            continue
        symbols = item.get("symbols", [])
        if symbols and bool(candidates.intersection(str(item) for item in symbols)):
            return operation == "lazy"
    return False


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


def _enclosing_symbol_name(node: ast.AST, parents: Mapping[int, ast.AST]) -> str | None:
    """Return the exact class/function symbol containing ``node``.

    For example, a call inside ``BoundedS3ObjectStore.fetch_object`` is
    represented as that qualified symbol, not merely ``fetch_object``.  This
    prevents a registration for one adapter method from approving another
    method in the same file.
    """
    names: list[str] = []
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        names.append(node.name)
    current = parents.get(id(node))
    while current is not None:
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.append(current.name)
        current = parents.get(id(current))
    return ".".join(reversed(names)) or None


def _enclosing_class(node: ast.AST, parents: Mapping[int, ast.AST]) -> ast.ClassDef | None:
    current = parents.get(id(node))
    while current is not None:
        if isinstance(current, ast.ClassDef):
            return current
        current = parents.get(id(current))
    return None


def _scope_nodes(
    node: ast.AST,
    parents: Mapping[int, ast.AST],
    function_node: ast.FunctionDef | ast.AsyncFunctionDef | None,
) -> list[ast.AST]:
    """Use the method's class scope for adapter methods, otherwise its function."""
    class_node = _enclosing_class(node, parents)
    if class_node is not None:
        return [class_node]
    return [function_node] if function_node is not None else [node]


def _ast_text(scope: Iterable[ast.AST]) -> str:
    """Collect executable AST identifiers/constants, excluding comments."""
    values: list[str] = []
    for root in scope:
        for node in ast.walk(root):
            if isinstance(node, ast.Name):
                values.append(node.id)
            elif isinstance(node, ast.Attribute):
                values.append(node.attr)
            elif isinstance(node, ast.keyword) and node.arg is not None:
                values.append(node.arg)
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                values.append(node.value)
    return " ".join(values).lower()


def _has_false_network_default(function_node: ast.FunctionDef | ast.AsyncFunctionDef | None) -> bool:
    if function_node is None:
        return False
    positional = list(function_node.args.posonlyargs) + list(function_node.args.args)
    positional_defaults = dict(zip(positional[-len(function_node.args.defaults):], function_node.args.defaults)) if function_node.args.defaults else {}
    for argument in (*positional, *function_node.args.kwonlyargs):
        if argument.arg.lower() not in {"allow_network", "network_enabled", "download_enabled", "network"}:
            continue
        default = positional_defaults.get(argument) if argument in positional_defaults else dict(zip(function_node.args.kwonlyargs, function_node.args.kw_defaults)).get(argument)
        return isinstance(default, ast.Constant) and default.value is False
    return False


def _has_call(scope: Iterable[ast.AST], *, function_name: str, keyword: str | None = None) -> bool:
    for root in scope:
        for node in ast.walk(root):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute) or node.func.attr != function_name:
                continue
            if keyword is None or any(item.arg == keyword for item in node.keywords):
                return True
    return False


def _calls(scope: Iterable[ast.AST], *, function_name: str) -> list[ast.Call]:
    calls: list[ast.Call] = []
    for root in scope:
        for node in ast.walk(root):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == function_name:
                calls.append(node)
    return calls


def _registration_for(path: str, qualified_function: str | None, policy: DataAccessPolicy) -> Mapping[str, Any] | None:
    if not qualified_function:
        return None
    for item in policy.approved_adapters:
        if path != item.get("path"):
            continue
        if qualified_function in {str(symbol) for symbol in item.get("symbols", [])} and item.get("registration"):
            return item
    return None


def _registration_findings(
    node: ast.AST,
    *,
    registration: Mapping[str, Any],
    function_node: ast.FunctionDef | ast.AsyncFunctionDef | None,
    parents: Mapping[int, ast.AST],
    add: Any,
) -> None:
    """Validate registered adapter controls using executable AST structure."""
    profile = registration.get("control_profile")
    scope = _scope_nodes(node, parents, function_node)
    text = _ast_text(scope)

    def require(condition: bool, rule: str, remediation: str) -> None:
        if not condition:
            add(node, rule, "error", "policy_control", remediation)

    require(
        _has_false_network_default(function_node),
        "NETWORK_ENABLED_BY_DEFAULT",
        "Registered bounded adapters must expose allow_network=False and require explicit opt-in.",
    )
    if profile == "s3_store":
        get_object_calls = _calls(scope, function_name="get_object")
        require(
            bool(get_object_calls) and all(any(item.arg == "Range" for item in call.keywords) for call in get_object_calls),
            "UNAUTHORIZED_BOUNDED_TRANSFER",
            "Every registered S3 data read must pass an explicit Range keyword; full-object calls are rejected.",
        )
        require(
            _has_call(scope, function_name="head_object") and "contentlength" in text and _has_call(scope, function_name="_object_uri"),
            "MISSING_EXPECTED_OBJECT_IDENTITY",
            "Bind the explicit source object identity and read size from head_object ContentLength before transfer.",
        )
        require(
            any(token in text for token in ("checksum", "sha256", "sha-256", "etag", "digest")) and "unknown" in text,
            "MISSING_CHECKSUM",
            "Represent checksum verification or explicit checksum unknown state.",
        )
        require(
            any(token in text for token in ("max_cache_bytes", "cache_budget", "metadata_max_bytes")),
            "MISSING_CACHE_BOUND",
            "Declare an explicit cache or metadata byte budget.",
        )
        require(
            _has_call(scope, function_name="_evict_for") or any(token in text for token in ("eviction", "lru")),
            "MISSING_EVICTION",
            "Declare observable bounded-cache eviction.",
        )
        require(
            _has_call(scope, function_name="_contained") or "is_relative_to" in text or "commonpath" in text,
            "OUTPUT_ROOT_ESCAPE",
            "Contain output paths under the explicit cache/output root.",
        )
        require(
            not any(_calls(scope, function_name=name) for name in ("download_file", "download_fileobj", "copyfileobj")),
            "UNBOUNDED_REMOTE_MATERIALIZATION",
            "Registered S3 adapters must not use full-object or unbounded copy helpers.",
        )
    elif profile == "delegated_s3_wrapper":
        metadata_wrapper = function_node is not None and function_node.name in {
            "load_mdd_complete_subjects",
            "load_group_labels",
        }
        explicit_bound = (
            "metadata_max_bytes" in text
            if metadata_wrapper
            else "max_cache_bytes" in text and "chunk_size" in text
        )
        require(
            explicit_bound,
            "MISSING_CACHE_BOUND",
            "Delegated callers must pass explicit cache/chunk bounds, or metadata_max_bytes for bounded metadata.",
        )
        require(
            "boundeds3objectstore" in text and ("fetch_object" in text or "read_text_metadata" in text),
            "UNAUTHORIZED_BOUNDED_TRANSFER",
            "Delegated callers must use the registered BoundedS3ObjectStore methods.",
        )
        require(
            not any(_calls(scope, function_name=name) for name in ("download_file", "download_fileobj", "get_object", "copyfileobj")),
            "UNAUTHORIZED_BOTO3_FULL_OBJECT",
            "Delegated callers must not bypass the bounded S3 adapter with direct transfer calls.",
        )


def _function_node(node: ast.AST, parents: Mapping[int, ast.AST]) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    current = parents.get(id(node))
    while current is not None:
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return current
        current = parents.get(id(current))
    return None


def _function_source(function_node: ast.FunctionDef | ast.AsyncFunctionDef | None, source_lines: list[str]) -> str:
    if function_node is None:
        return ""
    start = max(0, function_node.lineno - 1)
    end = min(len(source_lines), getattr(function_node, "end_lineno", function_node.lineno))
    return "\n".join(source_lines[start:end])


def _contains_marker(text: str, markers: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(marker in lowered for marker in markers)


def _unsafe_control_findings(
    node: ast.Call,
    *,
    function_source: str,
    function: str | None,
    function_node: ast.FunctionDef | ast.AsyncFunctionDef | None,
    approved: bool,
    add: Any,
) -> None:
    """Report absent runtime controls on unapproved transfer/materialization code.

    This is intentionally conservative.  The scanner cannot prove that a
    runtime path is safe; it can only make missing declarations fail closed.
    """
    if approved:
        return
    func_name = node.func.attr if isinstance(node.func, ast.Attribute) else node.func.id if isinstance(node.func, ast.Name) else ""
    function_lower = (function or "").lower()
    transfer_like = func_name in {"download_file", "download_fileobj", "get_object", "copyfileobj"} or any(
        token in function_lower for token in ("download", "fetch", "transfer", "material", "sync", "cache")
    )
    if not transfer_like:
        return
    anchor = function_node or node
    if not _contains_marker(function_source, ("range", "byte_range", "max_bytes", "chunk", "cache_budget", "memory_budget", "size_limit")):
        add(anchor, "MISSING_CACHE_BOUND", "error", "policy_control", "Declare an explicit byte/cache bound before remote bytes can be materialized.", source_text=None)
    if not _contains_marker(function_source, ("checksum", "sha256", "sha-256", "etag", "digest")):
        add(anchor, "MISSING_CHECKSUM", "error", "policy_control", "Require a source checksum or record checksum availability as unknown; never fabricate one.", source_text=None)
    if not _contains_marker(function_source, ("evict", "eviction", "lru", "cache_policy")):
        add(anchor, "MISSING_EVICTION", "warning", "policy_control", "Declare observable bounded-cache eviction and preserve active leases.", source_text=None)


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
            # A parent traversal in executable source is still a policy
            # concern even when it is not part of a shell command.
            if re.search(r"(?:[\"']\.\.[\"']|\.\.[\\/])", line) and not _exception_for(path, "OUTPUT_ROOT_ESCAPE", policy):
                findings.append(PolicyFinding(path, line_number, "OUTPUT_ROOT_ESCAPE", "error", "path_containment", "Resolve output/cache candidates and reject paths outside the explicit root.", False, line.strip()))
            continue
        normalized = re.sub(r"[\[\],\"'()]", " ", line)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        for pattern, rule, severity, category, remediation in patterns:
            match = re.search(pattern, line) or re.search(pattern, normalized)
            if match and (line_number, rule) not in emitted and not _exception_for(path, rule, policy):
                emitted.add((line_number, rule))
                findings.append(PolicyFinding(path, line_number, rule, severity, category, remediation, False, line.strip()))
        if re.search(r"(?:[\"']\.\.[\"']|\.\.[\\/])", line) and (line_number, "OUTPUT_ROOT_ESCAPE") not in emitted and not _exception_for(path, "OUTPUT_ROOT_ESCAPE", policy):
            emitted.add((line_number, "OUTPUT_ROOT_ESCAPE"))
            findings.append(PolicyFinding(path, line_number, "OUTPUT_ROOT_ESCAPE", "error", "path_containment", "Resolve output/cache candidates and reject paths outside the explicit root.", False, line.strip()))
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
    source_lines = source.splitlines()
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
        qualified_function = _enclosing_symbol_name(node, parents)
        function_node = _function_node(node, parents)
        function_source = _function_source(function_node, source_lines)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            defaults = list(node.args.defaults)
            positional = list(node.args.posonlyargs) + list(node.args.args)
            first_default = len(positional) - len(defaults)
            for index, argument in enumerate(positional):
                if index < first_default or argument.arg.lower() not in {"allow_network", "network_enabled", "download_enabled", "network"}:
                    continue
                default = defaults[index - first_default]
                if isinstance(default, ast.Constant) and default.value is True:
                    add(node, "NETWORK_ENABLED_BY_DEFAULT", "critical", "network_policy", "Make network/data access opt-in with a default of False.", source_text=ast.get_source_segment(source, node))
            for argument, default in zip(node.args.kwonlyargs, node.args.kw_defaults):
                if argument.arg.lower() in {"allow_network", "network_enabled", "download_enabled", "network"} and isinstance(default, ast.Constant) and default.value is True:
                    add(node, "NETWORK_ENABLED_BY_DEFAULT", "critical", "network_policy", "Make network/data access opt-in with a default of False.", source_text=ast.get_source_segment(source, node))
            registration = _registration_for(relative, qualified_function, policy)
            if registration is not None:
                _registration_findings(
                    node,
                    registration=registration,
                    function_node=node,
                    parents=parents,
                    add=add,
                )
            continue
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div) and isinstance(node.right, ast.Constant) and node.right.value == "..":
            add(node, "OUTPUT_ROOT_ESCAPE", "error", "path_containment", "Resolve output/cache candidates and reject paths outside the explicit root.", source_text=ast.get_source_segment(source, node))
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in {"join", "joinpath"} and any(isinstance(argument, ast.Constant) and argument.value == ".." for argument in node.args):
            add(node, "OUTPUT_ROOT_ESCAPE", "error", "path_containment", "Resolve output/cache candidates and reject paths outside the explicit root.", source_text=ast.get_source_segment(source, node))
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            modules = [alias.name for alias in node.names]
            direct_http = any(module == "requests" or module.startswith(("urllib", "httpx")) for module in modules)
            # Imports are not themselves data access.  If a retrieval call is
            # made, its enclosing symbol is checked below.  In particular, do
            # not use a filename-only exemption for a module containing one
            # approved function.
            if direct_http and function is not None and not _allowlisted(
                relative,
                function,
                "metadata",
                policy,
                qualified_function=qualified_function,
            ) and not _allowlisted(
                relative,
                function,
                "bounded",
                policy,
                qualified_function=qualified_function,
            ) and not _allowlisted(
                relative,
                function,
                "lazy",
                policy,
                qualified_function=qualified_function,
            ):
                add(node, "UNAUTHORIZED_DIRECT_HTTP_RETRIEVAL", "error", "remote_reader", "Use an approved metadata-only or bounded adapter with explicit network opt-in.", source_text="import " + ", ".join(modules))
        if not isinstance(node, ast.Call):
            continue
        text = _constant_text(node)
        if isinstance(node, ast.Call):
            argument_text = " ".join(_constant_text(argument) for argument in node.args)
            text = " ".join(part for part in (text, argument_text, ast.get_source_segment(source, node) or "") if part)
        lowered = text.lower()
        approved_metadata = _allowlisted(relative, function, "metadata", policy, qualified_function=qualified_function)
        approved_bounded = _allowlisted(relative, function, "bounded", policy, qualified_function=qualified_function)
        approved_lazy = _allowlisted(relative, function, "lazy", policy, qualified_function=qualified_function)
        func_name = ""
        qualified_name = ""
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
            qualified_name = func_name
        elif isinstance(node.func, ast.Attribute):
            func_name = node.func.attr
            qualified_name = _qualified_name(node.func)
        if func_name == "add_argument" and any(token in lowered for token in ("network", "download")):
            default_true = any(keyword.arg == "default" and isinstance(keyword.value, ast.Constant) and keyword.value.value is True for keyword in node.keywords)
            if default_true:
                add(node, "NETWORK_ENABLED_BY_DEFAULT", "critical", "network_policy", "Make network/data access opt-in with a default of False.", source_text=ast.get_source_segment(source, node))
        if func_name == "getenv" and len(node.args) >= 2:
            key = _constant_text(node.args[0]).lower()
            default = _constant_text(node.args[1]).lower()
            if any(token in key for token in ("network", "download")) and default in {"1", "true", "yes", "on"}:
                add(node, "NETWORK_ENABLED_BY_DEFAULT", "critical", "network_policy", "Make network/data access opt-in with a default of False.", source_text=ast.get_source_segment(source, node))
        http_call = func_name == "urlopen" or qualified_name.lower().startswith(("urllib.", "requests.", "httpx."))
        if http_call:
            if not approved_metadata and not approved_bounded and not approved_lazy:
                add(node, "UNAUTHORIZED_DIRECT_HTTP_RETRIEVAL", "error", "remote_reader", "Use an approved metadata-only or bounded adapter with explicit network opt-in.", source_text=ast.get_source_segment(source, node))
        if func_name in {"download_file", "download_fileobj"}:
            if not approved_bounded:
                add(node, "UNAUTHORIZED_BOTO3_FULL_OBJECT", "critical", "full_dataset_download", "Replace direct full-object boto3 transfer with an approved bounded adapter.", source_text=ast.get_source_segment(source, node))
        if func_name == "get_object":
            has_range = any(keyword.arg == "Range" for keyword in node.keywords)
            if not approved_metadata and not approved_lazy and (not has_range or not approved_bounded):
                add(node, "UNBOUNDED_REMOTE_MATERIALIZATION" if not has_range else "UNAUTHORIZED_BOUNDED_TRANSFER", "critical" if not has_range else "error", "full_dataset_download" if not has_range else "remote_reader", "Declare a byte range, manifest size, checksum, and approved adapter before reading object bytes.", source_text=ast.get_source_segment(source, node))
        if func_name == "copyfileobj" and not approved_bounded:
            add(node, "UNBOUNDED_REMOTE_MATERIALIZATION", "error", "unbounded_materialization", "Read bounded chunks into a partial file and verify completion before rename.", source_text=ast.get_source_segment(source, node))
        receiver = _qualified_name(node.func.value) if isinstance(node.func, ast.Attribute) else ""
        remote_receiver = receiver.rsplit(".", 1)[-1].lower() in {"response", "resp", "body", "stream", "remote", "payload"}
        if func_name == "read" and remote_receiver and not node.args and not approved_metadata and not approved_bounded and not approved_lazy:
            add(node, "UNBOUNDED_REMOTE_MATERIALIZATION", "error", "unbounded_materialization", "Read bounded chunks into a partial file and verify completion before rename.", source_text=ast.get_source_segment(source, node))
        if func_name in {"run", "Popen", "call", "check_call", "check_output", "system"} and any(token in lowered for token in ("openneuro download", "aws s3 cp", "aws s3 sync", " wget ", " curl ")):
            if "openneuro download" in lowered:
                add(node, "UNAUTHORIZED_OPENNEURO_DOWNLOAD", "critical", "full_dataset_download", "Replace with manifest-first planning and an approved bounded adapter.", source_text=ast.get_source_segment(source, node))
            elif "aws s3 cp" in lowered or "aws s3 sync" in lowered:
                add(node, "UNAUTHORIZED_AWS_FULL_TRANSFER", "critical", "full_dataset_download", "Use the approved chunk-cache adapter; do not execute aws s3 cp/sync for data.", source_text=ast.get_source_segment(source, node))
            else:
                add(node, "UNAUTHORIZED_SHELL_TRANSFER", "critical", "full_dataset_download", "Do not launch download shells; use the manifest-first bounded adapter.", source_text=ast.get_source_segment(source, node))
        if isinstance(node, ast.Call):
            _unsafe_control_findings(
                node,
                function_source=function_source,
                function=function,
                function_node=function_node,
                approved=approved_metadata or approved_bounded or approved_lazy,
                add=add,
            )

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
