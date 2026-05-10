"""EventEnvelope v1 — append-only event schema for the orchestrator pipeline.

event_id = sha256[:16] of canonical JSON (sorted keys, no 'event_id' key itself).
Stable: same stage + run_id + payload → same event_id across reruns.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional


def canonical_json(d: Dict[str, Any]) -> str:
    """Compact, sorted JSON string suitable for stable hashing."""
    return json.dumps(d, sort_keys=True, separators=(",", ":"), default=str)


def _event_id(stage: str, run_id: str, status: str, payload: Dict[str, Any]) -> str:
    blob = canonical_json({"run_id": run_id, "stage": stage, "status": status, "payload": payload})
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


@dataclass
class EventEnvelope:
    event_id: str
    run_id: str
    stage: str                         # e.g. "ingest_inputs", "propose_hypotheses"
    status: str                        # "start" | "ok" | "error" | "skip"
    timestamp: str                     # ISO-8601 UTC
    payload: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    duration_ms: Optional[float] = None

    # ── constructors ──────────────────────────────────────────────────────────

    @classmethod
    def make(
        cls,
        run_id: str,
        stage: str,
        status: str,
        payload: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None,
        duration_ms: Optional[float] = None,
        _now: Optional[datetime] = None,
    ) -> "EventEnvelope":
        payload = payload or {}
        ts = (_now or datetime.now(timezone.utc)).isoformat()
        eid = _event_id(stage, run_id, status, payload)
        return cls(
            event_id=eid,
            run_id=run_id,
            stage=stage,
            status=status,
            timestamp=ts,
            payload=payload,
            error=error,
            duration_ms=duration_ms,
        )

    # ── serialization ─────────────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        d = {
            "event_id": self.event_id,
            "run_id": self.run_id,
            "stage": self.stage,
            "status": self.status,
            "timestamp": self.timestamp,
            "payload": self.payload,
        }
        if self.error is not None:
            d["error"] = self.error
        if self.duration_ms is not None:
            d["duration_ms"] = self.duration_ms
        return d

    def to_jsonl(self) -> str:
        return canonical_json(self.to_dict())

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "EventEnvelope":
        return cls(
            event_id=d["event_id"],
            run_id=d["run_id"],
            stage=d["stage"],
            status=d["status"],
            timestamp=d["timestamp"],
            payload=d.get("payload", {}),
            error=d.get("error"),
            duration_ms=d.get("duration_ms"),
        )


# ── Stage registry ────────────────────────────────────────────────────────────

PIPELINE_STAGES = (
    "ingest_inputs",
    "propose_hypotheses",
    "plan_experiments",
    "execute",
    "validate",
    "digest",
    "draft_report",
    "ops_update",
)
