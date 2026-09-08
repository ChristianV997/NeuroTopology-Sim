"""Serialization, atomic JSON persistence, and SHA-256 verification for the Research Cycle Registry.

Enforces:
- Strict RFC-8259 compliance (allow_nan=False).
- Non-finite numbers converted recursively to null (None).
- Atomic file writes with temporary suffix replacement.
- Cryptographic SHA-256 integrity checksumming.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Mapping

from .schema import (
    EvidenceUpdate,
    ExperimentPlan,
    HumanReviewGate,
    HypothesisRecord,
    PredictionRecord,
    TheoryRevision,
    _safe_dict,
)


def compute_record_checksum(record_dict: Mapping[str, Any]) -> str:
    """Compute deterministic SHA-256 digest over canonical JSON representation."""
    canonical = {str(k): v for k, v in record_dict.items() if k != "checksum"}
    canonical_json = json.dumps(canonical, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()


def save_registry_json(data: Mapping[str, Any], output_path: str | Path, indent: int = 2) -> Path:
    """Save registry dictionary to JSON atomically with strict RFC-8259 compliance."""
    out_p = Path(output_path)
    out_p.parent.mkdir(parents=True, exist_ok=True)

    sanitized = _safe_dict(data)
    json_text = json.dumps(sanitized, indent=indent, allow_nan=False)

    temp_p = out_p.with_suffix(f"{out_p.suffix}.tmp")
    try:
        temp_p.write_text(json_text, encoding="utf-8")
        temp_p.replace(out_p)
    finally:
        if temp_p.exists():
            try:
                temp_p.unlink()
            except OSError:
                pass

    return out_p


def load_registry_json(path_or_data: str | Path | Mapping[str, Any]) -> dict[str, Any]:
    """Load and parse registry JSON data from file or mapping."""
    if isinstance(path_or_data, (str, Path)):
        p = Path(path_or_data)
        if not p.exists():
            raise FileNotFoundError(f"Registry file not found: {p}")
        raw_text = p.read_text(encoding="utf-8")
        parsed = json.loads(raw_text)
    elif isinstance(path_or_data, Mapping):
        parsed = dict(path_or_data)
    else:
        raise TypeError(f"Expected path or Mapping, got {type(path_or_data)}")

    if not isinstance(parsed, dict):
        raise ValueError(f"Registry payload must be a JSON object, got {type(parsed)}")

    return parsed


def verify_record_checksum(record_dict: Mapping[str, Any]) -> bool:
    """Check if the recorded checksum matches the computed SHA-256 digest."""
    reported = record_dict.get("checksum", "")
    if not reported:
        return False
    expected = compute_record_checksum(record_dict)
    return reported == expected
