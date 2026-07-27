"""Atomic JSON telemetry artifacts for local-to-DM1 cloud execution."""
from __future__ import annotations
import json
import os
import tempfile
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import Any
import numpy as np


def _safe(value: Any) -> Any:
    if isinstance(value, (np.floating, float)): return float(value) if np.isfinite(value) else None
    if isinstance(value, np.integer): return int(value)
    if isinstance(value, Path): return str(value)
    if isinstance(value, (datetime, date, time)): return value.isoformat()
    if isinstance(value, timedelta): return value.total_seconds()
    if isinstance(value, np.ndarray): return _safe(value.tolist())
    if isinstance(value, dict): return {str(key): _safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)): return [_safe(item) for item in value]
    return value


def write_telemetry(path: str | Path, payload: dict[str, Any]) -> Path:
    """Write JSON compliant telemetry atomically; non-finite values become null."""
    destination = Path(path); destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=destination.parent, prefix=destination.stem, suffix=".tmp"); os.close(descriptor)
    try:
        Path(temporary).write_text(json.dumps(_safe(payload), indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
        os.replace(temporary, destination)
    finally: Path(temporary).unlink(missing_ok=True)
    return destination
