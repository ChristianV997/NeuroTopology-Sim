"""Typed inventory models for the Phase 1 retrofit scanner.

These dataclasses are JSON-serializable via ``to_dict``. List ordering is
normalized in ``InventorySnapshot.to_dict`` so later reporting can dump
``json.dumps(..., sort_keys=True)`` deterministically.

Labels on artifacts are inventory heuristics only (synthetic / empirical /
unknown). They are not scientific claims, evidence, or ontology promotions.

Reporting fields on ``InventorySnapshot`` are placeholders for a later phase
and stay empty unless a caller fills them in.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


INVENTORY_SCHEMA_VERSION = "0.1"

KIND_TEXT = "text"
KIND_BINARY = "binary"

HASH_POLICY_CONTENT_SHA256 = "content_sha256"
HASH_POLICY_SIZE_PATH_V1 = "size_path_v1"

ARTIFACT_LABEL_SYNTHETIC = "synthetic"
ARTIFACT_LABEL_EMPIRICAL = "empirical"
ARTIFACT_LABEL_UNKNOWN = "unknown"

WORKTREE_KIND_BRANCH = "branch"
WORKTREE_KIND_WORKTREE = "worktree"

ENTRY_KIND_VALUES = (KIND_TEXT, KIND_BINARY)
ARTIFACT_LABEL_VALUES = (
    ARTIFACT_LABEL_SYNTHETIC,
    ARTIFACT_LABEL_EMPIRICAL,
    ARTIFACT_LABEL_UNKNOWN,
)


def _as_plain(value: Any) -> Any:
    if isinstance(value, list):
        return [_as_plain(item) for item in value]
    if isinstance(value, dict):
        return {key: _as_plain(item) for key, item in value.items()}
    return value


@dataclass
class FileInventoryEntry:
    """One repository file (metadata only; contents are never stored).

    ``content_hash`` is content-stable: it does not incorporate mtime, inode,
    or other filesystem metadata. See ``tools.retrofit_inventory.scanner``
    for the size+path digest policy used on large or binary files.
    """

    path: str
    kind: str
    size: int
    content_hash: str
    mtime: Optional[float] = None
    hash_policy: str = HASH_POLICY_CONTENT_SHA256

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class WorktreeOrBranchEntry:
    """A local/remote git branch or a linked worktree (read-only git data)."""

    kind: str
    name: str
    path: Optional[str] = None
    commit_sha: Optional[str] = None
    is_current: bool = False
    is_remote: bool = False
    is_detached: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class ArtifactInventoryEntry:
    """File under a known artifact directory, with a heuristic provenance label.

    ``label`` is one of synthetic | empirical | unknown. It is derived from
    explicit markers or path/name tokens and must not be treated as evidence.
    """

    path: str
    label: str
    schema_id: Optional[str] = None
    size: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class GovernanceFileEntry:
    """Governance / contract / agent-rule file located by path convention."""

    path: str
    category: str
    size: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class DependencyReferenceEntry:
    """Declared dependency name mined from a lock-less manifest (no resolve)."""

    name: str
    source_path: str
    ecosystem: str
    extra: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class OverlapOrDuplicateFinding:
    """Same basename across top-level trees, or a known dual-root overlap."""

    paths: List[str]
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        payload = asdict(self)
        payload["paths"] = sorted(payload["paths"])
        return payload


@dataclass
class InventorySnapshot:
    """Deterministic, JSON-ready inventory of one local checkout.

    ``generated_at``, ``generated_by``, and ``report_fields`` are placeholders
    for later reporting. The scanner leaves them empty so default dumps stay
    clock-independent.
    """

    repo_root: str
    commit_sha: str
    files: List[FileInventoryEntry] = field(default_factory=list)
    worktrees_and_branches: List[WorktreeOrBranchEntry] = field(default_factory=list)
    artifacts: List[ArtifactInventoryEntry] = field(default_factory=list)
    governance_files: List[GovernanceFileEntry] = field(default_factory=list)
    dependencies: List[DependencyReferenceEntry] = field(default_factory=list)
    overlaps: List[OverlapOrDuplicateFinding] = field(default_factory=list)
    schema_version: str = INVENTORY_SCHEMA_VERSION
    generated_at: Optional[str] = None
    generated_by: Optional[str] = None
    report_fields: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        payload = _as_plain(asdict(self))
        payload["files"] = sorted(payload["files"], key=lambda row: row["path"])
        payload["worktrees_and_branches"] = sorted(
            payload["worktrees_and_branches"],
            key=lambda row: (row["kind"], row["name"], row.get("path") or ""),
        )
        payload["artifacts"] = sorted(payload["artifacts"], key=lambda row: row["path"])
        payload["governance_files"] = sorted(
            payload["governance_files"],
            key=lambda row: (row["category"], row["path"]),
        )
        payload["dependencies"] = sorted(
            payload["dependencies"],
            key=lambda row: (row["name"], row["source_path"], row.get("extra") or ""),
        )
        payload["overlaps"] = sorted(
            payload["overlaps"],
            key=lambda row: (row["reason"], tuple(sorted(row.get("paths") or []))),
        )
        for row in payload["overlaps"]:
            row["paths"] = sorted(row.get("paths") or [])
        payload["report_fields"] = dict(sorted((payload.get("report_fields") or {}).items()))
        return payload
