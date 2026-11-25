"""Output-root containment: traversal, symlink, and Windows drive escapes."""
from __future__ import annotations

import os
import re
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import List, Optional, Tuple

from tools.release_readiness.batch2_security.schema import (
    REMEDIATION_OWNERS,
    Finding,
    ThreatClass,
)

_WINDOWS_DRIVE = re.compile(r"^[A-Za-z]:[\\/]")


class PathEscapeError(ValueError):
    """Raised when a candidate path escapes the declared output root."""


def looks_like_windows_drive(candidate: str) -> bool:
    return bool(_WINDOWS_DRIVE.match(candidate)) or candidate.startswith("\\\\")


def _is_under(root: Path, candidate: Path) -> bool:
    try:
        return candidate.is_relative_to(root)
    except AttributeError:  # pragma: no cover - older Python
        try:
            return os.path.commonpath([str(root), str(candidate)]) == str(root)
        except ValueError:
            return False


def resolve_under_root(root: Path, candidate: str | Path, *, follow_symlinks: bool = True) -> Path:
    """Resolve ``candidate`` and require it stays inside ``root``.

    Rejects ``..`` traversal, absolute escapes, Windows drive letters on
    non-Windows interpreters (treated as escape), and symlink targets that
    leave the root when ``follow_symlinks`` is True.
    """
    root_resolved = root.expanduser().resolve()
    raw = str(candidate)

    if looks_like_windows_drive(raw) and (raw.startswith("\\\\") or not Path(raw).is_absolute()):
        # On POSIX CI agents a Windows drive path cannot be contained under a
        # POSIX root; on Windows, let absolute paths proceed to root comparison.
        raise PathEscapeError(f"windows drive escape: {raw}")

    pure = PureWindowsPath(raw) if "\\" in raw and not raw.startswith("/") else PurePosixPath(raw)
    if pure.is_absolute() and not Path(raw).is_absolute():
        # Defensive: PureWindows absolute without local absolute meaning.
        raise PathEscapeError(f"absolute path escape: {raw}")

    if Path(raw).is_absolute():
        # Absolute candidates are never rewritten under root.
        joined = Path(raw)
        if follow_symlinks:
            joined = joined.resolve()
        if not _is_under(root_resolved, joined):
            raise PathEscapeError(f"absolute path escape: {raw}")
        return joined

    # Lexical join first so we can detect in-root symlinks before resolve().
    lexical = root_resolved / Path(raw)
    if follow_symlinks and lexical.is_symlink():
        target = lexical.resolve()
        if not _is_under(root_resolved, target):
            raise PathEscapeError(f"symlink escape: {raw} -> {target}")
        return target

    joined = lexical.resolve()
    if not _is_under(root_resolved, joined):
        raise PathEscapeError(f"output root escape: {raw}")

    return joined


def classify_path_threat(root: Path, candidate: str, *, follow_symlinks: bool = True) -> Optional[str]:
    """Return a ThreatClass value when candidate escapes; otherwise None."""
    raw = str(candidate)
    if looks_like_windows_drive(raw) and (raw.startswith("\\\\") or not Path(raw).is_absolute()):
        return ThreatClass.WINDOWS_DRIVE_ESCAPE.value
    try:
        resolve_under_root(root, candidate, follow_symlinks=follow_symlinks)
        return None
    except PathEscapeError as exc:
        msg = str(exc).lower()
        if "symlink" in msg:
            return ThreatClass.SYMLINK_ESCAPE.value
        if "windows" in msg or looks_like_windows_drive(raw):
            return ThreatClass.WINDOWS_DRIVE_ESCAPE.value
        return ThreatClass.OUTPUT_ROOT_ESCAPE.value


def evaluate_path_cases(
    root: Path,
    cases: List[Tuple[str, str, bool]],
) -> List[Finding]:
    """Evaluate (fixture_id, candidate, should_escape) cases into findings.

    A case *passes* the harness when escape expectation matches detection.
    Findings are emitted for every detected escape (expected=True when intended).
    """
    findings: List[Finding] = []
    for fixture_id, candidate, should_escape in cases:
        threat = classify_path_threat(root, candidate)
        escaped = threat is not None
        if escaped != should_escape:
            findings.append(
                Finding(
                    threat_class=threat or ThreatClass.OUTPUT_ROOT_ESCAPE.value,
                    severity="critical",
                    message=(
                        f"path containment mismatch for {candidate!r}: "
                        f"escaped={escaped} expected_escape={should_escape}"
                    ),
                    fixture_id=fixture_id,
                    location=candidate,
                    remediation_owners=list(
                        REMEDIATION_OWNERS[ThreatClass.OUTPUT_ROOT_ESCAPE.value]
                    ),
                    expected=False,
                )
            )
            continue
        if escaped and threat is not None:
            findings.append(
                Finding(
                    threat_class=threat,
                    severity="error",
                    message=f"rejected escaping path {candidate!r}",
                    fixture_id=fixture_id,
                    location=candidate,
                    remediation_owners=list(REMEDIATION_OWNERS.get(threat, [])),
                    expected=True,
                )
            )
    return findings
