"""Phase 5 Integration CLI: write the offline retrofit inventory report bundle.

Calls ``tools.retrofit_inventory.reporting.build_report_bundle``. Does not
reimplement the scanner, tool-source registry, validators, or reports.

Inventory is **not scientific evidence**. Reports never emit scientific
``PASS``. This CLI is offline-only: ``--online`` is refused.

Exit codes: 0 = ok, 1 = incomplete, 2 = error or argparse/path failure.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_PACKAGE_ROOT = _SCRIPT_DIR.parent
if str(_PACKAGE_ROOT) not in sys.path:
    sys.path.insert(0, str(_PACKAGE_ROOT))

from tools.retrofit_inventory.reporting import (
    DEFAULT_OUTPUT_RELATIVE,
    REPORT_FILENAMES,
    STATUS_ERROR,
    STATUS_INCOMPLETE,
    STATUS_OK,
    build_report_bundle,
)

EXIT_OK = 0
EXIT_INCOMPLETE = 1
EXIT_ERROR = 2


class PathPolicyError(ValueError):
    """Fail-closed path / containment error (maps to exit 2)."""


def _has_traversal(raw: str) -> bool:
    return ".." in Path(raw).parts


def resolve_repo_root(raw: str) -> Path:
    """Resolve ``--repo-root``. Fail closed on missing dir or ``..``."""

    if raw is None or not str(raw).strip():
        raise PathPolicyError("repo-root is missing")
    text = str(raw).strip()
    if _has_traversal(text):
        raise PathPolicyError("repo-root must not contain '..' traversal")
    resolved = Path(text).expanduser().resolve()
    if not resolved.exists():
        raise PathPolicyError(f"repo-root does not exist: {text}")
    if not resolved.is_dir():
        raise PathPolicyError(f"repo-root is not a directory: {text}")
    return resolved


def resolve_output_dir(raw: str | None, repo_root: Path) -> Path:
    """Resolve ``--output-dir`` so it stays under ``repo_root``.

    Policy (documented in ``docs/retrofit_inventory_cli.md``):

    - Relative paths are joined to ``repo_root``.
    - Absolute paths are allowed only when they resolve under ``repo_root``.
    - Raw ``..`` segments are rejected (fail closed).
    - Existing parents between ``output_dir`` and ``repo_root`` must be
      directories (not files).
    """

    if raw is None or not str(raw).strip():
        candidate = repo_root / DEFAULT_OUTPUT_RELATIVE
    else:
        text = str(raw).strip()
        if _has_traversal(text):
            raise PathPolicyError("output-dir must not contain '..' traversal")
        given = Path(text).expanduser()
        candidate = given if given.is_absolute() else (repo_root / given)

    repo_resolved = repo_root.resolve()
    resolved = candidate.resolve()
    try:
        resolved.relative_to(repo_resolved)
    except ValueError as exc:
        raise PathPolicyError("output-dir must resolve under repo-root") from exc

    current = resolved
    while current != repo_resolved:
        parent = current.parent
        if parent.exists() and not parent.is_dir():
            raise PathPolicyError(f"output-dir parent is not a directory: {parent}")
        if parent == current:
            break
        current = parent
    return resolved


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="build_retrofit_inventory.py",
        description=(
            "Write the six offline retrofit inventory JSON reports. "
            "Inventory is not scientific evidence and never a scientific PASS."
        ),
    )
    parser.add_argument(
        "--repo-root",
        default=".",
        help="Repository root to inventory (default: .). Must exist; no '..'.",
    )
    parser.add_argument(
        "--output-dir",
        default=None,
        help=(
            "Directory for the six report files "
            f"(default: <repo-root>/{DEFAULT_OUTPUT_RELATIVE}). "
            "Must resolve under repo-root."
        ),
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        default=True,
        help="Stay offline (default; only supported mode).",
    )
    parser.add_argument(
        "--online",
        action="store_true",
        default=False,
        help="Refused: warn and stay offline. No network calls.",
    )
    parser.add_argument(
        "--generated-at",
        default=None,
        help="Optional ISO-8601 timestamp forwarded to reporting (tests).",
    )
    return parser


def _print_summary(bundle: dict) -> None:
    status = bundle.get("status", STATUS_ERROR)
    commit = bundle.get("repository_commit", "")
    names = bundle.get("report_filenames") or list(REPORT_FILENAMES)
    print(f"status: {status}")
    print(f"commit: {commit}")
    print(f"reports: {', '.join(str(name) for name in names)}")


def _exit_for_status(status: str) -> int:
    if status == STATUS_OK:
        return EXIT_OK
    if status == STATUS_INCOMPLETE:
        return EXIT_INCOMPLETE
    return EXIT_ERROR


def run(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
    except SystemExit as exc:
        code = exc.code
        if code is None:
            return EXIT_ERROR
        if isinstance(code, int):
            return code
        return EXIT_ERROR

    try:
        repo_root = resolve_repo_root(args.repo_root)
        output_dir = resolve_output_dir(args.output_dir, repo_root)
    except PathPolicyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    if args.online:
        print(
            "warning: --online is ignored; this CLI is offline-only and "
            "makes no network calls.",
            file=sys.stderr,
        )

    try:
        bundle = build_report_bundle(
            repo_root,
            output_dir=output_dir,
            offline=True,
            generated_at=args.generated_at,
        )
    except (OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR

    _print_summary(bundle)
    return _exit_for_status(str(bundle.get("status", STATUS_ERROR)))


def main(argv: Sequence[str] | None = None) -> int:
    return run(argv)


if __name__ == "__main__":
    raise SystemExit(main())
