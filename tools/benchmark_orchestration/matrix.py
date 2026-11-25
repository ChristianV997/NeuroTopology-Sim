"""Load and validate declarative benchmark matrices."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from tools.benchmark_orchestration.schema import (
    MATRIX_SCHEMA_VERSION,
    CaseSpec,
    MatrixSpec,
)

PathLike = Union[str, Path]

# Substrings that imply non-local / networked execution by default.
_NETWORK_OR_REMOTE_MARKERS = (
    "aws ",
    "awscli",
    "docker ",
    "docker.exe",
    "curl ",
    "wget ",
    "http://",
    "https://",
    "s3://",
    "ssh ",
    "scp ",
    "gh pr merge",
    "kubectl ",
)


class MatrixValidationError(ValueError):
    """Raised when a matrix document is malformed or inconsistent."""


def _load_raw(path: Path) -> Dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise MatrixValidationError(f"empty matrix file: {path}")
    suffix = path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore
        except ImportError as exc:  # pragma: no cover
            raise MatrixValidationError(
                "PyYAML is required to load YAML matrices; use JSON or install pyyaml"
            ) from exc
        data = yaml.safe_load(text)
    else:
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise MatrixValidationError(f"invalid JSON matrix: {path}") from exc
    if not isinstance(data, dict):
        raise MatrixValidationError("matrix root must be a mapping/object")
    return data


def _as_command(value: Any, case_id: str) -> List[str]:
    if isinstance(value, str):
        # Split conservatively on whitespace for string commands.
        parts = value.split()
        if not parts:
            raise MatrixValidationError(f"case {case_id!r}: empty command")
        return parts
    if isinstance(value, list) and all(isinstance(x, (str, int, float)) for x in value):
        parts = [str(x) for x in value]
        if not parts:
            raise MatrixValidationError(f"case {case_id!r}: empty command")
        return parts
    raise MatrixValidationError(f"case {case_id!r}: command must be a string or list of scalars")


def _command_implies_network(command: List[str]) -> Optional[str]:
    joined = " ".join(command).lower()
    for marker in _NETWORK_OR_REMOTE_MARKERS:
        if marker.strip().lower() in joined:
            return marker.strip()
    return None


def validate_matrix(data: Dict[str, Any], *, local_only: bool = True) -> MatrixSpec:
    """Validate a raw matrix dict and return a :class:`MatrixSpec`.

    Raises :class:`MatrixValidationError` on any structural problem, including
    duplicate case IDs and (when ``local_only``) networked commands.
    """
    if not isinstance(data, dict):
        raise MatrixValidationError("matrix root must be a mapping/object")

    schema_version = str(data.get("schema_version", MATRIX_SCHEMA_VERSION))
    if schema_version != MATRIX_SCHEMA_VERSION:
        raise MatrixValidationError(
            f"unsupported schema_version {schema_version!r}; expected {MATRIX_SCHEMA_VERSION!r}"
        )

    defaults = data.get("defaults") or {}
    if not isinstance(defaults, dict):
        raise MatrixValidationError("defaults must be a mapping")

    raw_cases = data.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise MatrixValidationError("cases must be a non-empty list")

    default_timeout = int(defaults.get("timeout_s", 60))
    default_retries = int(defaults.get("max_retries", 0))
    default_optional = list(defaults.get("optional_deps") or [])
    if default_timeout < 1:
        raise MatrixValidationError("defaults.timeout_s must be >= 1")
    if default_retries < 0:
        raise MatrixValidationError("defaults.max_retries must be >= 0")

    seen: set[str] = set()
    cases: List[CaseSpec] = []
    for idx, raw in enumerate(raw_cases):
        if not isinstance(raw, dict):
            raise MatrixValidationError(f"cases[{idx}] must be a mapping")
        case_id = raw.get("id") or raw.get("case_id")
        if not isinstance(case_id, str) or not case_id.strip():
            raise MatrixValidationError(f"cases[{idx}]: missing non-empty id/case_id")
        case_id = case_id.strip()
        if case_id in seen:
            raise MatrixValidationError(f"duplicate case id: {case_id!r}")
        seen.add(case_id)

        command = _as_command(raw.get("command"), case_id)
        timeout_s = int(raw.get("timeout_s", default_timeout))
        max_retries = int(raw.get("max_retries", default_retries))
        if timeout_s < 1:
            raise MatrixValidationError(f"case {case_id!r}: timeout_s must be >= 1")
        if max_retries < 0:
            raise MatrixValidationError(f"case {case_id!r}: max_retries must be >= 0")

        optional_deps = list(raw.get("optional_deps") or default_optional)
        if not all(isinstance(d, str) for d in optional_deps):
            raise MatrixValidationError(f"case {case_id!r}: optional_deps must be strings")

        config = raw.get("config") or {}
        if not isinstance(config, dict):
            raise MatrixValidationError(f"case {case_id!r}: config must be a mapping")

        tags = list(raw.get("tags") or [])
        if not all(isinstance(t, str) for t in tags):
            raise MatrixValidationError(f"case {case_id!r}: tags must be strings")

        mem_ref = raw.get("memory_telemetry_ref")
        if mem_ref is not None and not isinstance(mem_ref, str):
            raise MatrixValidationError(f"case {case_id!r}: memory_telemetry_ref must be a string")

        cwd = raw.get("cwd")
        if cwd is not None and not isinstance(cwd, str):
            raise MatrixValidationError(f"case {case_id!r}: cwd must be a string")

        case_local_only = bool(raw.get("local_only", True))
        if local_only and case_local_only:
            hit = _command_implies_network(command)
            if hit is not None:
                raise MatrixValidationError(
                    f"case {case_id!r}: command appears non-local ({hit!r}); "
                    "local_only matrices reject network/remote markers"
                )

        cases.append(
            CaseSpec(
                case_id=case_id,
                command=command,
                timeout_s=timeout_s,
                max_retries=max_retries,
                optional_deps=optional_deps,
                config=dict(config),
                tags=tags,
                memory_telemetry_ref=mem_ref,
                cwd=cwd,
                local_only=case_local_only,
            )
        )

    # Deterministic ordering: lexicographic by case_id (stable across platforms).
    cases = sorted(cases, key=lambda c: c.case_id)

    provenance = str(data.get("provenance_label") or "benchmark-orchestration")
    return MatrixSpec(
        schema_version=schema_version,
        cases=cases,
        defaults=dict(defaults),
        provenance_label=provenance,
    )


def load_matrix(path: PathLike, *, local_only: bool = True) -> MatrixSpec:
    """Load a JSON or YAML matrix file and validate it."""
    path = Path(path)
    if not path.exists():
        raise MatrixValidationError(f"matrix file not found: {path}")
    return validate_matrix(_load_raw(path), local_only=local_only)
