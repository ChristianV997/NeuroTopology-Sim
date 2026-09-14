"""Strict RFC 8259 finite JSON serialization and SHA-256 integrity verification tools."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Dict, Tuple


def _validate_finite(value: Any) -> Any:
    """Recursively verify that all float numbers in the structure are strictly finite."""
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise ValueError(f"Non-finite float value encountered ({value}); RFC 8259 strictly prohibits NaN/Infinity")
        return value
    if isinstance(value, dict):
        return {str(k): _validate_finite(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_validate_finite(x) for x in value]
    return value


def dumps_rfc8259(payload: Any, indent: int = 2) -> str:
    """Serialize payload to deterministic RFC 8259 JSON, strictly rejecting NaN and Infinity.

    Args:
        payload: Dict or list to serialize.
        indent: Indentation spaces.

    Returns:
        Deterministic formatted JSON string.

    Raises:
        ValueError: If any NaN or Infinity value is present.
    """
    sanitized = _validate_finite(payload)
    return json.dumps(
        sanitized,
        indent=indent,
        ensure_ascii=False,
        sort_keys=True,
        allow_nan=False,
    )


def compute_sha256(content: bytes) -> str:
    """Compute standard hexadecimal SHA-256 digest."""
    return hashlib.sha256(content).hexdigest()


def write_canonical_telemetry(path: str | Path, payload: Dict[str, Any]) -> Tuple[Path, str]:
    """Write deterministic RFC 8259 telemetry file and accompanying .sha256 digest file.

    Args:
        path: Target file path (e.g. results.json).
        payload: Dictionary of telemetry metrics.

    Returns:
        (json_path, sha256_hex_digest) tuple.
    """
    json_path = Path(path).resolve()
    json_path.parent.mkdir(parents=True, exist_ok=True)

    json_str = dumps_rfc8259(payload, indent=2) + "\n"
    raw_bytes = json_str.encode("utf-8")
    digest = compute_sha256(raw_bytes)

    json_path.write_bytes(raw_bytes)

    sha_path = json_path.with_suffix(json_path.suffix + ".sha256")
    sha_content = f"{digest}  {json_path.name}\n"
    sha_path.write_text(sha_content, encoding="utf-8")

    return json_path, digest


def verify_telemetry_digest(path: str | Path) -> Tuple[bool, str]:
    """Verify that a telemetry JSON file matches its companion .sha256 digest file.

    Args:
        path: Path to the .json telemetry file.

    Returns:
        (is_valid, message) tuple.
    """
    json_path = Path(path).resolve()
    if not json_path.is_file():
        return False, f"Telemetry file not found: {json_path}"

    sha_path = json_path.with_suffix(json_path.suffix + ".sha256")
    if not sha_path.is_file():
        return False, f"Companion checksum file not found: {sha_path}"

    actual_digest = compute_sha256(json_path.read_bytes())
    sha_line = sha_path.read_text(encoding="utf-8").strip()
    expected_digest = sha_line.split()[0] if sha_line else ""

    if actual_digest == expected_digest:
        return True, f"Checksum verified: {actual_digest}"
    return False, f"Checksum mismatch: expected {expected_digest}, computed {actual_digest}"
