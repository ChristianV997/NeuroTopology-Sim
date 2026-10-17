"""Output-root containment, traversal, symlink, and Windows drive escapes."""
from __future__ import annotations

from pathlib import Path

import pytest

from tools.release_readiness.batch2_security.path_containment import (
    PathEscapeError,
    classify_path_threat,
    looks_like_windows_drive,
    resolve_under_root,
)
from tools.release_readiness.batch2_security.schema import ThreatClass


def test_child_path_is_contained(tmp_path: Path):
    (tmp_path / "artifacts").mkdir()
    resolved = resolve_under_root(tmp_path, "artifacts/report.json")
    assert resolved.is_relative_to(tmp_path.resolve())


def test_traversal_is_rejected(tmp_path: Path):
    with pytest.raises(PathEscapeError):
        resolve_under_root(tmp_path, "../etc/passwd")
    assert classify_path_threat(tmp_path, "../etc/passwd") == ThreatClass.OUTPUT_ROOT_ESCAPE.value


def test_absolute_posix_escape(tmp_path: Path):
    assert classify_path_threat(tmp_path, "/tmp/escape") == ThreatClass.OUTPUT_ROOT_ESCAPE.value


def test_windows_drive_escape(tmp_path: Path):
    assert looks_like_windows_drive(r"C:\Windows\System32")
    assert (
        classify_path_threat(tmp_path, r"C:\Windows\System32\config")
        == ThreatClass.WINDOWS_DRIVE_ESCAPE.value
    )


def test_symlink_escape(tmp_path: Path):
    outside = tmp_path.parent / "batch2_outside_secret"
    outside.write_text("secret", encoding="utf-8")
    link = tmp_path / "link"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable")
    assert classify_path_threat(tmp_path, "link") == ThreatClass.SYMLINK_ESCAPE.value
