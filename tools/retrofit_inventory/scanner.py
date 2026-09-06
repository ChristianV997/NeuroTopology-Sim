"""Offline retrofit inventory scanner (Phase 1).

Walk a local repository root and emit deterministic, JSON-serializable
dataclasses from ``tools.retrofit_inventory.models``. No network, no
credential reads, no dataset downloads, and no live API calls.

Hash policy
-----------
* **content_sha256** — SHA-256 of file bytes. Used for small text files
  that are not treated as secrets. The digest is content-stable: mtime,
  inode, and path are not mixed in.
* **size_path_v1** — SHA-256 of the UTF-8 payload
  ``size_path_v1\\0{size}\\0{posix_rel_path}``. Used for binary files,
  files larger than ``LARGE_FILE_BYTES``, and likely-secret filenames
  (``.env``, keys, credential basenames). Binary / large contents are
  never copied into the JSON snapshot.

Ignore policy
-------------
Directory names ``.git``, ``__pycache__``, ``.venv``, ``venv``,
``node_modules`` (and a small additional set of common cache/VCS dirs)
are not descended into. Files under ``data/``, ``outputs/``,
``artifacts/``, and ``runs/`` are inventoried as metadata only; their
binary bytes are not ingested.

Git
---
Worktree / branch inventory uses read-only ``git`` (``branch -a``,
``worktree list``, ``rev-parse``). If ``git`` is missing or the root is
not a work tree, those calls fail closed with ``GitUnavailableError``.

Artifact labels are path/marker heuristics (synthetic | empirical |
unknown) and are not scientific evidence.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple, Union

from .models import (
    ARTIFACT_LABEL_EMPIRICAL,
    ARTIFACT_LABEL_SYNTHETIC,
    ARTIFACT_LABEL_UNKNOWN,
    HASH_POLICY_CONTENT_SHA256,
    HASH_POLICY_SIZE_PATH_V1,
    KIND_BINARY,
    KIND_TEXT,
    WORKTREE_KIND_BRANCH,
    WORKTREE_KIND_WORKTREE,
    ArtifactInventoryEntry,
    DependencyReferenceEntry,
    FileInventoryEntry,
    GovernanceFileEntry,
    InventorySnapshot,
    OverlapOrDuplicateFinding,
    WorktreeOrBranchEntry,
)

Pathish = Union[str, Path]

LARGE_FILE_BYTES = 1_048_576
MARKER_PEEK_BYTES = 262_144
NUL_PEEK_BYTES = 8192
GIT_TIMEOUT_S = 45
SIZE_PATH_DIGEST_VERSION = "size_path_v1"

IGNORE_DIR_NAMES = frozenset(
    {
        ".git",
        "__pycache__",
        ".venv",
        "venv",
        "node_modules",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
        ".ruff_cache",
        ".eggs",
        ".nox",
        ".hypothesis",
        "htmlcov",
        ".cursor",
        ".idea",
        ".openclaw",
    }
)
IGNORE_DIR_SUFFIXES = (".egg-info",)
IGNORE_FILE_SUFFIXES = (".pyc", ".pyo")

ARTIFACT_ROOTS = ("artifacts", "outputs", "runs")

KNOWN_DUAL_ROOTS: Tuple[Tuple[str, str], ...] = (("", "apps/awareness_studio"),)

UBIQUITOUS_BASENAMES = frozenset(
    {
        "__init__.py",
        "__main__.py",
        ".gitkeep",
        ".ds_store",
        ".gitattributes",
    }
)

SECRET_BASENAMES = frozenset(
    {
        ".env",
        ".env.local",
        ".env.production",
        ".env.development",
        "credentials",
        "credentials.json",
        "secrets.json",
        "id_rsa",
        "id_dsa",
        "id_ecdsa",
        "id_ed25519",
    }
)
SECRET_SUFFIXES = (".pem", ".key", ".p12", ".pfx")
ENV_EXAMPLE_BASENAMES = frozenset({".env.example", ".env.sample", ".env.template"})

TEXT_EXTENSIONS = frozenset(
    {
        ".py",
        ".pyi",
        ".md",
        ".rst",
        ".txt",
        ".yml",
        ".yaml",
        ".json",
        ".toml",
        ".ini",
        ".cfg",
        ".in",
        ".csv",
        ".tsv",
        ".html",
        ".htm",
        ".css",
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".sh",
        ".bash",
        ".zsh",
        ".xml",
        ".svg",
        ".sql",
        ".r",
        ".ipynb",
        ".tex",
        ".bib",
        ".c",
        ".h",
        ".cpp",
        ".hpp",
        ".rs",
        ".go",
        ".java",
        ".kt",
        ".swift",
        ".rb",
        ".php",
        ".lua",
        ".pl",
        ".ps1",
        ".bat",
        ".cmd",
        ".cmake",
        ".mk",
        ".gitignore",
        ".dockerignore",
        ".editorconfig",
        ".flake8",
        ".coveragerc",
    }
)
BINARY_EXTENSIONS = frozenset(
    {
        ".npy",
        ".npz",
        ".pkl",
        ".pickle",
        ".h5",
        ".hdf5",
        ".sqlite",
        ".db",
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".ico",
        ".bmp",
        ".tif",
        ".tiff",
        ".pdf",
        ".zip",
        ".gz",
        ".bz2",
        ".xz",
        ".7z",
        ".tar",
        ".whl",
        ".egg",
        ".so",
        ".dylib",
        ".dll",
        ".exe",
        ".bin",
        ".pt",
        ".pth",
        ".onnx",
        ".parquet",
        ".feather",
        ".arrow",
        ".fif",
        ".edf",
        ".bdf",
        ".set",
        ".fdt",
        ".nii",
        ".mat",
        ".pyd",
        ".o",
        ".a",
        ".woff",
        ".woff2",
        ".ttf",
        ".eot",
        ".mp4",
        ".mp3",
        ".wav",
        ".ogg",
        ".webm",
        ".avi",
        ".mov",
    }
)

_REQ_NAME_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)")
_SIMPLE_YAML_KV_RE = re.compile(
    r"^(schema_id|schemaId|schema|schema_version|inventory_label|"
    r"artifact_label|label|data_mode)\s*:\s*(.+?)\s*$"
)


class GitUnavailableError(RuntimeError):
    """Raised when git is missing or the root is not a usable work tree."""


def _as_root(repo_root: Pathish) -> Path:
    root = Path(repo_root)
    if not root.exists():
        raise FileNotFoundError(f"repo_root does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"repo_root is not a directory: {root}")
    return root


def _posix_rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _is_secret_path(rel_posix: str) -> bool:
    base = Path(rel_posix).name
    if base in SECRET_BASENAMES:
        return True
    if base.startswith(".env") and base not in ENV_EXAMPLE_BASENAMES:
        return True
    return base.endswith(SECRET_SUFFIXES)


def _iter_repo_files(root: Path) -> Iterator[Path]:
    """Yield regular files under ``root`` in sorted path order (no symlinks)."""

    def walk(current: Path) -> Iterator[Path]:
        try:
            entries = list(os.scandir(current))
        except OSError:
            return
        entries.sort(key=lambda entry: entry.name)
        for entry in entries:
            name = entry.name
            if name in IGNORE_DIR_NAMES:
                continue
            if any(name.endswith(suffix) for suffix in IGNORE_DIR_SUFFIXES):
                continue
            try:
                is_symlink = entry.is_symlink()
                is_dir = entry.is_dir(follow_symlinks=False)
                is_file = entry.is_file(follow_symlinks=False)
            except OSError:
                continue
            if is_symlink:
                continue
            child = Path(entry.path)
            if is_dir:
                yield from walk(child)
            elif is_file:
                if name.endswith(IGNORE_FILE_SUFFIXES):
                    continue
                yield child

    yield from walk(root)


def _looks_binary(path: Path, size: int, rel_posix: str) -> bool:
    suffix = Path(rel_posix).suffix.lower()
    if suffix in BINARY_EXTENSIONS:
        return True
    if suffix in TEXT_EXTENSIONS:
        return False
    if _is_secret_path(rel_posix):
        return True
    if size == 0:
        return False
    if size > LARGE_FILE_BYTES:
        return True
    try:
        with path.open("rb") as handle:
            sample = handle.read(NUL_PEEK_BYTES)
        return b"\x00" in sample
    except OSError:
        return True


def size_path_digest(size: int, rel_posix: str) -> str:
    """Deterministic size+path digest (``size_path_v1``).

    Payload is ``size_path_v1\\0{size}\\0{posix_rel_path}`` encoded as UTF-8
    and hashed with SHA-256. Path separators are POSIX. This is used when
    file bytes must not be ingested (binary, large, or likely-secret).
    """

    payload = f"{SIZE_PATH_DIGEST_VERSION}\0{size}\0{rel_posix}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _sha256_file_bytes(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hash_file(
    path: Path,
    *,
    rel_path: str,
    size: int,
    kind: str,
) -> Tuple[str, str]:
    """Return ``(content_hash, hash_policy)`` for one file.

    Small text files use SHA-256 of bytes. Large files, binary files, and
    likely-secret names use ``size_path_v1``. mtime is never hashed.
    """

    if (
        kind == KIND_BINARY
        or size > LARGE_FILE_BYTES
        or _is_secret_path(rel_path)
    ):
        return size_path_digest(size, rel_path), HASH_POLICY_SIZE_PATH_V1
    try:
        return _sha256_file_bytes(path), HASH_POLICY_CONTENT_SHA256
    except OSError:
        return size_path_digest(size, rel_path), HASH_POLICY_SIZE_PATH_V1


def scan_repository_files(
    repo_root: Pathish,
    *,
    include_mtime: bool = False,
) -> List[FileInventoryEntry]:
    """Inventory regular files under ``repo_root`` (metadata + stable hash)."""

    root = _as_root(repo_root)
    entries: List[FileInventoryEntry] = []
    for path in _iter_repo_files(root):
        rel = _posix_rel(root, path)
        try:
            stat = path.stat()
        except OSError:
            continue
        size = int(stat.st_size)
        kind = KIND_BINARY if _looks_binary(path, size, rel) else KIND_TEXT
        content_hash, policy = hash_file(path, rel_path=rel, size=size, kind=kind)
        mtime = float(stat.st_mtime) if include_mtime else None
        entries.append(
            FileInventoryEntry(
                path=rel,
                kind=kind,
                size=size,
                content_hash=content_hash,
                mtime=mtime,
                hash_policy=policy,
            )
        )
    entries.sort(key=lambda row: row.path)
    return entries


def _which_git() -> str:
    git = shutil.which("git")
    if git is None:
        raise GitUnavailableError("git executable not found; fail closed")
    return git


def _run_git(root: Path, args: Sequence[str]) -> str:
    git = _which_git()
    try:
        proc = subprocess.run(
            [git, "-C", str(root), *args],
            check=False,
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_S,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GitUnavailableError(f"git invocation failed: {exc}") from exc
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "git command failed").strip()
        raise GitUnavailableError(detail)
    return proc.stdout


def resolve_commit_sha(repo_root: Pathish) -> str:
    """Return ``HEAD`` SHA. Fail closed if git is missing or not a work tree."""

    root = _as_root(repo_root)
    inside = _run_git(root, ["rev-parse", "--is-inside-work-tree"]).strip()
    if inside != "true":
        raise GitUnavailableError("repo_root is not inside a git work tree; fail closed")
    sha = _run_git(root, ["rev-parse", "HEAD"]).strip()
    if not sha:
        raise GitUnavailableError("git rev-parse HEAD returned empty; fail closed")
    return sha


def scan_worktrees_and_branches(repo_root: Pathish) -> List[WorktreeOrBranchEntry]:
    """Read-only ``git branch -a`` + ``git worktree list`` inventory.

    Raises ``GitUnavailableError`` if git is missing or the root is not a
    git work tree (fail closed).
    """

    root = _as_root(repo_root)
    resolve_commit_sha(root)
    entries: List[WorktreeOrBranchEntry] = []
    entries.extend(_scan_branches(root))
    entries.extend(_scan_worktrees(root))
    entries.sort(key=lambda row: (row.kind, row.name, row.path or ""))
    return entries


def _scan_branches(root: Path) -> List[WorktreeOrBranchEntry]:
    fmt = "%(HEAD)%00%(objectname)%00%(refname)%00%(refname:short)"
    raw = _run_git(root, ["branch", "-a", f"--format={fmt}"])
    rows: List[WorktreeOrBranchEntry] = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        parts = line.split("\0")
        if len(parts) < 4:
            continue
        head_mark, sha, refname, short = parts[0], parts[1], parts[2], parts[3]
        is_remote = refname.startswith("refs/remotes/") or short.startswith("remotes/")
        rows.append(
            WorktreeOrBranchEntry(
                kind=WORKTREE_KIND_BRANCH,
                name=short,
                path=None,
                commit_sha=sha or None,
                is_current=head_mark.strip() == "*",
                is_remote=is_remote,
                is_detached=False,
            )
        )
    return rows


def _scan_worktrees(root: Path) -> List[WorktreeOrBranchEntry]:
    raw = _run_git(root, ["worktree", "list", "--porcelain"])
    rows: List[WorktreeOrBranchEntry] = []
    current: Dict[str, str] = {}

    def flush() -> None:
        if not current.get("worktree"):
            current.clear()
            return
        wt_path = current["worktree"]
        branch = current.get("branch", "")
        if branch.startswith("refs/heads/"):
            name = branch[len("refs/heads/") :]
            detached = False
        elif current.get("detached") == "1":
            name = current.get("HEAD") or Path(wt_path).name
            detached = True
        else:
            name = branch or Path(wt_path).name
            detached = False
        rows.append(
            WorktreeOrBranchEntry(
                kind=WORKTREE_KIND_WORKTREE,
                name=name,
                path=wt_path,
                commit_sha=current.get("HEAD"),
                is_current=os.path.normpath(wt_path) == os.path.normpath(str(root.resolve())),
                is_remote=False,
                is_detached=detached,
            )
        )
        current.clear()

    for line in raw.splitlines():
        if not line.strip():
            flush()
            continue
        if line.startswith("worktree "):
            flush()
            current["worktree"] = line[len("worktree ") :]
        elif line.startswith("HEAD "):
            current["HEAD"] = line[len("HEAD ") :]
        elif line.startswith("branch "):
            current["branch"] = line[len("branch ") :]
        elif line.strip() == "detached":
            current["detached"] = "1"
    flush()
    return rows


def _map_label_token(raw: str) -> str:
    token = raw.strip().strip("\"'").lower().replace("-", "_")
    if token in {"synthetic", "mock", "fixture", "generated", "dry_run", "dryrun"}:
        return ARTIFACT_LABEL_SYNTHETIC
    if token in {"empirical", "empirical_local", "recorded"}:
        return ARTIFACT_LABEL_EMPIRICAL
    return ARTIFACT_LABEL_UNKNOWN


def _label_from_path(rel: str) -> str:
    lowered = rel.replace("\\", "/").lower()
    tokens = set(re.split(r"[\\/._-]+", lowered))
    tokens.update(lowered.split("/"))
    if tokens & {"synthetic", "mock", "fixture", "dry_run", "dryrun"}:
        return ARTIFACT_LABEL_SYNTHETIC
    if tokens & {"empirical", "empirical_local"}:
        return ARTIFACT_LABEL_EMPIRICAL
    padded = f"/{lowered}/"
    if "/synthetic/" in padded or "_synthetic_" in lowered:
        return ARTIFACT_LABEL_SYNTHETIC
    if "/empirical/" in padded or "_empirical_" in lowered:
        return ARTIFACT_LABEL_EMPIRICAL
    return ARTIFACT_LABEL_UNKNOWN


def _dir_marker_label(directory: Path, cache: Dict[str, Optional[str]]) -> Optional[str]:
    key = str(directory)
    if key in cache:
        return cache[key]
    label: Optional[str] = None
    markers = (
        ("SYNTHETIC", ARTIFACT_LABEL_SYNTHETIC),
        ("EMPIRICAL", ARTIFACT_LABEL_EMPIRICAL),
        (".synthetic", ARTIFACT_LABEL_SYNTHETIC),
        (".empirical", ARTIFACT_LABEL_EMPIRICAL),
        (".inventory_label", None),
        ("inventory_label", None),
    )
    for name, preset in markers:
        marker = directory / name
        if not marker.is_file() or marker.is_symlink():
            continue
        if preset is not None:
            label = preset
            break
        try:
            text = marker.read_text(encoding="utf-8")[:64]
        except (OSError, UnicodeDecodeError):
            continue
        mapped = _map_label_token(text)
        if mapped != ARTIFACT_LABEL_UNKNOWN:
            label = mapped
            break
    cache[key] = label
    return label


def _extract_markers_from_mapping(obj: Any) -> Tuple[Optional[str], Optional[str]]:
    if not isinstance(obj, dict):
        return None, None
    label: Optional[str] = None
    for key in ("inventory_label", "artifact_label", "label", "data_mode"):
        value = obj.get(key)
        if isinstance(value, str):
            mapped = _map_label_token(value)
            if mapped != ARTIFACT_LABEL_UNKNOWN:
                label = mapped
                break
    schema_id: Optional[str] = None
    for key in ("schema_id", "schemaId", "$id"):
        value = obj.get(key)
        if isinstance(value, str) and value.strip():
            schema_id = value.strip()
            break
    if schema_id is None:
        value = obj.get("schema")
        if isinstance(value, str):
            stripped = value.strip()
            if stripped and ("." in stripped or "/" in stripped or stripped.endswith(".json")):
                schema_id = stripped
    return label, schema_id


def _extract_markers_from_yaml_text(text: str) -> Tuple[Optional[str], Optional[str]]:
    label: Optional[str] = None
    schema_id: Optional[str] = None
    for raw_line in text.splitlines():
        line = raw_line.split("#", 1)[0].strip()
        match = _SIMPLE_YAML_KV_RE.match(line)
        if match is None:
            continue
        key, value = match.group(1), match.group(2).strip().strip("\"'")
        if key in {"inventory_label", "artifact_label", "label", "data_mode"} and label is None:
            mapped = _map_label_token(value)
            if mapped != ARTIFACT_LABEL_UNKNOWN:
                label = mapped
        elif key in {"schema_id", "schemaId"} and schema_id is None:
            schema_id = value or None
        elif key == "schema" and schema_id is None:
            if value and ("." in value or "/" in value or value.endswith(".json")):
                schema_id = value
    return label, schema_id


def _peek_artifact_markers(path: Path, size: int, kind: str) -> Tuple[Optional[str], Optional[str]]:
    if kind != KIND_TEXT or size == 0 or size > MARKER_PEEK_BYTES:
        return None, None
    if _is_secret_path(path.name):
        return None, None
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None, None
    suffix = path.suffix.lower()
    if suffix == ".json":
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return None, None
        return _extract_markers_from_mapping(parsed)
    if suffix in {".yml", ".yaml"}:
        return _extract_markers_from_yaml_text(text)
    return None, None


def scan_artifacts(repo_root: Pathish) -> List[ArtifactInventoryEntry]:
    """Inventory files under ``artifacts/``, ``outputs/``, and ``runs/``.

    Classification is heuristic (path tokens + explicit markers). Labels
    never assert scientific evidence.
    """

    root = _as_root(repo_root)
    entries: List[ArtifactInventoryEntry] = []
    marker_cache: Dict[str, Optional[str]] = {}
    seen: set[str] = set()
    for artifact_root in ARTIFACT_ROOTS:
        base = root / artifact_root
        if not base.is_dir() or base.is_symlink():
            continue
        for path in _iter_repo_files(base):
            rel = _posix_rel(root, path)
            if rel in seen:
                continue
            seen.add(rel)
            try:
                size = int(path.stat().st_size)
            except OSError:
                continue
            kind = KIND_BINARY if _looks_binary(path, size, rel) else KIND_TEXT
            dir_label = _dir_marker_label(path.parent, marker_cache)
            peek_label, schema_id = _peek_artifact_markers(path, size, kind)
            path_label = _label_from_path(rel)
            label = dir_label or peek_label or path_label or ARTIFACT_LABEL_UNKNOWN
            if label not in {
                ARTIFACT_LABEL_SYNTHETIC,
                ARTIFACT_LABEL_EMPIRICAL,
                ARTIFACT_LABEL_UNKNOWN,
            }:
                label = ARTIFACT_LABEL_UNKNOWN
            entries.append(
                ArtifactInventoryEntry(
                    path=rel,
                    label=label,
                    schema_id=schema_id,
                    size=size,
                )
            )
    entries.sort(key=lambda row: row.path)
    return entries


def _governance_category(rel: str) -> Optional[str]:
    base = Path(rel).name
    if base == "AGENTS.md":
        return "agents"
    if base == "CLAUDE.md":
        return "claude"
    parts = rel.split("/")
    if parts and parts[0] == ".dev-runtime":
        return "dev_runtime"
    if parts and parts[0] == "governance":
        return "governance"
    if parts and parts[0] == "contracts":
        return "contracts"
    if parts and parts[0] == "docs" and "contract" in base.lower():
        return "docs_contract"
    return None


def scan_governance_files(repo_root: Pathish) -> List[GovernanceFileEntry]:
    """Inventory AGENTS.md, CLAUDE.md, ``.dev-runtime/``, ``governance/``,
    ``contracts/``, and ``docs/*contract*`` files.
    """

    root = _as_root(repo_root)
    entries: List[GovernanceFileEntry] = []
    for path in _iter_repo_files(root):
        rel = _posix_rel(root, path)
        category = _governance_category(rel)
        if category is None:
            continue
        try:
            size = int(path.stat().st_size)
        except OSError:
            size = 0
        entries.append(GovernanceFileEntry(path=rel, category=category, size=size))
    entries.sort(key=lambda row: (row.category, row.path))
    return entries


def _parse_requirement_name(line: str) -> Optional[str]:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    if stripped.startswith("--"):
        return None
    if stripped.startswith(("-r ", "-c ", "--requirement", "--constraint")):
        return None
    if stripped.startswith("-e ") or stripped.startswith("--editable"):
        rest = stripped.split(None, 1)[1] if " " in stripped else ""
        if "#egg=" in rest:
            return rest.split("#egg=", 1)[1].split("&")[0].strip() or None
        return None
    if ";" in stripped:
        stripped = stripped.split(";", 1)[0].strip()
    match = _REQ_NAME_RE.match(stripped)
    if match is None:
        return None
    name = match.group(1)
    if name.lower() in {"python"}:
        return None
    return name


def _iter_requirement_names(text: str) -> Iterator[str]:
    for line in text.splitlines():
        name = _parse_requirement_name(line)
        if name:
            yield name


def _load_toml(path: Path) -> Optional[Dict[str, Any]]:
    try:
        import tomllib
    except ImportError:
        return None
    try:
        return tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, tomllib.TOMLDecodeError):
        return None


def _names_from_dep_item(item: Any) -> Optional[str]:
    if isinstance(item, str):
        return _parse_requirement_name(item)
    if isinstance(item, dict):
        name = item.get("name")
        if isinstance(name, str):
            return name.strip() or None
    return None


def _dependencies_from_pyproject(path: Path, rel: str) -> List[DependencyReferenceEntry]:
    data = _load_toml(path)
    if not data:
        return []
    rows: List[DependencyReferenceEntry] = []
    project = data.get("project") or {}
    for item in project.get("dependencies") or []:
        name = _names_from_dep_item(item)
        if name:
            rows.append(
                DependencyReferenceEntry(
                    name=name, source_path=rel, ecosystem="pypi", extra=None
                )
            )
    optional = project.get("optional-dependencies") or {}
    if isinstance(optional, dict):
        for extra, items in optional.items():
            if not isinstance(items, (list, tuple)):
                continue
            extra_name = str(extra)
            for item in items:
                name = _names_from_dep_item(item)
                if name:
                    rows.append(
                        DependencyReferenceEntry(
                            name=name,
                            source_path=rel,
                            ecosystem="pypi",
                            extra=extra_name,
                        )
                    )
    poetry = (data.get("tool") or {}).get("poetry") or {}
    poetry_deps = poetry.get("dependencies") or {}
    if isinstance(poetry_deps, dict):
        for name in poetry_deps:
            if str(name).lower() == "python":
                continue
            rows.append(
                DependencyReferenceEntry(
                    name=str(name), source_path=rel, ecosystem="pypi", extra=None
                )
            )
    poetry_dev = poetry.get("dev-dependencies") or {}
    if isinstance(poetry_dev, dict):
        for name in poetry_dev:
            if str(name).lower() == "python":
                continue
            rows.append(
                DependencyReferenceEntry(
                    name=str(name), source_path=rel, ecosystem="pypi", extra="dev"
                )
            )
    groups = poetry.get("group") or {}
    if isinstance(groups, dict):
        for group_name, group in groups.items():
            if not isinstance(group, dict):
                continue
            grouped = group.get("dependencies") or {}
            if not isinstance(grouped, dict):
                continue
            for name in grouped:
                if str(name).lower() == "python":
                    continue
                rows.append(
                    DependencyReferenceEntry(
                        name=str(name),
                        source_path=rel,
                        ecosystem="pypi",
                        extra=str(group_name),
                    )
                )
    return rows


def _dependencies_from_package_json(path: Path, rel: str) -> List[DependencyReferenceEntry]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return []
    if not isinstance(data, dict):
        return []
    rows: List[DependencyReferenceEntry] = []
    sections = (
        ("dependencies", None),
        ("devDependencies", "dev"),
        ("optionalDependencies", "optional"),
        ("peerDependencies", "peer"),
    )
    for section, extra in sections:
        block = data.get(section) or {}
        if not isinstance(block, dict):
            continue
        for name in block:
            if not isinstance(name, str) or not name.strip():
                continue
            rows.append(
                DependencyReferenceEntry(
                    name=name.strip(),
                    source_path=rel,
                    ecosystem="npm",
                    extra=extra,
                )
            )
    return rows


def scan_dependency_references(repo_root: Pathish) -> List[DependencyReferenceEntry]:
    """Collect declared package names from manifests. No network resolve."""

    root = _as_root(repo_root)
    entries: List[DependencyReferenceEntry] = []
    for path in _iter_repo_files(root):
        rel = _posix_rel(root, path)
        name = path.name
        if name.startswith("requirements") and name.endswith(".txt"):
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for dep_name in _iter_requirement_names(text):
                entries.append(
                    DependencyReferenceEntry(
                        name=dep_name,
                        source_path=rel,
                        ecosystem="pypi",
                        extra=None,
                    )
                )
        elif name == "pyproject.toml":
            entries.extend(_dependencies_from_pyproject(path, rel))
        elif name == "package.json":
            entries.extend(_dependencies_from_package_json(path, rel))
    entries.sort(key=lambda row: (row.name, row.source_path, row.extra or ""))
    return entries


def _index_under(files: Iterable[FileInventoryEntry], prefix: str) -> Dict[str, str]:
    if prefix == "":
        return {row.path: row.path for row in files}
    prefix_slash = prefix.rstrip("/") + "/"
    indexed: Dict[str, str] = {}
    for row in files:
        if row.path.startswith(prefix_slash):
            indexed[row.path[len(prefix_slash) :]] = row.path
    return indexed


def detect_overlaps_or_duplicates(
    repo_root: Pathish,
    files: Optional[Sequence[FileInventoryEntry]] = None,
) -> List[OverlapOrDuplicateFinding]:
    """Same basename in multiple top-level directories, plus known dual roots.

    Known dual root: repository root vs ``apps/awareness_studio``. Findings
    describe path overlap only; they do not infer labels or science.
    """

    root = _as_root(repo_root)
    rows = list(files) if files is not None else scan_repository_files(root)
    findings: List[OverlapOrDuplicateFinding] = []

    by_basename_tops: Dict[str, set[str]] = {}
    by_basename_paths: Dict[str, List[str]] = {}
    for row in rows:
        base = Path(row.path).name
        if base.lower() in UBIQUITOUS_BASENAMES:
            continue
        parts = row.path.split("/")
        top = parts[0] if len(parts) > 1 else ""
        by_basename_tops.setdefault(base, set()).add(top)
        by_basename_paths.setdefault(base, []).append(row.path)
    for base, tops in sorted(by_basename_tops.items()):
        if len(tops) < 2:
            continue
        paths = sorted(by_basename_paths[base])
        tops_txt = ", ".join(sorted(t if t else "<repo-root>" for t in tops))
        findings.append(
            OverlapOrDuplicateFinding(
                paths=paths,
                reason=f"same basename {base!r} in multiple top-level directories: {tops_txt}",
            )
        )

    for left_prefix, right_prefix in KNOWN_DUAL_ROOTS:
        left = _index_under(rows, left_prefix)
        right = _index_under(rows, right_prefix)
        shared = sorted(set(left) & set(right))
        left_label = left_prefix or "repo-root"
        right_label = right_prefix or "repo-root"
        for rel in shared:
            left_path = left[rel]
            right_path = right[rel]
            if left_path == right_path:
                continue
            findings.append(
                OverlapOrDuplicateFinding(
                    paths=sorted([left_path, right_path]),
                    reason=(
                        f"known dual-root overlap ({left_label} vs {right_label}): {rel}"
                    ),
                )
            )

    findings.sort(key=lambda row: (row.reason, tuple(sorted(row.paths))))
    return findings


def build_inventory_snapshot(
    repo_root: Pathish,
    *,
    include_mtime: bool = False,
) -> InventorySnapshot:
    """Full offline scan. Requires git (fail closed). Writes nothing to disk."""

    root = _as_root(repo_root)
    commit_sha = resolve_commit_sha(root)
    files = scan_repository_files(root, include_mtime=include_mtime)
    return InventorySnapshot(
        repo_root=root.resolve().as_posix(),
        commit_sha=commit_sha,
        files=files,
        worktrees_and_branches=scan_worktrees_and_branches(root),
        artifacts=scan_artifacts(root),
        governance_files=scan_governance_files(root),
        dependencies=scan_dependency_references(root),
        overlaps=detect_overlaps_or_duplicates(root, files=files),
        generated_at=None,
        generated_by=None,
        report_fields={},
    )


def snapshot_to_dict(snapshot: InventorySnapshot) -> Dict[str, Any]:
    """Return a JSON-ready dict with sorted keys at dump time and stable lists."""

    return snapshot.to_dict()


def snapshot_to_json(snapshot: InventorySnapshot, *, indent: int = 2) -> str:
    """Deterministic JSON text (``sort_keys=True``, POSIX trailing newline)."""

    return json.dumps(snapshot.to_dict(), indent=indent, sort_keys=True, ensure_ascii=True) + "\n"


scan_repo = build_inventory_snapshot

__all__ = [
    "ARTIFACT_ROOTS",
    "GitUnavailableError",
    "LARGE_FILE_BYTES",
    "SIZE_PATH_DIGEST_VERSION",
    "build_inventory_snapshot",
    "detect_overlaps_or_duplicates",
    "hash_file",
    "resolve_commit_sha",
    "scan_artifacts",
    "scan_dependency_references",
    "scan_governance_files",
    "scan_repo",
    "scan_repository_files",
    "scan_worktrees_and_branches",
    "size_path_digest",
    "snapshot_to_dict",
    "snapshot_to_json",
]
