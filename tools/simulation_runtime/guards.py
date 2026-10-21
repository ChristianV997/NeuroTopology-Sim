"""Resource budget guards and pre-execution admission checks for simulation units.
"""
from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path
from typing import List, Optional, Sequence, Tuple, Union

try:
    import psutil  # type: ignore
    _PSUTIL = psutil
except Exception:
    _PSUTIL = None

PathLike = Union[str, Path]


def check_disk_budget(
    target_dir: PathLike,
    required_mb: float,
    min_free_mb: float,
) -> Tuple[bool, str, float]:
    """Verify that the target filesystem has sufficient free space.

    Args:
        target_dir: Path to directory where artifacts will be written.
        required_mb: Estimated disk space required by the work unit in MB.
        min_free_mb: Minimum required safety headroom in MB.

    Returns:
        (passed, reason, free_mb)
    """
    path = Path(target_dir).resolve()
    # Find existing ancestor directory
    while not path.exists() and path != path.parent:
        path = path.parent

    try:
        usage = shutil.disk_usage(str(path))
        free_mb = usage.free / (1024.0 * 1024.0)
    except Exception as exc:
        return False, f"Could not inspect disk usage: {exc}", 0.0

    threshold_mb = required_mb + min_free_mb
    if free_mb < threshold_mb:
        return (
            False,
            f"Insufficient disk space: {free_mb:.1f} MB available, but {threshold_mb:.1f} MB required "
            f"({required_mb:.1f} MB unit estimate + {min_free_mb:.1f} MB safety budget)",
            free_mb,
        )
    return True, f"Disk budget check passed ({free_mb:.1f} MB available)", free_mb


def check_memory_budget(
    estimated_mb: float,
    max_memory_mb: float,
) -> Tuple[bool, str, float]:
    """Verify that estimated memory fits within the campaign memory policy.

    Args:
        estimated_mb: Estimated memory usage in MB for the work unit.
        max_memory_mb: Maximum memory allowed per work unit.

    Returns:
        (passed, reason, current_system_available_mb)
    """
    avail_mb = -1.0
    if _PSUTIL is not None:
        try:
            avail_mb = _PSUTIL.virtual_memory().available / (1024.0 * 1024.0)
        except Exception:
            pass

    if estimated_mb > max_memory_mb:
        return (
            False,
            f"Work unit estimated memory ({estimated_mb:.1f} MB) exceeds maximum allowed memory budget "
            f"({max_memory_mb:.1f} MB)",
            avail_mb,
        )

    if avail_mb > 0 and avail_mb < estimated_mb:
        return (
            False,
            f"Current system available memory ({avail_mb:.1f} MB) is below work unit requirement "
            f"({estimated_mb:.1f} MB)",
            avail_mb,
        )

    return True, "Memory budget check passed", avail_mb


def check_dependencies(dependencies: Sequence[str]) -> Tuple[bool, List[str]]:
    """Check availability of required Python modules and system binaries.

    Args:
        dependencies: Sequence of module names or command binaries.

    Returns:
        (all_present, missing_list)
    """
    missing: List[str] = []
    for dep in dependencies:
        dep_str = str(dep).strip()
        if not dep_str:
            continue
        # Check if available as python module
        try:
            spec = importlib.util.find_spec(dep_str)
            if spec is not None:
                continue
        except Exception:
            pass

        # Check if available as executable on PATH
        if shutil.which(dep_str) is not None:
            continue

        missing.append(dep_str)

    return len(missing) == 0, missing
