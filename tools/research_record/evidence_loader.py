"""Strict, format-uniform loading of untrusted local evidence files.

Supports JSON, YAML, and CSV. Every loader returns the same ``LoadResult``
shape so ``sections.py`` never has to know which format a given input
arrived in. Loading never raises: a bad file (missing, malformed,
containing a non-finite numeric literal) becomes a structured error so the
rest of the record can still compile as "partial" (rule 9: null for
missing values). No network access and no directory scanning happen here
-- only the exact path given is read (rule 13: no network access).
"""
from __future__ import annotations

import csv
import io
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from tools.research_record.checksums import sha256_file

_NON_FINITE_STRINGS = {"nan", "inf", "-inf", "+inf", "infinity", "-infinity", "+infinity"}


class NonFiniteValueError(ValueError):
    """Raised internally when an input document contains NaN/Infinity (rule 10)."""


@dataclass(frozen=True)
class LoadResult:
    path: str | None
    ok: bool
    data: Any | None
    error: str | None
    sha256: str | None
    format: str | None


def _reject_json_constant(token: str) -> float:
    raise NonFiniteValueError(f"non-finite JSON token {token!r} is not permitted in report inputs")


def _contains_non_finite_float(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, float):
        return not math.isfinite(value)
    if isinstance(value, dict):
        return any(_contains_non_finite_float(v) for v in value.values())
    if isinstance(value, list):
        return any(_contains_non_finite_float(v) for v in value)
    return False


def _load_json(text: str) -> Any:
    return json.loads(text, parse_constant=_reject_json_constant)


def _load_yaml(text: str) -> Any:
    # safe_load: no arbitrary Python object construction from untrusted YAML.
    data = yaml.safe_load(text)
    if _contains_non_finite_float(data):
        raise NonFiniteValueError("YAML document contains a non-finite float literal (e.g. .nan / .inf)")
    return data


def _load_csv(text: str, list_key: str | None) -> Any:
    if list_key is None:
        raise NonFiniteValueError("CSV is not a supported format for this section (no row-list contract)")
    rows = [dict(row) for row in csv.DictReader(io.StringIO(text))]
    for row in rows:
        for value in row.values():
            if isinstance(value, str) and value.strip().lower() in _NON_FINITE_STRINGS:
                raise NonFiniteValueError(f"non-finite literal {value!r} is not permitted in CSV report inputs")
    return {list_key: rows}


_TEXT_LOADERS = {".json": _load_json, ".yaml": _load_yaml, ".yml": _load_yaml}


def load_evidence_file(path: Path, *, list_key: str | None = None) -> LoadResult:
    """Load one evidence file, dispatching on its extension.

    ``list_key`` names the top-level list a CSV file's rows should be
    wrapped under (e.g. ``"benchmarks"``) so downstream section builders
    see the same envelope shape regardless of source format.
    """
    str_path = str(path)
    if not path.is_file():
        return LoadResult(path=str_path, ok=False, data=None, error="file_not_found", sha256=None, format=None)

    suffix = path.suffix.lower()
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        return LoadResult(path=str_path, ok=False, data=None, error=f"read_error: {exc}", sha256=None, format=suffix)

    try:
        if suffix in _TEXT_LOADERS:
            data = _TEXT_LOADERS[suffix](text)
        elif suffix == ".csv":
            data = _load_csv(text, list_key)
        else:
            return LoadResult(
                path=str_path, ok=False, data=None, error=f"unsupported_format: {suffix or '(none)'}", sha256=None, format=suffix
            )
    except NonFiniteValueError as exc:
        return LoadResult(path=str_path, ok=False, data=None, error=f"non_finite_value: {exc}", sha256=None, format=suffix)
    except json.JSONDecodeError as exc:
        return LoadResult(path=str_path, ok=False, data=None, error=f"invalid_json: {exc}", sha256=None, format=suffix)
    except yaml.YAMLError as exc:
        return LoadResult(path=str_path, ok=False, data=None, error=f"invalid_yaml: {exc}", sha256=None, format=suffix)
    except csv.Error as exc:
        return LoadResult(path=str_path, ok=False, data=None, error=f"invalid_csv: {exc}", sha256=None, format=suffix)

    return LoadResult(path=str_path, ok=True, data=data, error=None, sha256=sha256_file(path), format=suffix)
