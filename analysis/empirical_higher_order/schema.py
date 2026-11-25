"""Versioned local input and output contracts for empirical execution."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Mapping

SCHEMA_VERSION = "NeuroTopologySim.EmpiricalHigherOrderManifest.v1"
EVIDENCE_CLASS = "empirical_forecasting_runner"
FEATURE_FAMILIES = (
    "psd",
    "pairwise_fc",
    "triadic_fc",
    "directed_hypergraph",
    "higher_order_spectra",
)


class ManifestError(ValueError):
    """Raised for a malformed or unsafe local manifest."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_safe(value: Any, path: str = "$") -> Any:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ManifestError(f"{path} contains a non-finite number")
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [_json_safe(item, f"{path}[{i}]") for i, item in enumerate(value)]
    if isinstance(value, Mapping):
        return {str(k): _json_safe(v, f"{path}.{k}") for k, v in value.items()}
    raise ManifestError(f"{path} is not JSON serializable")


def finite_json(value: Mapping[str, Any]) -> str:
    return json.dumps(_json_safe(value), sort_keys=True, indent=2, allow_nan=False) + "\n"


def local_path(value: Any, base: Path, *, required: bool = True) -> Path | None:
    if value is None or str(value).strip() == "":
        if required:
            raise ManifestError("local path is required")
        return None
    raw = str(value).strip()
    if "://" in raw or raw.startswith(("http:", "https:", "s3:", "gs:")):
        raise ManifestError("network and cloud URLs are not accepted; provide an explicit local path")
    path = Path(raw)
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def load_manifest(path: str | Path) -> dict[str, Any]:
    source = Path(path).resolve()
    if not source.is_file():
        raise ManifestError(f"manifest does not exist: {source}")
    try:
        data = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ManifestError(f"manifest is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise ManifestError("manifest root must be an object")
    data["_manifest_path"] = str(source)
    data["_base_dir"] = str(source.parent)
    return data

