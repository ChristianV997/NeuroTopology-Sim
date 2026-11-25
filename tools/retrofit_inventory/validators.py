"""Fail-closed Phase 3 validators for the retrofit inventory.

Functions return error lists or raise ``ValueError``. Failures are never
downgraded to warnings.

Inventory labels and snapshots are **not scientific evidence**. Validators
never emit scientific claim status ``PASS`` from inventory alone. An
``empirical`` artifact label is a heuristic, not a scientific pass.
"""

from __future__ import annotations

import ast
import json
import math
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple, Union

from .models import (
    ARTIFACT_LABEL_EMPIRICAL,
    ARTIFACT_LABEL_VALUES,
    ENTRY_KIND_VALUES,
    HASH_POLICY_CONTENT_SHA256,
    HASH_POLICY_SIZE_PATH_V1,
    INVENTORY_SCHEMA_VERSION,
    KIND_TEXT,
    WORKTREE_KIND_BRANCH,
    WORKTREE_KIND_WORKTREE,
    InventorySnapshot,
)
from .tool_sources import (
    ADOPTION_RECOMMENDATIONS,
    INTEGRATION_MODES,
    REQUIRED_KEYS,
    load_tool_sources,
    validate_tool_source_entry,
)

Pathish = Union[str, Path]
Rowish = Union[Mapping[str, Any], Any]

HASH_POLICIES = frozenset(
    {HASH_POLICY_CONTENT_SHA256, HASH_POLICY_SIZE_PATH_V1}
)
WORKTREE_KIND_VALUES = frozenset({WORKTREE_KIND_BRANCH, WORKTREE_KIND_WORKTREE})

HEX_RE = re.compile(r"^[0-9a-fA-F]+$")

# Patterns assembled so this module source does not contain the literal
# needle strings (a later tree scan must still fail on real fixtures).
_SECRET_SPECS: Tuple[Tuple[str, re.Pattern[str]], ...] = (
    ("api_key=", re.compile("api_key" + r"\s*=", re.IGNORECASE)),
    ("AKIA", re.compile("AKIA" + r"[0-9A-Z]{8,}")),
    ("BEGIN PRIVATE KEY", re.compile("BEGIN " + "PRIVATE " + "KEY")),
    ("password=", re.compile("password" + r"\s*=", re.IGNORECASE)),
    ("secret_key=", re.compile("secret_key" + r"\s*=", re.IGNORECASE)),
)

NETWORK_IMPORT_DENYLIST = frozenset(
    {
        "requests",
        "urllib",
        "urllib2",
        "urllib3",
        "httpx",
        "aiohttp",
        "httplib",
        "http.client",
    }
)
MARKETOS_IMPORT_DENYLIST = frozenset({"marketos", "MarketOS"})

NOTEBOOKLM_TOOL_ID = "notebooklm-mcp"
NOTEBOOKLM_INTEGRATION_MODE = "experimental"
NOTEBOOKLM_ADOPTION = "experimental_only"
EXPECTED_REAL_TOOL_SOURCE_COUNT = 15

# Inventory is never scientific evidence. This is the only status validators
# may attach to a snapshot. ``PASS`` is forbidden.
INVENTORY_CLAIM_STATUS_NOT_EVIDENCE = "not_evidence"
FORBIDDEN_SCIENTIFIC_CLAIM_STATUSES = frozenset({"PASS", "PASSED", "pass", "passed"})
_CLAIM_STATUS_KEYS = frozenset(
    {
        "claim_status",
        "scientific_status",
        "scientific_claim_status",
        "verdict",
        "evidence_status",
        "hypothesis_verdict",
        "pci_status",
    }
)

SNAPSHOT_REQUIRED_FIELDS = (
    "repo_root",
    "commit_sha",
    "files",
    "worktrees_and_branches",
    "artifacts",
    "governance_files",
    "dependencies",
    "overlaps",
    "schema_version",
)
FILE_REQUIRED_FIELDS = ("path", "kind", "size", "content_hash", "hash_policy")
ARTIFACT_REQUIRED_FIELDS = ("path", "label")
GOVERNANCE_REQUIRED_FIELDS = ("path", "category")
DEPENDENCY_REQUIRED_FIELDS = ("name", "source_path", "ecosystem")
WORKTREE_REQUIRED_FIELDS = ("kind", "name")
OVERLAP_REQUIRED_FIELDS = ("paths", "reason")

_PACKAGE_DIR = Path(__file__).resolve().parent


def inventory_scientific_claim_status(
    snapshot: Optional[InventorySnapshot] = None,
) -> str:
    """Return the only allowed scientific-claim status for inventory.

    Inventory is not evidence. This never returns ``PASS``, including when
    every artifact is labelled empirical.
    """

    _ = snapshot  # labels on the snapshot cannot promote a claim
    return INVENTORY_CLAIM_STATUS_NOT_EVIDENCE


def inventory_is_scientific_evidence(
    snapshot: Optional[InventorySnapshot] = None,
) -> bool:
    """Inventory never counts as scientific evidence."""

    _ = snapshot
    return False


def empirical_label_is_scientific_pass(label: str) -> bool:
    """An empirical inventory label is never a scientific PASS."""

    _ = label
    return False


def inventory_claim_record(snapshot: Optional[InventorySnapshot] = None) -> Dict[str, Any]:
    """Deterministic claim metadata. Never includes scientific PASS."""

    return {
        "inventory_is_evidence": inventory_is_scientific_evidence(snapshot),
        "scientific_claim_status": inventory_scientific_claim_status(snapshot),
        "empirical_label_is_pass": False,
        "schema_version": (
            snapshot.schema_version if snapshot is not None else INVENTORY_SCHEMA_VERSION
        ),
    }


def _row_get(row: Rowish, key: str, default: Any = None) -> Any:
    if isinstance(row, Mapping):
        return row.get(key, default)
    return getattr(row, key, default)


def _as_mapping(row: Rowish) -> Dict[str, Any]:
    if isinstance(row, Mapping):
        return dict(row)
    if hasattr(row, "to_dict"):
        return dict(row.to_dict())
    if hasattr(row, "__dict__"):
        return {
            key: value
            for key, value in vars(row).items()
            if not key.startswith("_")
        }
    raise TypeError(f"cannot view row as mapping: {type(row)!r}")


def _is_nonneg_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _is_finite_number(value: Any) -> bool:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return False
    return math.isfinite(float(value))


def _missing_required(row: Rowish, keys: Sequence[str], *, prefix: str) -> List[str]:
    errors: List[str] = []
    mapping = _as_mapping(row) if not isinstance(row, Mapping) else row
    for key in keys:
        if key not in mapping:
            errors.append(f"{prefix}: missing required field: {key}")
            continue
        value = mapping[key]
        if value is None:
            errors.append(f"{prefix}: required field {key} is None")
        elif isinstance(value, str) and not value.strip():
            errors.append(f"{prefix}: required field {key} is empty")
    return errors


def find_secret_pattern_hits(text: str) -> List[str]:
    """Return secret-pattern names found in ``text`` (empty means clean)."""

    hits: List[str] = []
    for name, pattern in _SECRET_SPECS:
        if pattern.search(text):
            hits.append(name)
    return hits


def find_secrets_in_text(text: str, *, location: str) -> List[str]:
    return [
        f"{location}: secret pattern {name!r} is forbidden"
        for name in find_secret_pattern_hits(text)
    ]


def find_secrets_in_value(value: Any, *, location: str) -> List[str]:
    errors: List[str] = []
    if isinstance(value, str):
        errors.extend(find_secrets_in_text(value, location=location))
    elif isinstance(value, Mapping):
        for key, item in value.items():
            errors.extend(
                find_secrets_in_value(item, location=f"{location}.{key}")
            )
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            errors.extend(
                find_secrets_in_value(item, location=f"{location}[{index}]")
            )
    return errors


def validate_integration_mode(mode: Any) -> List[str]:
    """Fail closed unless ``mode`` is one of ``INTEGRATION_MODES``."""

    if not isinstance(mode, str) or not mode.strip():
        return ["integration_mode must be a non-empty string"]
    if mode not in INTEGRATION_MODES:
        allowed = ", ".join(sorted(INTEGRATION_MODES))
        return [f"integration_mode {mode!r} is not one of: {allowed}"]
    return []


def validate_hash_fields(
    content_hash: Any,
    hash_policy: Any,
    *,
    prefix: str,
) -> List[str]:
    errors: List[str] = []
    if not isinstance(content_hash, str) or not content_hash.strip():
        errors.append(f"{prefix}: content_hash must be a non-empty hex string")
    elif not HEX_RE.fullmatch(content_hash):
        errors.append(f"{prefix}: content_hash must be hex, got {content_hash!r}")
    if not isinstance(hash_policy, str) or hash_policy not in HASH_POLICIES:
        allowed = ", ".join(sorted(HASH_POLICIES))
        errors.append(f"{prefix}: hash_policy must be one of: {allowed}")
    return errors


def _has_null_byte(value: str) -> bool:
    return "\x00" in value


def _has_dotdot(value: str) -> bool:
    if ".." in Path(value).parts:
        return True
    normalized = value.replace("\\", "/")
    return (
        normalized == ".."
        or normalized.startswith("../")
        or "/../" in normalized
        or normalized.endswith("/..")
    )


def _is_absolute_path(value: str) -> bool:
    if not value:
        return False
    if value.startswith("/") or value.startswith("\\"):
        return True
    if len(value) >= 2 and value[0].isalpha() and value[1] == ":":
        return True
    return Path(value).is_absolute()


def _escapes_repo_root(rel: str) -> bool:
    """True when a relative path logically walks above the root."""

    depth = 0
    for part in Path(rel.replace("\\", "/")).parts:
        if part in ("", "."):
            continue
        if part == "..":
            depth -= 1
            if depth < 0:
                return True
            continue
        depth += 1
    return False


def validate_path_safety(
    path: Any,
    *,
    prefix: str,
    allow_absolute: bool = False,
    require_relative: bool = True,
) -> List[str]:
    """Reject absolute escapes, ``..`` traversal, and null bytes."""

    errors: List[str] = []
    if not isinstance(path, str) or not path.strip():
        errors.append(f"{prefix}: path must be a non-empty string")
        return errors
    if _has_null_byte(path):
        errors.append(f"{prefix}: path contains a null byte")
    if _has_dotdot(path) or _escapes_repo_root(path):
        errors.append(f"{prefix}: path traversal ('..') is forbidden: {path!r}")
    absolute = _is_absolute_path(path)
    if absolute and not allow_absolute:
        errors.append(f"{prefix}: absolute path escape is forbidden: {path!r}")
    if require_relative and not allow_absolute and absolute:
        errors.append(f"{prefix}: path must be relative to repo_root: {path!r}")
    return errors


def validate_finite_numeric_fields(
    row: Rowish,
    *,
    prefix: str,
    size_required: bool = True,
    mtime_optional: bool = True,
) -> List[str]:
    errors: List[str] = []
    size = _row_get(row, "size", None)
    if size is None:
        if size_required:
            errors.append(f"{prefix}: size is required and must be an int >= 0")
    elif not _is_nonneg_int(size):
        errors.append(f"{prefix}: size must be a finite int >= 0, got {size!r}")

    if "mtime" in _as_mapping(row) or hasattr(row, "mtime"):
        mtime = _row_get(row, "mtime", None)
        if mtime is None:
            if not mtime_optional:
                errors.append(f"{prefix}: mtime must be a finite number")
        elif not _is_finite_number(mtime):
            errors.append(f"{prefix}: mtime must be a finite number, got {mtime!r}")
    return errors


def validate_file_entry(entry: Rowish, *, index: int = 0) -> List[str]:
    prefix = f"files[{index}]"
    errors = _missing_required(entry, FILE_REQUIRED_FIELDS, prefix=prefix)
    errors.extend(validate_path_safety(_row_get(entry, "path"), prefix=prefix))
    kind = _row_get(entry, "kind")
    if kind is not None and kind not in ENTRY_KIND_VALUES:
        errors.append(f"{prefix}: kind must be one of {ENTRY_KIND_VALUES}, got {kind!r}")
    errors.extend(validate_finite_numeric_fields(entry, prefix=prefix))
    errors.extend(
        validate_hash_fields(
            _row_get(entry, "content_hash"),
            _row_get(entry, "hash_policy"),
            prefix=prefix,
        )
    )
    return errors


def validate_artifact_entry(entry: Rowish, *, index: int = 0) -> List[str]:
    prefix = f"artifacts[{index}]"
    errors = _missing_required(entry, ARTIFACT_REQUIRED_FIELDS, prefix=prefix)
    path = _row_get(entry, "path")
    if path is None or (isinstance(path, str) and not path.strip()):
        errors.append(f"{prefix}: missing path")
    else:
        errors.extend(validate_path_safety(path, prefix=prefix))
    label = _row_get(entry, "label")
    if label not in ARTIFACT_LABEL_VALUES:
        errors.append(
            f"{prefix}: label must be one of {ARTIFACT_LABEL_VALUES}, got {label!r}"
        )
    schema_id = _row_get(entry, "schema_id", None)
    if schema_id is not None and not isinstance(schema_id, str):
        errors.append(f"{prefix}: schema_id must be a string or null, got {type(schema_id).__name__}")
    elif isinstance(schema_id, str) and not schema_id.strip():
        errors.append(f"{prefix}: schema_id must be a non-empty string when present")
    mapping = _as_mapping(entry)
    if "size" in mapping:
        errors.extend(
            validate_finite_numeric_fields(entry, prefix=prefix, size_required=True)
        )
    if label == ARTIFACT_LABEL_EMPIRICAL and empirical_label_is_scientific_pass(label):
        errors.append(f"{prefix}: empirical label must not be treated as scientific PASS")
    return errors


def validate_governance_entry(entry: Rowish, *, index: int = 0) -> List[str]:
    prefix = f"governance_files[{index}]"
    errors = _missing_required(entry, GOVERNANCE_REQUIRED_FIELDS, prefix=prefix)
    errors.extend(validate_path_safety(_row_get(entry, "path"), prefix=prefix))
    errors.extend(validate_finite_numeric_fields(entry, prefix=prefix, size_required=True))
    return errors


def validate_dependency_entry(entry: Rowish, *, index: int = 0) -> List[str]:
    prefix = f"dependencies[{index}]"
    errors = _missing_required(entry, DEPENDENCY_REQUIRED_FIELDS, prefix=prefix)
    errors.extend(
        validate_path_safety(_row_get(entry, "source_path"), prefix=f"{prefix}.source_path")
    )
    extra = _row_get(entry, "extra", None)
    if extra is not None and not isinstance(extra, str):
        errors.append(f"{prefix}: extra must be a string or null")
    return errors


def validate_worktree_entry(entry: Rowish, *, index: int = 0) -> List[str]:
    prefix = f"worktrees_and_branches[{index}]"
    errors = _missing_required(entry, WORKTREE_REQUIRED_FIELDS, prefix=prefix)
    kind = _row_get(entry, "kind")
    if kind is not None and kind not in WORKTREE_KIND_VALUES:
        errors.append(f"{prefix}: kind must be one of {sorted(WORKTREE_KIND_VALUES)}")
    path = _row_get(entry, "path", None)
    if path is not None:
        errors.extend(
            validate_path_safety(
                path,
                prefix=f"{prefix}.path",
                allow_absolute=True,
                require_relative=False,
            )
        )
    sha = _row_get(entry, "commit_sha", None)
    if sha is not None:
        if not isinstance(sha, str) or not sha.strip() or not HEX_RE.fullmatch(sha):
            errors.append(f"{prefix}: commit_sha must be hex when present")
    return errors


def validate_overlap_finding(entry: Rowish, *, index: int = 0) -> List[str]:
    prefix = f"overlaps[{index}]"
    errors = _missing_required(entry, OVERLAP_REQUIRED_FIELDS, prefix=prefix)
    paths = _row_get(entry, "paths")
    if not isinstance(paths, (list, tuple)) or not paths:
        errors.append(f"{prefix}: paths must be a non-empty list")
        return errors
    seen: set[str] = set()
    for path_index, path in enumerate(paths):
        errors.extend(
            validate_path_safety(path, prefix=f"{prefix}.paths[{path_index}]")
        )
        if isinstance(path, str):
            if path in seen:
                errors.append(f"{prefix}: duplicate path {path!r}")
            seen.add(path)
    return errors


def validate_duplicate_ownership(
    snapshot: InventorySnapshot,
    tool_rows: Optional[Sequence[Mapping[str, Any]]] = None,
) -> List[str]:
    """Duplicate paths, overlap-path repeats, and duplicate tool ids are errors."""

    errors: List[str] = []

    def _dup_paths(rows: Sequence[Any], key: str, label: str) -> None:
        seen: Dict[str, int] = {}
        for index, row in enumerate(rows):
            path = _row_get(row, key)
            if not isinstance(path, str) or not path:
                continue
            if path in seen:
                errors.append(
                    f"duplicate ownership: {label} path {path!r} "
                    f"claimed at index {seen[path]} and {index}"
                )
            else:
                seen[path] = index

    _dup_paths(snapshot.files, "path", "file")
    _dup_paths(snapshot.artifacts, "path", "artifact")
    _dup_paths(snapshot.governance_files, "path", "governance")

    overlap_owners: Dict[str, List[int]] = {}
    for index, finding in enumerate(snapshot.overlaps):
        paths = list(finding.paths)
        if len(paths) != len(set(paths)):
            errors.append(f"overlaps[{index}]: duplicate paths in overlap finding")
        for path in set(paths):
            overlap_owners.setdefault(path, []).append(index)

    claimed = snapshot.report_fields.get("claimed_owners")
    if isinstance(claimed, (list, tuple)):
        owner_by_path: Dict[str, str] = {}
        for index, claim in enumerate(claimed):
            if not isinstance(claim, Mapping):
                errors.append(f"report_fields.claimed_owners[{index}] must be a mapping")
                continue
            path = claim.get("path")
            owner = claim.get("owner")
            if not isinstance(path, str) or not path:
                errors.append(f"report_fields.claimed_owners[{index}]: missing path")
                continue
            if not isinstance(owner, str) or not owner:
                errors.append(f"report_fields.claimed_owners[{index}]: missing owner")
                continue
            previous = owner_by_path.get(path)
            if previous is not None and previous != owner:
                errors.append(
                    f"overlapping claimed owners for path {path!r}: "
                    f"{previous!r} and {owner!r}"
                )
            elif previous == owner:
                errors.append(
                    f"duplicate claimed owner {owner!r} for path {path!r}"
                )
            else:
                owner_by_path[path] = owner

    if tool_rows is not None:
        seen_ids: Dict[str, int] = {}
        for index, row in enumerate(tool_rows):
            tool_id = row.get("id")
            if not isinstance(tool_id, str):
                continue
            if tool_id in seen_ids:
                errors.append(
                    f"duplicate tool id {tool_id!r} "
                    f"(first at tools[{seen_ids[tool_id]}], also tools[{index}])"
                )
            else:
                seen_ids[tool_id] = index
    return errors


def validate_no_scientific_pass(
    snapshot: InventorySnapshot,
    extra_payloads: Optional[Sequence[Any]] = None,
) -> List[str]:
    """Fail if inventory-derived payloads claim scientific PASS."""

    errors: List[str] = []
    status = inventory_scientific_claim_status(snapshot)
    if status in FORBIDDEN_SCIENTIFIC_CLAIM_STATUSES:
        errors.append(
            "inventory validators must not emit scientific claim status PASS"
        )
    if inventory_is_scientific_evidence(snapshot):
        errors.append("inventory must not be treated as scientific evidence")
    record = inventory_claim_record(snapshot)
    if record.get("scientific_claim_status") in FORBIDDEN_SCIENTIFIC_CLAIM_STATUSES:
        errors.append("inventory_claim_record must not use scientific PASS")
    if record.get("inventory_is_evidence") is True:
        errors.append("inventory_claim_record must not mark inventory as evidence")

    payloads: List[Any] = [snapshot.report_fields, record]
    if extra_payloads:
        payloads.extend(extra_payloads)

    def _walk(value: Any, location: str) -> None:
        if isinstance(value, Mapping):
            for key, item in value.items():
                key_text = str(key)
                if key_text in _CLAIM_STATUS_KEYS and isinstance(item, str):
                    if item in FORBIDDEN_SCIENTIFIC_CLAIM_STATUSES:
                        errors.append(
                            f"{location}.{key_text}: scientific PASS is forbidden "
                            "from inventory alone"
                        )
                _walk(item, f"{location}.{key_text}")
        elif isinstance(value, (list, tuple)):
            for index, item in enumerate(value):
                _walk(item, f"{location}[{index}]")
        elif isinstance(value, str) and value in FORBIDDEN_SCIENTIFIC_CLAIM_STATUSES:
            if location.endswith("scientific_claim_status") or location.endswith(
                "verdict"
            ):
                errors.append(f"{location}: scientific PASS is forbidden")

    for payload in payloads:
        _walk(payload, "payload")

    for index, artifact in enumerate(snapshot.artifacts):
        if artifact.label == ARTIFACT_LABEL_EMPIRICAL:
            if empirical_label_is_scientific_pass(artifact.label):
                errors.append(
                    f"artifacts[{index}]: empirical label must not imply scientific PASS"
                )
    return errors


def validate_snapshot_required_fields(snapshot: InventorySnapshot) -> List[str]:
    errors = _missing_required(snapshot, SNAPSHOT_REQUIRED_FIELDS, prefix="snapshot")
    if snapshot.schema_version != INVENTORY_SCHEMA_VERSION:
        errors.append(
            f"snapshot.schema_version must be {INVENTORY_SCHEMA_VERSION!r}, "
            f"got {snapshot.schema_version!r}"
        )
    if not isinstance(snapshot.repo_root, str) or not snapshot.repo_root.strip():
        errors.append("snapshot.repo_root must be a non-empty string")
    elif _has_null_byte(snapshot.repo_root) or _has_dotdot(snapshot.repo_root):
        errors.append(f"snapshot.repo_root is unsafe: {snapshot.repo_root!r}")
    if not isinstance(snapshot.commit_sha, str) or not snapshot.commit_sha.strip():
        errors.append("snapshot.commit_sha must be a non-empty string")
    elif not HEX_RE.fullmatch(snapshot.commit_sha):
        errors.append("snapshot.commit_sha must be hex")
    if not isinstance(snapshot.report_fields, dict):
        errors.append("snapshot.report_fields must be a dict")
    return errors


def _scan_text_file_secrets(snapshot: InventorySnapshot, repo_root: Pathish) -> List[str]:
    errors: List[str] = []
    root = Path(repo_root)
    for index, entry in enumerate(snapshot.files):
        if entry.kind != KIND_TEXT:
            continue
        path = root / entry.path
        if not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            errors.append(f"files[{index}]: cannot read text path {entry.path!r}: {exc}")
            continue
        errors.extend(find_secrets_in_text(text, location=f"files[{index}] ({entry.path})"))
    return errors


def validate_hash_stability(
    first: InventorySnapshot,
    second: InventorySnapshot,
) -> List[str]:
    """Two scans of the same tree must produce equal content hashes."""

    errors: List[str] = []
    by_path_a = {row.path: row for row in first.files}
    by_path_b = {row.path: row for row in second.files}
    if set(by_path_a) != set(by_path_b):
        errors.append("hash stability: file path sets differ between scans")
        return errors
    for path, row_a in sorted(by_path_a.items()):
        row_b = by_path_b[path]
        if row_a.content_hash != row_b.content_hash:
            errors.append(f"hash stability: content_hash changed for {path!r}")
        if row_a.hash_policy != row_b.hash_policy:
            errors.append(f"hash stability: hash_policy changed for {path!r}")
        if row_a.size != row_b.size:
            errors.append(f"hash stability: size changed for {path!r}")
    return errors


def validate_snapshot_to_dict_stability(
    first: InventorySnapshot,
    second: Optional[InventorySnapshot] = None,
) -> List[str]:
    """``to_dict`` dumps with ``sort_keys=True`` must be identical."""

    payload_a = json.dumps(first.to_dict(), sort_keys=True, ensure_ascii=True)
    other = second if second is not None else first
    payload_b = json.dumps(other.to_dict(), sort_keys=True, ensure_ascii=True)
    if payload_a != payload_b:
        return ["InventorySnapshot.to_dict() is not sort_keys-stable across builds"]
    return []


def validate_notebooklm_entry(entry: Mapping[str, Any]) -> List[str]:
    """Hard-fail unless notebooklm-mcp is experimental + experimental_only."""

    errors: List[str] = []
    tool_id = entry.get("id")
    if tool_id != NOTEBOOKLM_TOOL_ID:
        return [f"validate_notebooklm_entry expected id {NOTEBOOKLM_TOOL_ID!r}"]
    mode = entry.get("integration_mode")
    if mode != NOTEBOOKLM_INTEGRATION_MODE:
        errors.append(
            f"{NOTEBOOKLM_TOOL_ID} integration_mode must be "
            f"{NOTEBOOKLM_INTEGRATION_MODE!r}, got {mode!r}"
        )
    adoption = entry.get("adoption_recommendation")
    if adoption != NOTEBOOKLM_ADOPTION:
        errors.append(
            f"{NOTEBOOKLM_TOOL_ID} adoption_recommendation must be "
            f"{NOTEBOOKLM_ADOPTION!r}, got {adoption!r}"
        )
    return errors


def validate_tool_source_row(entry: Any) -> List[str]:
    """Deeper fail-closed checks on one registry row (errors, not warnings)."""

    if not isinstance(entry, Mapping):
        return ["tool source entry must be a mapping"]
    errors = list(validate_tool_source_entry(entry))
    mode = entry.get("integration_mode")
    if isinstance(mode, str) and mode:
        for message in validate_integration_mode(mode):
            if message not in errors:
                errors.append(message)
    adoption = entry.get("adoption_recommendation")
    if isinstance(adoption, str) and adoption and adoption not in ADOPTION_RECOMMENDATIONS:
        allowed = ", ".join(sorted(ADOPTION_RECOMMENDATIONS))
        errors.append(f"adoption_recommendation must be one of: {allowed}")
    errors.extend(find_secrets_in_value(entry, location=f"tool[{entry.get('id', '?')}]"))
    if entry.get("id") == NOTEBOOKLM_TOOL_ID:
        errors.extend(validate_notebooklm_entry(entry))
    return errors


def validate_tool_source_registry(
    entries: Sequence[Mapping[str, Any]],
    *,
    expect_count: Optional[int] = None,
    require_notebooklm: Optional[bool] = None,
) -> List[str]:
    errors: List[str] = []
    if require_notebooklm is None:
        require_notebooklm = expect_count == EXPECTED_REAL_TOOL_SOURCE_COUNT
    if expect_count is not None and len(entries) != expect_count:
        errors.append(
            f"tool registry length must be {expect_count}, got {len(entries)}"
        )
    seen_ids: Dict[str, int] = {}
    notebooklm: Optional[Mapping[str, Any]] = None
    for index, row in enumerate(entries):
        prefix = f"tools[{index}]"
        if not isinstance(row, Mapping):
            errors.append(f"{prefix}: entry must be a mapping")
            continue
        row_errors = validate_tool_source_row(row)
        errors.extend(f"{prefix}: {message}" for message in row_errors)
        tool_id = row.get("id")
        if isinstance(tool_id, str):
            if tool_id in seen_ids:
                errors.append(
                    f"{prefix}: duplicate tool id {tool_id!r} "
                    f"(first at tools[{seen_ids[tool_id]}])"
                )
            else:
                seen_ids[tool_id] = index
            if tool_id == NOTEBOOKLM_TOOL_ID:
                notebooklm = row
    if require_notebooklm:
        if notebooklm is None:
            errors.append(f"tool registry missing required id {NOTEBOOKLM_TOOL_ID!r}")
        else:
            errors.extend(validate_notebooklm_entry(notebooklm))
    return errors


def validate_real_tool_sources(repo_root: Optional[Pathish] = None) -> List[str]:
    """Load the real YAML and fail closed on count / NotebookLM / rows."""

    entries = load_tool_sources(repo_root)
    return validate_tool_source_registry(
        entries,
        expect_count=EXPECTED_REAL_TOOL_SOURCE_COUNT,
        require_notebooklm=True,
    )


def _iter_imported_modules(tree: ast.AST) -> Iterable[str]:
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom) and node.module:
            yield node.module


def _root_module(name: str) -> str:
    return name.split(".", 1)[0]


def collect_forbidden_import_violations(source_path: Pathish) -> List[str]:
    """AST denylist: network clients and MarketOS must not be imported."""

    path = Path(source_path)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return [f"{path.as_posix()}: cannot read source: {exc}"]
    try:
        tree = ast.parse(text, filename=str(path))
    except SyntaxError as exc:
        return [f"{path.as_posix()}: cannot parse source: {exc}"]
    errors: List[str] = []
    for module in _iter_imported_modules(tree):
        root = _root_module(module)
        if module in NETWORK_IMPORT_DENYLIST or root in NETWORK_IMPORT_DENYLIST:
            errors.append(f"{path.as_posix()}: forbidden network import {module!r}")
        if module in MARKETOS_IMPORT_DENYLIST or root in MARKETOS_IMPORT_DENYLIST:
            errors.append(f"{path.as_posix()}: forbidden MarketOS import {module!r}")
    return errors


def validate_no_network_imports(
    extra_paths: Optional[Sequence[Pathish]] = None,
) -> List[str]:
    """Scanner/validators (and sibling package modules) must stay offline."""

    paths: List[Path] = [
        _PACKAGE_DIR / "validators.py",
        _PACKAGE_DIR / "scanner.py",
        _PACKAGE_DIR / "tool_sources.py",
        _PACKAGE_DIR / "models.py",
    ]
    if extra_paths:
        paths.extend(Path(item) for item in extra_paths)
    errors: List[str] = []
    seen: set[str] = set()
    for path in paths:
        key = path.resolve().as_posix()
        if key in seen:
            continue
        seen.add(key)
        errors.extend(collect_forbidden_import_violations(path))
    return errors


def validate_inventory_snapshot(
    snapshot: InventorySnapshot,
    *,
    repo_root: Optional[Pathish] = None,
    scan_text_contents: bool = True,
    tool_sources: Optional[Sequence[Mapping[str, Any]]] = None,
) -> List[str]:
    """Validate one snapshot. Returns all errors (never warnings)."""

    errors: List[str] = []
    errors.extend(validate_snapshot_required_fields(snapshot))
    for index, entry in enumerate(snapshot.files):
        errors.extend(validate_file_entry(entry, index=index))
        errors.extend(
            find_secrets_in_value(
                {"path": entry.path, "content_hash": entry.content_hash},
                location=f"files[{index}]",
            )
        )
    for index, entry in enumerate(snapshot.worktrees_and_branches):
        errors.extend(validate_worktree_entry(entry, index=index))
    for index, entry in enumerate(snapshot.artifacts):
        errors.extend(validate_artifact_entry(entry, index=index))
    for index, entry in enumerate(snapshot.governance_files):
        errors.extend(validate_governance_entry(entry, index=index))
    for index, entry in enumerate(snapshot.dependencies):
        errors.extend(validate_dependency_entry(entry, index=index))
    for index, entry in enumerate(snapshot.overlaps):
        errors.extend(validate_overlap_finding(entry, index=index))
    errors.extend(validate_duplicate_ownership(snapshot, tool_sources))
    errors.extend(validate_no_scientific_pass(snapshot))
    errors.extend(find_secrets_in_value(snapshot.report_fields, location="report_fields"))
    errors.extend(validate_snapshot_to_dict_stability(snapshot))
    if scan_text_contents:
        root = repo_root if repo_root is not None else snapshot.repo_root
        if root:
            errors.extend(_scan_text_file_secrets(snapshot, root))
    if tool_sources is not None:
        errors.extend(validate_tool_source_registry(tool_sources))
    return errors


def validate_inventory_snapshot_or_raise(
    snapshot: InventorySnapshot,
    **kwargs: Any,
) -> None:
    errors = validate_inventory_snapshot(snapshot, **kwargs)
    if errors:
        raise ValueError(
            "inventory snapshot failed validation:\n" + "\n".join(errors)
        )


def validate_tool_source_registry_or_raise(
    entries: Sequence[Mapping[str, Any]],
    **kwargs: Any,
) -> None:
    errors = validate_tool_source_registry(entries, **kwargs)
    if errors:
        raise ValueError(
            "tool source registry failed validation:\n" + "\n".join(errors)
        )


# Re-export consumed contracts so tests can import from one QA module if needed.
__all__ = [
    "ADOPTION_RECOMMENDATIONS",
    "ARTIFACT_LABEL_EMPIRICAL",
    "EXPECTED_REAL_TOOL_SOURCE_COUNT",
    "FORBIDDEN_SCIENTIFIC_CLAIM_STATUSES",
    "HASH_POLICIES",
    "INTEGRATION_MODES",
    "INVENTORY_CLAIM_STATUS_NOT_EVIDENCE",
    "MARKETOS_IMPORT_DENYLIST",
    "NETWORK_IMPORT_DENYLIST",
    "NOTEBOOKLM_ADOPTION",
    "NOTEBOOKLM_INTEGRATION_MODE",
    "NOTEBOOKLM_TOOL_ID",
    "REQUIRED_KEYS",
    "collect_forbidden_import_violations",
    "empirical_label_is_scientific_pass",
    "find_secret_pattern_hits",
    "find_secrets_in_text",
    "inventory_claim_record",
    "inventory_is_scientific_evidence",
    "inventory_scientific_claim_status",
    "validate_artifact_entry",
    "validate_duplicate_ownership",
    "validate_file_entry",
    "validate_finite_numeric_fields",
    "validate_hash_fields",
    "validate_hash_stability",
    "validate_integration_mode",
    "validate_inventory_snapshot",
    "validate_inventory_snapshot_or_raise",
    "validate_no_network_imports",
    "validate_no_scientific_pass",
    "validate_notebooklm_entry",
    "validate_path_safety",
    "validate_real_tool_sources",
    "validate_snapshot_to_dict_stability",
    "validate_tool_source_registry",
    "validate_tool_source_registry_or_raise",
    "validate_tool_source_row",
]
