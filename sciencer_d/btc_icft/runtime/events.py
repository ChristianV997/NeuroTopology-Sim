"""
Science runtime event model (P18.2).
Deterministic replay-safe event envelopes with sha256 replay_hash.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Optional


@dataclass
class ScienceEventEnvelope:
    event_id: str
    type: str
    ts: str
    source: str
    payload: dict
    replay_hash: str
    event_version: int = 1
    correlation_id: Optional[str] = None
    sequence_id: Optional[int] = None


def deterministic_replay_hash(event_type: str, payload: dict) -> str:
    raw = json.dumps({"type": event_type, "payload": payload}, sort_keys=True, default=str)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def build_event(
    event_type: str,
    payload: dict,
    source: str,
    *,
    ts: Optional[str] = None,
    correlation_id: Optional[str] = None,
    sequence_id: Optional[int] = None,
) -> ScienceEventEnvelope:
    from datetime import datetime, timezone

    event_id = str(uuid.uuid4())[:12]
    ts = ts or datetime.now(timezone.utc).isoformat()
    replay_hash = deterministic_replay_hash(event_type, payload)
    return ScienceEventEnvelope(
        event_id=event_id,
        type=event_type,
        ts=ts,
        source=source,
        payload=payload,
        replay_hash=replay_hash,
        event_version=1,
        correlation_id=correlation_id,
        sequence_id=sequence_id,
    )


def envelope_to_dict(envelope: ScienceEventEnvelope) -> dict:
    return asdict(envelope)


def envelope_to_json(envelope: ScienceEventEnvelope) -> str:
    return json.dumps(envelope_to_dict(envelope), default=str)
