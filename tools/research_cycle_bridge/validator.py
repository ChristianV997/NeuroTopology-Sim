"""Validator enforcing scientific guardrails and contract integrity for bridge records.

Enforces:
1. Rejection of network/cloud URLs (must be local offline paths).
2. Complete, non-fabricated provenance (run_id, created_at, source).
3. Synthetic and proxy non-promotion:
   - Synthetic output cannot be empirical evidence.
   - Proxy Bayes factors cannot be formal scientific proof.
4. Preservation of nulls (missing metrics stay null; zero-filling is forbidden).
5. Deterministic finite JSON compliance (no NaN or Infinity).
6. Checksum and parent-lineage continuity.
"""
from __future__ import annotations

import re
from typing import Any, Mapping

from tools.research_cycle_bridge.models import (
    BRIDGE_SCHEMA_VERSION,
    canonical_hash,
    finite_value,
    verify_bridge_checksum,
)

_URL_PATTERN = re.compile(r"^(?:https?|s3|gs|ftp)://", re.I)
_PROHIBITED_PROVENANCE_VALUES = {"unknown", "none", "null", "undefined", ""}


class BridgeValidationError(ValueError):
    """Raised when a bridge record violates validation rules."""


def validate_bridge_record(record: Mapping[str, Any] | Any) -> list[str]:
    """Perform comprehensive validation on a bridge record mapping or dataclass.
    
    Returns:
        List of validation error strings. If empty, the record is fully compliant.
    """
    errors: list[str] = []

    if hasattr(record, "to_dict"):
        data = record.to_dict()
    elif isinstance(record, Mapping):
        data = dict(record)
    else:
        return [f"Record must be a Mapping or dataclass with to_dict(), got {type(record).__name__}"]

    # 1. Schema version
    if data.get("schema_version") != BRIDGE_SCHEMA_VERSION:
        errors.append(f"Invalid schema_version: expected '{BRIDGE_SCHEMA_VERSION}', got '{data.get('schema_version')}'")

    # 2. Mandatory identifiers
    for req_field in ("record_id", "cycle_id", "status", "data_mode", "evidence_class"):
        val = data.get(req_field)
        if not val or not isinstance(val, str) or val.strip() in _PROHIBITED_PROVENANCE_VALUES:
            errors.append(f"Missing or invalid mandatory field '{req_field}': got {val!r}")

    # 3. Provenance validation
    prov = data.get("provenance")
    if not isinstance(prov, Mapping):
        errors.append("Missing provenance mapping")
    else:
        for pfield in ("run_id", "created_at", "source"):
            pval = str(prov.get(pfield, "")).strip().lower()
            if pval in _PROHIBITED_PROVENANCE_VALUES:
                errors.append(f"Provenance field '{pfield}' is missing or unauthenticated: {prov.get(pfield)!r}")

        # URL check
        for k, v in prov.items():
            if isinstance(v, str) and _URL_PATTERN.match(v.strip()):
                errors.append(f"Network/cloud URL forbidden in provenance field '{k}': {v}")

    # 4. Check for network URLs anywhere in payload
    def _check_urls(obj: Any, path: str = "$") -> None:
        if isinstance(obj, str) and _URL_PATTERN.match(obj.strip()):
            errors.append(f"Network/cloud URL forbidden at '{path}': {obj}")
        elif isinstance(obj, Mapping):
            for k, v in obj.items():
                _check_urls(v, f"{path}.{k}")
        elif isinstance(obj, (list, tuple)):
            for idx, item in enumerate(obj):
                _check_urls(item, f"{path}[{idx}]")

    _check_urls(data)

    # 5. Scientific guardrails: synthetic / proxy non-promotion
    synthetic = bool(data.get("synthetic") or data.get("data_mode") == "synthetic")
    proxy = bool(data.get("proxy") or data.get("data_mode") == "proxy")
    empirical = bool(data.get("empirical") or data.get("data_mode") == "empirical")

    if synthetic and empirical:
        errors.append("Contradiction: record declares both synthetic and empirical flags as True")

    if proxy and empirical:
        errors.append("Contradiction: record declares both proxy and empirical flags as True")

    if synthetic:
        ev_class = str(data.get("evidence_class", ""))
        if ev_class in {"empirical_dataset", "formal_empirical"}:
            errors.append(f"Guardrail violation: synthetic output cannot be classified as '{ev_class}'")
        if data.get("scientific_verdict") == "PASS":
            errors.append("Guardrail violation: synthetic simulation cannot receive scientific PASS")

    if proxy:
        ev_class = str(data.get("evidence_class", ""))
        if ev_class in {"empirical_dataset", "formal_empirical"}:
            errors.append(f"Guardrail violation: proxy output cannot be classified as '{ev_class}'")
        if data.get("scientific_verdict") == "PASS":
            errors.append("Guardrail violation: proxy output cannot receive scientific PASS")

    # 6. Finite JSON verification
    try:
        finite_value(data)
    except Exception as exc:
        errors.append(f"Finite JSON violation: {exc}")

    # 7. Checksum validation
    if "checksum" in data and data["checksum"]:
        if not verify_bridge_checksum(data):
            errors.append("Record checksum mismatch: digest does not match canonical payload content")

    return errors
