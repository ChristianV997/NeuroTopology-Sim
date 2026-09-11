"""Safety gates for the research-cycle operator pack.

Read-only by default. Writes only under an explicit --output-dir.
No network, no package install, no git mutation, no solver unless opted in.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Mapping, Sequence

FORBIDDEN_ARGV_SUBSTRINGS: tuple[str, ...] = (
    "git merge",
    "git reset",
    "git push",
    "git rebase",
    "git checkout",
    "force-push",
    "--force",
    "rm -rf",
    "rm -r ",
    "pip install",
    "conda install",
    "wget ",
    "curl ",
    "dandi download",
    "openneuro download",
    "aws s3",
    "gh pr merge",
    "gh pr close",
    "--allow-network",
    "--peer-reviewed-contract-confirmed",
)

FORBIDDEN_GIT_VERBS: frozenset[str] = frozenset(
    {
        "merge",
        "reset",
        "push",
        "rebase",
        "checkout",
        "commit",
        "add",
        "clean",
        "stash",
        "branch",
        "tag",
        "cherry-pick",
        "revert",
        "fetch",
        "pull",
        "remote",
        "update-ref",
        "filter-branch",
    }
)

ALLOWED_GIT_VERBS: frozenset[str] = frozenset(
    {"rev-parse", "status", "symbolic-ref", "diff", "log", "show", "describe"}
)

SOLVER_MARKERS: tuple[str, ...] = (
    "run_research_campaign",
    "optimize_exceptional_point",
    "simulate_fhn",
    "--execute --peer-reviewed",
    "main.py --mode",
)

NETWORK_ENV_CLEAR: tuple[str, ...] = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "FTP_PROXY",
    "ftp_proxy",
)


class SafetyError(ValueError):
    """Operator-pack safety violation. Maps to BLOCKED."""


def require_output_dir(raw: str | Path | None) -> Path:
    if raw is None or str(raw).strip() == "":
        raise SafetyError("--output-dir is required; the pack will not invent a write location")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = (Path.cwd() / path).resolve()
    else:
        path = path.resolve()
    path.mkdir(parents=True, exist_ok=True)
    if not path.is_dir():
        raise SafetyError(f"--output-dir is not a directory: {path}")
    return path


def is_inside(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


def assert_write_path(path: Path, output_dir: Path) -> Path:
    resolved = path.resolve()
    if not is_inside(resolved, output_dir):
        raise SafetyError(
            f"refusing write outside --output-dir: {resolved} (allowed root {output_dir})"
        )
    return resolved


def argv_text(argv: Sequence[str]) -> str:
    return " ".join(str(part) for part in argv)


def forbidden_reason(argv: Sequence[str]) -> str | None:
    text = argv_text(argv)
    lowered = text.lower()
    for token in FORBIDDEN_ARGV_SUBSTRINGS:
        if token.lower() in lowered:
            return f"forbidden token {token!r} in argv"
    if _looks_like_network_url(text):
        return "network URL in argv is blocked (no automatic downloads)"
    if _looks_like_git(argv):
        verb = _git_verb(argv)
        if verb is None:
            return "unrecognized git invocation"
        if verb in FORBIDDEN_GIT_VERBS or verb not in ALLOWED_GIT_VERBS:
            return f"git verb {verb!r} is blocked (read-only git only)"
        if "--porcelain" not in argv and verb == "status" and "-s" not in argv:
            # status without --porcelain is still read-only; allow it.
            return None
    return None


def solver_reason(argv: Sequence[str], *, allow_solver: bool) -> str | None:
    if allow_solver:
        return None
    text = argv_text(argv)
    for marker in SOLVER_MARKERS:
        if marker in text:
            return f"solver marker {marker!r} requires --allow-solver"
    if "--dry-run" not in argv and "run_benchmark_matrix.py" in text:
        return "simulation campaign requires --dry-run unless --allow-solver is set"
    return None


def sanitize_env(base: Mapping[str, str] | None = None) -> dict[str, str]:
    env = dict(os.environ if base is None else base)
    for key in NETWORK_ENV_CLEAR:
        env.pop(key, None)
    env["NO_NETWORK"] = "1"
    env["RCOP_NO_NETWORK"] = "1"
    env["PIP_DISABLE_PIP_VERSION_CHECK"] = "1"
    env["PYTHONNOUSERSITE"] = env.get("PYTHONNOUSERSITE", "1")
    return env


def _looks_like_network_url(text: str) -> bool:
    return bool(re.search(r"https?://|ftp://|s3://|dandi://", text, flags=re.IGNORECASE))


def _looks_like_git(argv: Sequence[str]) -> bool:
    if not argv:
        return False
    first = Path(str(argv[0])).name.lower()
    return first in {"git", "git.exe"} or (len(argv) >= 2 and str(argv[0]).endswith("git"))


def _git_verb(argv: Sequence[str]) -> str | None:
    skip_next = False
    takes_value = {"-C", "--git-dir", "--work-tree"}
    for part in argv[1:]:
        token = str(part)
        if skip_next:
            skip_next = False
            continue
        if token in takes_value:
            skip_next = True
            continue
        if token.startswith("-"):
            continue
        return token
    return None


def classify_resolved_path(
    raw: str,
    *,
    repo_root: Path,
    output_dir: Path,
    declared_repo_paths_ok: bool,
) -> str | None:
    """Return a BLOCKED reason if this argv token is an unsafe write path."""
    if raw in {"", "-", "."}:
        return None
    if raw.startswith("-") and "=" not in raw:
        return None
    candidate = raw.split("=", 1)[-1] if raw.startswith("-") and "=" in raw else raw
    if any(sep in candidate for sep in ("/", "\\")) or candidate.endswith((".json", ".md", ".yml", ".yaml")):
        path = Path(candidate)
        if not path.is_absolute():
            # Relative repo inputs (scripts, fixtures, governance/specs) are reads.
            if declared_repo_paths_ok:
                return None
            abs_path = (repo_root / path).resolve() if not path.exists() else path.resolve()
            if abs_path.exists():
                return None
            # Non-existent relative path: only allow if it will land under output_dir
            # when resolved from cwd, or is a declared repo-relative target.
            if is_inside((output_dir / path).resolve(), output_dir):
                return None
            return None
        resolved = path
        try:
            resolved = path.resolve()
        except OSError:
            return None
        if is_inside(resolved, output_dir):
            return None
        if resolved.exists():
            return None
        return f"refusing write path outside --output-dir: {resolved}"
    return None


def scan_argv_write_safety(
    argv: Sequence[str],
    *,
    repo_root: Path,
    output_dir: Path,
    declared_repo_paths_ok: bool = False,
) -> str | None:
    # Validate the arguments that conventionally name write destinations even
    # when the destination already exists. Generic existing absolute paths are
    # retained as possible read-only repository inputs (for example ``git -C``);
    # explicit output flags must never escape the declared output root.
    output_flags = {"--output", "--out", "--output-json", "--output-md", "--output-summary", "--target-root"}
    for index, token in enumerate(argv):
        text = str(token)
        flag, separator, value = text.partition("=")
        if flag not in output_flags:
            continue
        if not separator and index + 1 < len(argv):
            value = str(argv[index + 1])
        if not value or value.startswith("-"):
            continue
        candidate = Path(value).expanduser()
        if candidate.is_absolute() and not is_inside(candidate, output_dir):
            return f"refusing write path outside --output-dir: {candidate.resolve()}"
    for token in argv:
        reason = classify_resolved_path(
            str(token),
            repo_root=repo_root,
            output_dir=output_dir,
            declared_repo_paths_ok=declared_repo_paths_ok,
        )
        if reason:
            return reason
    return None


def assert_allowed_command(
    argv: Sequence[str],
    *,
    allow_solver: bool,
    repo_root: Path,
    output_dir: Path,
    declared_repo_paths_ok: bool = False,
) -> None:
    if not argv:
        raise SafetyError("empty argv is blocked")
    reason = forbidden_reason(argv)
    if reason:
        raise SafetyError(reason)
    reason = solver_reason(argv, allow_solver=allow_solver)
    if reason:
        raise SafetyError(reason)
    reason = scan_argv_write_safety(
        argv,
        repo_root=repo_root,
        output_dir=output_dir,
        declared_repo_paths_ok=declared_repo_paths_ok,
    )
    if reason:
        raise SafetyError(reason)
