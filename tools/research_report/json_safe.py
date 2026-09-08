"""Strict, side-effect-free JSON loading for untrusted evidence artifacts.

Every input to the report compiler is treated as untrusted (it may come from
another agent's tool, a partially-written CI artifact, or hand-edited
fixture). Loading must never raise out of the compiler: a bad file becomes a
structured ``LoadResult`` error so the rest of the report can still compile
(see "Support partial reports" in docs/research/report_contract.md).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class NonFiniteValueError(ValueError):
    """Raised internally when an input document contains NaN/Infinity."""


def _reject_constant(token: str) -> float:
    raise NonFiniteValueError(f"non-finite JSON token {token!r} is not permitted in report inputs")


@dataclass(frozen=True)
class LoadResult:
    path: str | None
    ok: bool
    data: Any | None
    error: str | None
    sha256: str | None


def load_json_strict(path: Path) -> LoadResult:
    """Load a JSON document, rejecting NaN/Infinity and reporting errors structurally.

    Never raises: any failure (missing file, malformed JSON, non-finite
    numeric literal) is captured in the returned ``LoadResult``.
    """
    from tools.research_report.checksums import sha256_file

    str_path = str(path)
    if not path.is_file():
        return LoadResult(path=str_path, ok=False, data=None, error="file_not_found", sha256=None)

    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return LoadResult(path=str_path, ok=False, data=None, error=f"read_error: {exc}", sha256=None)

    try:
        data = json.loads(text, parse_constant=_reject_constant)
    except NonFiniteValueError as exc:
        return LoadResult(path=str_path, ok=False, data=None, error=f"non_finite_value: {exc}", sha256=None)
    except json.JSONDecodeError as exc:
        return LoadResult(path=str_path, ok=False, data=None, error=f"invalid_json: {exc}", sha256=None)

    return LoadResult(path=str_path, ok=True, data=data, error=None, sha256=sha256_file(path))
