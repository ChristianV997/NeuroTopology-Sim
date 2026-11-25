"""Deterministic serialization, SHA-256 integrity verification, and atomic persistence.

Ensures strict RFC-8259 JSON compliance (no NaN/Inf), deterministic field ordering,
tamper-evident SHA-256 checksum generation, and atomic writes.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Mapping

from .models import _safe_dict
from .rejection import ContractCompatibilityError


def compute_checksum(data: Any) -> str:
    """Compute deterministic SHA-256 hex digest for a contract object or dictionary.

    Excludes any top-level or embedded 'checksum' field so that checksums
    can be verified against the payload content.
    """
    if hasattr(data, "to_dict"):
        payload = data.to_dict()
    elif isinstance(data, Mapping):
        payload = _safe_dict(dict(data))
    else:
        payload = _safe_dict(data)

    if isinstance(payload, dict):
        payload = {k: v for k, v in payload.items() if k != "checksum"}

    canonical_json = json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def verify_checksum(data: Any, expected_checksum: str | None = None) -> bool:
    """Verify integrity of data against an expected or embedded checksum.

    Returns True if valid. Raises ContractCompatibilityError if verification fails.
    """
    if expected_checksum is None:
        if hasattr(data, "checksum"):
            expected_checksum = getattr(data, "checksum")
        elif isinstance(data, Mapping):
            expected_checksum = data.get("checksum")

    if not expected_checksum:
        raise ContractCompatibilityError("No checksum provided or found in artifact to verify.")

    actual = compute_checksum(data)
    if actual != expected_checksum:
        raise ContractCompatibilityError(
            f"Integrity checksum mismatch: expected {expected_checksum[:12]}..., got {actual[:12]}..."
        )
    return True


def to_canonical_json(data: Any, *, indent: int = 2) -> str:
    """Serialize object or dict to RFC-8259 compliant canonical JSON string."""
    if hasattr(data, "to_dict"):
        dict_rep = data.to_dict()
    elif isinstance(data, Mapping):
        dict_rep = _safe_dict(dict(data))
    else:
        dict_rep = _safe_dict(data)

    return json.dumps(
        dict_rep,
        sort_keys=True,
        indent=indent,
        ensure_ascii=True,
        allow_nan=False,
    )


def save_contract_json(
    data: Any,
    filepath: str | Path,
    *,
    attach_checksum: bool = True,
    atomic: bool = True,
) -> str:
    """Save contract object to disk atomically with deterministic checksumming.

    Returns the calculated SHA-256 checksum.
    """
    path = Path(filepath).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)

    if hasattr(data, "to_dict"):
        payload = data.to_dict()
    elif isinstance(data, Mapping):
        payload = dict(data)
    else:
        raise TypeError(f"Cannot serialize object of type {type(data)} to contract JSON.")

    payload = _safe_dict(payload)

    digest = compute_checksum(payload)
    if attach_checksum:
        payload["checksum"] = digest
        if hasattr(data, "checksum"):
            setattr(data, "checksum", digest)

    content = to_canonical_json(payload)

    if atomic:
        temp_dir = path.parent
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=temp_dir, delete=False
        ) as tmp:
            tmp.write(content)
            tmp.flush()
            temp_path = Path(tmp.name)
        temp_path.replace(path)
    else:
        path.write_text(content, encoding="utf-8")

    return digest


def load_contract_json(
    filepath: str | Path,
    *,
    verify_integrity: bool = True,
) -> dict[str, Any]:
    """Load contract JSON file, parse safely, and optionally verify SHA-256 integrity."""
    path = Path(filepath).resolve()
    if not path.is_file():
        raise FileNotFoundError(f"Contract file not found: {path}")

    raw_text = path.read_text(encoding="utf-8")
    try:
        data = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise ContractCompatibilityError(f"Failed to parse contract JSON '{path}': {exc}") from exc

    if not isinstance(data, dict):
        raise ContractCompatibilityError(
            f"Expected JSON object at root of contract '{path}', got {type(data).__name__}"
        )

    if verify_integrity and "checksum" in data and data["checksum"]:
        verify_checksum(data, data["checksum"])

    return data
