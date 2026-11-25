"""Comprehensive test suite for platform compatibility harness.

Tests:
- Windows-style and POSIX-style paths
- mixed separators
- relative and absolute paths
- long paths and extended-length prefixes
- Unicode paths
- symlink available/unavailable detection
- hardlink detection
- atomic JSON writes
- invalid JSON targets
- subprocess timeout and process-tree cleanup
- missing optional dependencies
- NaN/Infinity rejection
- deterministic repeated reports
- capability-aware test decisions
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
import pytest

from tools.platform_compat import (
    CapabilityStatus,
    DependencyStatus,
    IS_WINDOWS,
    atomic_write_json,
    audit_platform_capabilities,
    compare_paths,
    detect_hardlink_capability,
    detect_symlink_capability,
    dumps_finite_json,
    evaluate_test_prerequisite,
    has_unicode_characters,
    is_safe_relative_path,
    normalize_path,
    safe_read_json,
    safe_temp_dir,
    strip_extended_prefix,
    to_extended_length_path,
    to_posix_path,
    to_windows_path,
    run_guarded_subprocess,
    classify_dependency,
)


# 1. Windows-style and POSIX-style paths & mixed separators
def test_path_normalization_styles() -> None:
    # POSIX style
    p_posix = "folder/subfolder/file.json"
    assert to_posix_path(p_posix) == "folder/subfolder/file.json"
    assert to_windows_path(p_posix) == r"folder\subfolder\file.json"

    # Windows style
    p_win = r"folder\subfolder\file.json"
    assert to_posix_path(p_win) == "folder/subfolder/file.json"
    assert to_windows_path(p_win) == r"folder\subfolder\file.json"

    # Mixed separators & redundant slashes
    p_mixed = r"folder/subfolder\\nested//./leaf.txt"
    norm_posix = normalize_path(p_mixed, as_posix=True)
    assert norm_posix == "folder/subfolder/nested/leaf.txt"

    # Empty path handling
    assert normalize_path("") == ""
    assert to_posix_path("") == ""
    assert to_windows_path("") == ""


# 2. Path comparison and platform-appropriate case-folding
def test_path_comparison_and_case_sensitivity() -> None:
    # Same logical path with different separators
    assert compare_paths("a/b/c.json", r"a\b\c.json")
    assert compare_paths("a/b/../b/c.json", "a/b/c.json")

    # Case folding on Windows
    if IS_WINDOWS:
        assert compare_paths(r"C:\Neuro\Data.json", "c:/neuro/data.json")
    else:
        assert not compare_paths("/opt/Neuro/Data.json", "/opt/neuro/data.json", case_sensitive=True)

    # Distinct paths
    assert not compare_paths("a/b/c.json", "a/b/d.json")


# 3. Long paths and extended length prefixes (\\?\)
def test_long_paths_extended_prefix() -> None:
    path_str = r"C:\Very\Long\Path\To\Some\Deep\Nested\Directory\Structure\File.txt"
    ext_path = to_extended_length_path(path_str)

    if IS_WINDOWS:
        assert ext_path.startswith("\\\\?\\")
        assert strip_extended_prefix(ext_path) == os.path.abspath(path_str)
    else:
        assert ext_path == path_str

    # Redundant prefix call should be idempotent
    assert to_extended_length_path(ext_path) == ext_path


# 4. Unicode paths
def test_unicode_paths() -> None:
    ascii_path = "data/cohort_01/results.json"
    unicode_path = "данные/папка_β/результаты_Ω.json"

    assert not has_unicode_characters(ascii_path)
    assert has_unicode_characters(unicode_path)

    with safe_temp_dir(prefix="test_unicode_") as tmp:
        uni_dir = tmp / "испытание_αβγ"
        uni_dir.mkdir()
        uni_file = uni_dir / "тест.txt"
        uni_file.write_text("unicode_content_123_✓", encoding="utf-8")

        assert uni_file.exists()
        assert uni_file.read_text(encoding="utf-8") == "unicode_content_123_✓"


# 5. Directory traversal safety
def test_safe_relative_path() -> None:
    base = Path("/safe/base/dir") if not IS_WINDOWS else Path(r"C:\safe\base\dir")
    assert is_safe_relative_path("child/grandchild.json", base_dir=base)
    assert not is_safe_relative_path("../../outside.json", base_dir=base)


# 6. Symlink capability detection
def test_symlink_capability_detection() -> None:
    res = detect_symlink_capability()
    assert res.name == "symlinks"
    assert res.status in (
        CapabilityStatus.AVAILABLE,
        CapabilityStatus.PERMISSION_DENIED,
        CapabilityStatus.UNSUPPORTED,
    )
    # If permission denied on Windows, verify it reports the privilege requirement
    if res.status == CapabilityStatus.PERMISSION_DENIED:
        assert "Developer Mode" in res.details or "privilege" in res.details.lower()


# 7. Hardlink capability detection
def test_hardlink_capability_detection() -> None:
    res = detect_hardlink_capability()
    assert res.name == "hardlinks"
    assert res.status in (
        CapabilityStatus.AVAILABLE,
        CapabilityStatus.UNSUPPORTED,
        CapabilityStatus.PERMISSION_DENIED,
    )


# 8. Atomic JSON writes and sibling tempfile cleanup
def test_atomic_json_writes_success() -> None:
    with safe_temp_dir(prefix="test_atomic_") as tmp:
        target = tmp / "sub" / "output.json"
        payload = {"model": "NeuroTopology", "runs": [1, 2, 3], "enabled": True}

        result_path = atomic_write_json(target, payload)
        assert result_path == target
        assert target.is_file()

        # Verify parsed content
        read_back = safe_read_json(target)
        assert read_back == payload

        # Verify no stray .tmp files left in directory
        tmp_files = list(target.parent.glob(".tmp_*"))
        assert len(tmp_files) == 0


# 9. Atomic JSON writes on invalid targets
def test_atomic_json_writes_invalid_targets() -> None:
    with safe_temp_dir(prefix="test_atomic_err_") as tmp:
        # Target is an existing directory
        existing_dir = tmp / "existing_dir"
        existing_dir.mkdir()
        with pytest.raises(IsADirectoryError):
            atomic_write_json(existing_dir, {"data": 123})

        # Non-existent parent when ensure_parents=False
        non_existent_parent = tmp / "does_not_exist" / "file.json"
        with pytest.raises(FileNotFoundError):
            atomic_write_json(non_existent_parent, {"data": 123}, ensure_parents=False)


# 10. NaN and Infinity rejection in JSON serialization
def test_nan_infinity_rejection() -> None:
    data_nan = {"score": float("nan")}
    data_inf = {"metric": float("inf")}
    data_neginf = {"bound": float("-inf")}

    # Default strict mode: ValueError raised
    with pytest.raises(ValueError, match="non-finite"):
        dumps_finite_json(data_nan)

    with pytest.raises(ValueError, match="non-finite"):
        dumps_finite_json(data_inf)

    with pytest.raises(ValueError, match="non-finite"):
        dumps_finite_json(data_neginf)

    # replace_non_finite=True mode: replaces with null (None)
    clean_json = dumps_finite_json(data_nan, replace_non_finite=True)
    parsed = json.loads(clean_json)
    assert parsed["score"] is None

    clean_inf = dumps_finite_json(data_inf, replace_non_finite=True)
    assert json.loads(clean_inf)["metric"] is None


# 11. Subprocess timeout and child process-tree cleanup
def test_subprocess_timeout_and_cleanup() -> None:
    # Spawn a python process that sleeps for 10 seconds with 0.5s timeout
    cmd = [sys.executable, "-c", "import time; time.sleep(10)"]
    res = run_guarded_subprocess(cmd, timeout=0.5)

    assert res.timed_out is True
    assert res.returncode is None
    assert res.duration_seconds >= 0.4
    assert len(res.terminated_children) >= 1


# 12. Optional dependency classification
def test_optional_dependency_classification() -> None:
    # Standard library or base dependency
    res_py = classify_dependency("sys")
    assert res_py.status == DependencyStatus.AVAILABLE

    # Known missing fake module
    res_fake = classify_dependency("definitely_not_a_real_python_package_xyz_999")
    assert res_fake.status == DependencyStatus.MISSING
    assert res_fake.version is None


# 13. Deterministic repeated audit reports
def test_deterministic_repeated_reports() -> None:
    report1 = audit_platform_capabilities()
    report2 = audit_platform_capabilities()

    # Checksum over static capabilities and dependencies must be 100% deterministic
    assert report1.deterministic_checksum == report2.deterministic_checksum
    assert len(report1.deterministic_checksum) == 64

    # Capabilities and dependency names must match
    assert set(report1.capabilities.keys()) == set(report2.capabilities.keys())
    assert set(report1.dependencies.keys()) == set(report2.dependencies.keys())


# 14. Capability-aware test decisions
def test_capability_aware_test_decisions() -> None:
    # Test for existing base feature
    decision_sys = evaluate_test_prerequisite("sys")
    assert decision_sys.can_run is True
    assert decision_sys.status == CapabilityStatus.AVAILABLE

    # Test for missing dependency
    decision_missing = evaluate_test_prerequisite("nonexistent_package_98765")
    assert decision_missing.can_run is False
    assert decision_missing.status == CapabilityStatus.UNAVAILABLE
    assert "not installed" in decision_missing.reason
    assert "Install" in decision_missing.mitigation
