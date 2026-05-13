"""
Science runtime JSONL event log (P18.2).
Append-only log with tail/scan/clear utilities.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from sciencer_d.btc_icft.runtime.events import (
    ScienceEventEnvelope,
    build_event,
    envelope_to_json,
)


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def append_event(
    log_path: str,
    event_type: str,
    payload: dict,
    source: str,
    *,
    ts: Optional[str] = None,
    correlation_id: Optional[str] = None,
    sequence_id: Optional[int] = None,
) -> ScienceEventEnvelope:
    envelope = build_event(
        event_type,
        payload,
        source,
        ts=ts,
        correlation_id=correlation_id,
        sequence_id=sequence_id,
    )
    p = Path(log_path)
    _ensure_parent(p)
    with p.open("a", encoding="utf-8") as f:
        f.write(envelope_to_json(envelope) + "\n")
    return envelope


def append_envelope(log_path: str, envelope: ScienceEventEnvelope) -> None:
    p = Path(log_path)
    _ensure_parent(p)
    with p.open("a", encoding="utf-8") as f:
        f.write(envelope_to_json(envelope) + "\n")


def tail_events(log_path: str, n: int = 20) -> list[dict]:
    p = Path(log_path)
    if not p.exists():
        return []
    lines = p.read_text(encoding="utf-8").splitlines()
    result = []
    for line in lines[-n:]:
        line = line.strip()
        if not line:
            continue
        try:
            result.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return result


def scan_events(
    log_path: str,
    event_type: Optional[str] = None,
    source: Optional[str] = None,
) -> list[dict]:
    p = Path(log_path)
    if not p.exists():
        return []
    result = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event_type is not None and rec.get("type") != event_type:
            continue
        if source is not None and rec.get("source") != source:
            continue
        result.append(rec)
    return result


def clear_events(log_path: str) -> None:
    p = Path(log_path)
    if p.exists():
        p.write_text("", encoding="utf-8")
