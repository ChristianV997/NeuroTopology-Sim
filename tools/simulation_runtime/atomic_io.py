"""Atomic file operations, JSON serialization, and cryptographic hashing utilities.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional, Union

PathLike = Union[str, Path]


def json_safe(value: Any) -> Any:
    """Recursively convert data to finite JSON-safe structures.

    NaN and infinite floating point values are converted to None.
    Sets and tuples are converted to lists.
    Enums are converted to their underlying value.
    """
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if hasattr(value, "value") and not isinstance(value, (dict, list)):
        # Enum or similar
        return json_safe(value.value)
    if isinstance(value, dict):
        return {str(k): json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [json_safe(v) for v in value]
    # Check for numpy numeric types without hard-importing numpy
    type_name = type(value).__name__
    if "float" in type_name.lower():
        try:
            f = float(value)
            return f if math.isfinite(f) else None
        except Exception:
            return None
    if "int" in type_name.lower():
        try:
            return int(value)
        except Exception:
            return None
    return value


def write_atomic_json(path: PathLike, data: Any, *, indent: Optional[int] = 2) -> Path:
    """Write data to a file atomically via temp file in the same directory + os.replace.

    Guarantees that readers never observe partial or corrupt files.
    Enforces finite JSON serialization (allow_nan=False).
    """
    target = Path(path).resolve()
    target.parent.mkdir(parents=True, exist_ok=True)
    clean_data = json_safe(data)
    encoded = json.dumps(clean_data, indent=indent, allow_nan=False)

    fd, tmp_path = tempfile.mkstemp(
        dir=str(target.parent),
        prefix=f".{target.name}.",
        suffix=".tmp",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(encoded)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, target)
    finally:
        if os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
    return target


def load_json(path: PathLike) -> Any:
    """Safely load JSON from file."""
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def compute_sha256(path: PathLike) -> str:
    """Compute hex SHA-256 digest of a file."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def compute_config_hash(data: Any) -> str:
    """Compute deterministic SHA-256 digest of arbitrary configuration data."""
    safe = json_safe(data)
    canonical = json.dumps(safe, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def get_git_commit(cwd: Optional[PathLike] = None) -> str:
    """Retrieve the current git commit hash, or 'unknown' if unavailable."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            check=False,
            timeout=5.0,
        )
        if res.returncode == 0:
            commit = res.stdout.strip()
            if commit:
                return commit
    except Exception:
        pass
    return "unknown"
