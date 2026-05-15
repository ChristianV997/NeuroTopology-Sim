"""
Append-only JSONL event log for local agent loop.

stdlib only.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any


def event_hash(event: dict) -> str:
    """Return sha256[:16] hex of the stable JSON representation."""
    stable = json.dumps(event, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(stable.encode()).hexdigest()[:16]


def append_event(log_path: str | Path, event: dict) -> None:
    """Append a single event dict as a JSONL line."""
    p = Path(log_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(event, separators=(",", ":")) + "\n")


def read_events(log_path: str | Path) -> list:
    """Return all events from the JSONL log. Returns [] if file missing."""
    p = Path(log_path)
    if not p.exists():
        return []
    events = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                events.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return events
