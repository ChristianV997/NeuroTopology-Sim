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


def test_write_reports_rejects_output_root_escape(tmp_path: Path):
    """Report destination must stay under a declared trusted root when requested.

    The CLI treats --output as a trusted local path. Callers that pass
    trusted_root get the existing path-containment guard. This is a local
    harness boundary, not a repository-wide security certification.
    """
    from tools.release_readiness.batch2_security.report import write_reports

    trusted = tmp_path / "trusted"
    trusted.mkdir()
    payload = {"schema_version": "test", "security_pass": True, "findings": []}
    with pytest.raises(PathEscapeError):
        write_reports(payload, trusted / ".." / "escape", trusted_root=trusted)


def test_write_reports_accepts_in_root(tmp_path: Path):
    """Valid child of trusted_root is written deterministically."""
    from tools.release_readiness.batch2_security.report import write_reports

    trusted = tmp_path / "trusted"
    trusted.mkdir()
    payload = {"schema_version": "v1", "security_pass": True, "scientific_pass_emitted": False, "findings": []}
    paths = write_reports(payload, "out", trusted_root=trusted)
    assert Path(paths["json"]).is_file()
    assert Path(paths["markdown"]).is_file()
    paths2 = write_reports(payload, "out", trusted_root=trusted)
    assert Path(paths["json"]).read_text() == Path(paths2["json"]).read_text()


def test_write_reports_rejects_symlink_escape(tmp_path: Path):
    """Symlink inside trusted root that targets outside is rejected."""
    from tools.release_readiness.batch2_security.report import write_reports

    trusted = tmp_path / "trusted"
    trusted.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    link = trusted / "link"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation unavailable")
    payload = {"schema_version": "v1", "security_pass": True, "findings": []}
    with pytest.raises(PathEscapeError):
        write_reports(payload, "link", trusted_root=trusted)
