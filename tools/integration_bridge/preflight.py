"""Preflight validation for the ecosystem-assembly run.

Everything here is a pure check: no file is written, no network call is
made, no adapter is invoked. A ``PreflightReport`` with ``ok=False`` must
stop the pipeline before the ``ingest`` stage runs.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

_HASH_CHUNK_BYTES = 1024 * 1024
_MAX_HASHED_BYTES = 512 * 1024 * 1024  # 512MB cap so preflight cannot be
                                        # used to silently hash an
                                        # arbitrarily large file forever.

# Fields every ingestion request must declare so provenance is
# reconstructable from the packaged artifacts alone (see "package" stage).
REQUIRED_METADATA_FIELDS: tuple[str, ...] = (
    "data_mode",       # "synthetic" | "empirical_local" | "empirical_csv"
    "dataset_id",
    "seed",
)

VALID_DATA_MODES: tuple[str, ...] = ("synthetic", "empirical_local", "empirical_csv")


@dataclass
class PreflightReport:
    ok: bool
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    source_hashes: Dict[str, str] = field(default_factory=dict)
    network_allowed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return {
            "ok": self.ok,
            "errors": list(self.errors),
            "warnings": list(self.warnings),
            "source_hashes": dict(sorted(self.source_hashes.items())),
            "network_allowed": self.network_allowed,
        }


def sha256_of_file(path: Path) -> str:
    """Stream-hash a file in bounded chunks; refuses anything past the cap
    rather than reading an unbounded amount of data into a hash context."""
    digest = hashlib.sha256()
    total = 0
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(_HASH_CHUNK_BYTES)
            if not chunk:
                break
            total += len(chunk)
            if total > _MAX_HASHED_BYTES:
                raise ValueError(
                    f"{path} exceeds the {_MAX_HASHED_BYTES}-byte preflight hashing cap"
                )
            digest.update(chunk)
    return digest.hexdigest()


def validate_paths(input_path: Optional[Path], output_dir: Path) -> List[str]:
    """Path existence / traversal checks. Returns a list of error strings
    (empty = valid)."""
    errors: List[str] = []
    if input_path is not None:
        if not input_path.exists():
            errors.append(f"input path does not exist: {input_path}")
        elif not input_path.is_file():
            errors.append(f"input path is not a regular file: {input_path}")
        elif input_path.is_symlink():
            errors.append(f"input path must not be a symlink: {input_path}")
    if output_dir.exists() and not output_dir.is_dir():
        errors.append(f"output path exists and is not a directory: {output_dir}")
    return errors


def validate_metadata(metadata: Dict[str, Any]) -> List[str]:
    """Required-field + enum checks on the run's declared metadata."""
    errors: List[str] = []
    for field_name in REQUIRED_METADATA_FIELDS:
        if field_name not in metadata or metadata[field_name] in (None, ""):
            errors.append(f"missing required metadata field: {field_name}")
    data_mode = metadata.get("data_mode")
    if data_mode is not None and data_mode not in VALID_DATA_MODES:
        errors.append(
            f"invalid data_mode {data_mode!r}; must be one of {VALID_DATA_MODES}"
        )
    seed = metadata.get("seed")
    if seed is not None and not isinstance(seed, int):
        errors.append("metadata field 'seed' must be an integer for reproducibility")
    return errors


def validate_dependency_profile(
    requested_adapters: tuple[str, ...],
    adapters_available: Dict[str, bool],
) -> List[str]:
    """Every explicitly requested adapter must actually be available given
    the current environment's optional dependencies."""
    errors: List[str] = []
    for adapter in requested_adapters:
        if adapter not in adapters_available:
            errors.append(f"unknown adapter requested: {adapter}")
        elif not adapters_available[adapter]:
            errors.append(
                f"adapter {adapter!r} was requested but its optional "
                "dependencies are not installed in this environment"
            )
    return errors


def resolve_network_permission(
    *,
    live_requested: bool,
    allow_network_flag: bool,
    allow_network_env: str = "NTS_INTEGRATION_ALLOW_NETWORK",
) -> tuple[bool, List[str]]:
    """Refuse network/live mode unless BOTH an explicit CLI flag and an
    explicit environment variable agree — a single opt-in surface (just the
    flag) is not enough, matching this repository's existing fail-closed
    precedent (governance/policy-style dual gates elsewhere in the repo).
    Returns (network_allowed, errors)."""
    if not live_requested:
        return False, []
    env_value = os.environ.get(allow_network_env, "").strip().lower()
    env_allows = env_value in {"1", "true", "yes"}
    if allow_network_flag and env_allows:
        return True, []
    return False, [
        "live/network mode was requested but not explicitly enabled: "
        f"pass --allow-network AND set {allow_network_env}=true"
    ]


def run_preflight(
    *,
    input_path: Optional[Path],
    output_dir: Path,
    metadata: Dict[str, Any],
    requested_adapters: tuple[str, ...],
    adapters_available: Dict[str, bool],
    live_requested: bool = False,
    allow_network_flag: bool = False,
) -> PreflightReport:
    errors: List[str] = []
    warnings: List[str] = []

    errors.extend(validate_paths(input_path, output_dir))
    errors.extend(validate_metadata(metadata))
    errors.extend(
        validate_dependency_profile(requested_adapters, adapters_available)
    )

    network_allowed, network_errors = resolve_network_permission(
        live_requested=live_requested, allow_network_flag=allow_network_flag
    )
    errors.extend(network_errors)

    source_hashes: Dict[str, str] = {}
    if input_path is not None and input_path.exists() and input_path.is_file():
        try:
            source_hashes[str(input_path)] = sha256_of_file(input_path)
        except ValueError as exc:
            errors.append(str(exc))

    if metadata.get("data_mode") == "synthetic" and input_path is not None:
        warnings.append(
            "data_mode='synthetic' but an input_path was also supplied; "
            "the input file is ignored for synthetic runs"
        )

    return PreflightReport(
        ok=not errors,
        errors=errors,
        warnings=warnings,
        source_hashes=source_hashes,
        network_allowed=network_allowed,
    )
