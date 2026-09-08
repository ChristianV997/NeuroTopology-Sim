"""Contract version negotiation and schema evolution policies.

Handles protocol version alignment between the hypothesis registry,
Awareness Studio orchestrator, and external evidence stores.
Emits explicit MigrationWarning notices for non-breaking schema evolution
and raises ContractCompatibilityError on major breaking incompatibilities.
"""
from __future__ import annotations

import re
from typing import Any, Sequence

from .models import MigrationWarning
from .rejection import ContractCompatibilityError

SUPPORTED_SCHEMAS: dict[str, list[str]] = {
    "HypothesisRecord": ["HypothesisRecord.v1", "v1.0", "v1.1"],
    "ExperimentPlan": ["ExperimentPlan.v1", "v1.0", "v1.1"],
    "PredictionRecord": ["PredictionRecord.v1", "v1.0"],
    "EvidenceUpdate": ["EvidenceUpdate.v1", "v1.0", "v1.1"],
    "AwarenessHypothesisNode": ["AwarenessHypothesisNode.v1", "v1.0"],
    "AwarenessStudioCycleInput": ["AwarenessStudioCycleInput.v1", "v1.0"],
    "ExperimentLedgerRow": ["ExperimentLedgerRow.v1", "v1.0"],
}

_VERSION_PATTERN = re.compile(
    r"^(?:(?P<schema>[A-Za-z0-9_]+)\.)?[vV]?(?P<major>\d+)(?:\.(?P<minor>\d+))?(?:\.(?P<patch>\d+))?$"
)


def parse_version(version_str: str) -> tuple[str | None, int, int, int]:
    """Parse schema version string into (schema_name, major, minor, patch)."""
    clean = str(version_str).strip()
    match = _VERSION_PATTERN.match(clean)
    if not match:
        raise ContractCompatibilityError(f"Malformed schema version string: '{version_str}'")
    schema_name = match.group("schema")
    major = int(match.group("major"))
    minor = int(match.group("minor") or 0)
    patch = int(match.group("patch") or 0)
    return schema_name, major, minor, patch


def negotiate_contract_version(
    source_version: str,
    target_version: str,
    schema_name: str | None = None,
    allow_cross_schema: bool = True,
) -> tuple[str, list[MigrationWarning]]:
    """Negotiate compatibility between source and target contract versions.

    Parameters
    ----------
    source_version : str
        The version declared by the incoming artifact or record.
    target_version : str
        The desired or host version required by the consumer.
    schema_name : str | None
        Optional schema family identifier (e.g. 'HypothesisRecord').
    allow_cross_schema : bool
        If True, permit adapter conversions across different schema names if major version matches.

    Returns
    -------
    tuple[str, list[MigrationWarning]]
        The agreed contract version string and any migration warnings recorded.

    Raises
    ------
    ContractCompatibilityError
        If major versions differ or incompatible schema types are mixed without allow_cross_schema.
    """
    warnings: list[MigrationWarning] = []

    if not source_version or not str(source_version).strip():
        warnings.append(
            MigrationWarning(
                source_version="unversioned",
                target_version=target_version,
                field_name="schema_version",
                warning_type="missing_source_version",
                message=f"Source version unspecified; assumed compatible with {target_version}.",
            )
        )
        return target_version, warnings

    src_schema, src_maj, src_min, _ = parse_version(source_version)
    tgt_schema, tgt_maj, tgt_min, _ = parse_version(target_version)

    # Schema family match check
    if src_schema and tgt_schema and src_schema != tgt_schema:
        if not allow_cross_schema:
            raise ContractCompatibilityError(
                f"Schema family mismatch: source '{src_schema}' vs target '{tgt_schema}'"
            )
        warnings.append(
            MigrationWarning(
                source_version=source_version,
                target_version=target_version,
                field_name="schema_version",
                warning_type="cross_schema_adaptation",
                message=f"Cross-schema adaptation between '{src_schema}' and '{tgt_schema}'.",
            )
        )

    # Major version break check
    if src_maj != tgt_maj:
        raise ContractCompatibilityError(
            f"Breaking schema major version mismatch: source v{src_maj} is incompatible with target v{tgt_maj}."
        )

    # Minor version adaptation
    if src_min < tgt_min:
        warnings.append(
            MigrationWarning(
                source_version=source_version,
                target_version=target_version,
                field_name="schema_version",
                warning_type="forward_adaptation",
                message=f"Source minor version {src_min} forward-adapted to host minor version {tgt_min}.",
            )
        )
    elif src_min > tgt_min:
        warnings.append(
            MigrationWarning(
                source_version=source_version,
                target_version=target_version,
                field_name="schema_version",
                warning_type="backward_adaptation",
                message=f"Source minor version {src_min} accepted under legacy host minor version {tgt_min}.",
            )
        )

    return target_version, warnings


def get_supported_schema_versions() -> dict[str, list[str]]:
    """Return all supported schemas and their permitted version strings."""
    return {k: list(v) for k, v in SUPPORTED_SCHEMAS.items()}
