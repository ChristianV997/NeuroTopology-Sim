"""RunRecord v0.1 — minimal, general-purpose run artifact contract.

Separate from sim/run_record_schema.py (which is psi/meditation-specific).
This one is pipeline-agnostic: hypothesis runs, orchestrator runs, etc.

JSON key contract is stable — do not rename keys between versions.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

_SCHEMA_VERSION = "0.1"


@dataclass
class RunRecordV1:
    run_id: str
    run_kind: str                          # "hypothesis" | "orchestrator"
    created_at: str                        # ISO-8601 UTC
    elapsed_s: Optional[float] = None
    spec_id: Optional[str] = None
    claim_type: Optional[str] = None
    layer: Optional[str] = None
    data_mode: Optional[str] = None
    dataset_id: Optional[str] = None
    verdict: Optional[str] = None
    metrics: Dict[str, Any] = field(default_factory=dict)
    artifacts: Dict[str, str] = field(default_factory=dict)
    source: str = "unknown"
    schema_version: str = _SCHEMA_VERSION

    # ── constructors ──────────────────────────────────────────────────────────

    @classmethod
    def make(
        cls,
        run_id: str,
        run_kind: str,
        *,
        elapsed_s: Optional[float] = None,
        spec_id: Optional[str] = None,
        claim_type: Optional[str] = None,
        layer: Optional[str] = None,
        data_mode: Optional[str] = None,
        dataset_id: Optional[str] = None,
        verdict: Optional[str] = None,
        metrics: Optional[Dict[str, Any]] = None,
        artifacts: Optional[Dict[str, str]] = None,
        source: str = "unknown",
        _now: Optional[datetime] = None,
    ) -> "RunRecordV1":
        ts = (_now or datetime.now(timezone.utc)).isoformat()
        return cls(
            run_id=run_id,
            run_kind=run_kind,
            created_at=ts,
            elapsed_s=elapsed_s,
            spec_id=spec_id,
            claim_type=claim_type,
            layer=layer,
            data_mode=data_mode,
            dataset_id=dataset_id,
            verdict=verdict,
            metrics=metrics or {},
            artifacts=artifacts or {},
            source=source,
        )

    # ── serialization ─────────────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "run_kind": self.run_kind,
            "created_at": self.created_at,
            "elapsed_s": self.elapsed_s,
            "spec_id": self.spec_id,
            "claim_type": self.claim_type,
            "layer": self.layer,
            "data_mode": self.data_mode,
            "dataset_id": self.dataset_id,
            "verdict": self.verdict,
            "metrics": self.metrics,
            "artifacts": self.artifacts,
            "source": self.source,
        }

    def write_json(self, path: Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(self.to_dict(), indent=2, default=str),
            encoding="utf-8",
        )
        return path

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "RunRecordV1":
        return cls(
            run_id=d["run_id"],
            run_kind=d["run_kind"],
            created_at=d["created_at"],
            elapsed_s=d.get("elapsed_s"),
            spec_id=d.get("spec_id"),
            claim_type=d.get("claim_type"),
            layer=d.get("layer"),
            data_mode=d.get("data_mode"),
            dataset_id=d.get("dataset_id"),
            verdict=d.get("verdict"),
            metrics=d.get("metrics", {}),
            artifacts=d.get("artifacts", {}),
            source=d.get("source", "unknown"),
            schema_version=d.get("schema_version", _SCHEMA_VERSION),
        )


def write_json(record: RunRecordV1, path: Path) -> Path:
    """Module-level convenience wrapper."""
    return record.write_json(path)


def read_json(path: Path) -> RunRecordV1:
    """Load a RunRecordV1 from a JSON file."""
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    return RunRecordV1.from_dict(d)
