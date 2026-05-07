"""RunRecord — single canonical run artifact contract.

Covers general pipeline runs (hypothesis, orchestrator) and sim-specific runs
(psi, meditation). Sim-specific fields are optional and None by default.

JSON key contract is stable — do not rename keys between versions.

Sim utilities previously in sim/run_record_schema.py now live here:
  CONFOUNDS_CHECKLIST, build_run_id, canonicalize_paths,
  RUN_RECORD_SCHEMA, validate_run_record_dict
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

_SCHEMA_VERSION = "0.1"

CONFOUNDS_CHECKLIST: List[str] = [
    "measurement_invariance_checked",
    "multiple_comparisons_corrected",
    "effect_size_reported",
    "confidence_intervals_reported",
    "null_model_compared",
    "data_leakage_checked",
    "reproducibility_seed_fixed",
    "outlier_handling_documented",
]


@dataclass
class RunRecordV1:
    run_id: str
    run_kind: str = ""                      # "hypothesis" | "orchestrator" | "psi" | "meditation"
    created_at: str = ""                    # ISO-8601 UTC
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
    # ── Sim-specific fields (psi / meditation runs) ───────────────────────────
    mode: Optional[str] = None              # "psi" | "meditation"; mirrors run_kind for sims
    repo: Optional[str] = None
    git_commit: Optional[str] = None
    argv: Optional[List[str]] = None
    input: Optional[Dict[str, Any]] = None  # sim input params (avoids shadowing builtin in scope)
    confounds: Optional[List[str]] = None
    guardrails: Optional[Dict[str, Any]] = None
    h8_falsifiers: Optional[List[Dict[str, str]]] = None
    notes: str = ""

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
        """Serialize to the general RunRecordV1 format (schema_version='0.1')."""
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

    def to_sim_dict(self) -> Dict[str, Any]:
        """Serialize to the legacy sim format (schema_version='1') for Airtable/validation."""
        return {
            "schema_version": "1",
            "run_id": self.run_id,
            "created_at": self.created_at,
            "mode": self.mode or self.run_kind,
            "repo": self.repo or "",
            "git_commit": self.git_commit or "",
            "argv": self.argv if self.argv is not None else [],
            "input": self.input or {},
            "metrics": self.metrics,
            "artifacts": self.artifacts,
            "confounds": self.confounds if self.confounds is not None else [],
            "guardrails": self.guardrails or {},
            "h8_falsifiers": self.h8_falsifiers if self.h8_falsifiers is not None else [],
            "notes": self.notes,
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
            run_kind=d.get("run_kind") or d.get("mode", ""),
            created_at=d.get("created_at", ""),
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
            # sim-specific fields
            mode=d.get("mode"),
            repo=d.get("repo"),
            git_commit=d.get("git_commit"),
            argv=d.get("argv"),
            input=d.get("input"),
            confounds=d.get("confounds"),
            guardrails=d.get("guardrails"),
            h8_falsifiers=d.get("h8_falsifiers"),
            notes=d.get("notes", ""),
        )


# ── Sim utilities (canonical home — previously in sim/run_record_schema.py) ──

def canonicalize_paths(d: Dict[str, Any], repo_root: Optional[Path] = None) -> Dict[str, Any]:
    """Return a copy of d with Path values converted to relative POSIX strings."""
    out: Dict[str, Any] = {}
    for k, v in d.items():
        if isinstance(v, Path):
            if repo_root is not None:
                try:
                    v = v.relative_to(repo_root)
                except ValueError:
                    pass
            out[k] = v.as_posix()
        elif isinstance(v, dict):
            out[k] = canonicalize_paths(v, repo_root)
        elif isinstance(v, list):
            out[k] = [
                canonicalize_paths(i, repo_root) if isinstance(i, dict) else
                (i.as_posix() if isinstance(i, Path) else i)
                for i in v
            ]
        else:
            out[k] = v
    return out


def build_run_id(
    mode: str,
    repo: str,
    git_commit: str,
    argv: List[str],
    input_params: Dict[str, Any],
    metrics: Dict[str, float],
    repo_root: Optional[Path] = None,
) -> str:
    """Stable sha256[:16] hash — does NOT include created_at or artifact paths."""
    canonical = {
        "mode": mode,
        "repo": repo,
        "git_commit": git_commit,
        "argv": argv,
        "input": canonicalize_paths(input_params, repo_root),
        "metrics": {k: metrics[k] for k in sorted(metrics)},
    }
    blob = json.dumps(canonical, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode()).hexdigest()[:16]


RUN_RECORD_SCHEMA: Dict[str, Any] = {
    "$schema": "run_record_v1",
    "required": [
        "schema_version", "run_id", "created_at", "mode", "repo",
        "git_commit", "argv", "input", "metrics", "artifacts",
        "confounds", "guardrails", "h8_falsifiers",
    ],
    "properties": {
        "schema_version": {"type": "string", "const": "1"},
        "run_id": {"type": "string", "minLength": 16, "maxLength": 16},
        "created_at": {"type": "string"},
        "mode": {"type": "string", "enum": ["psi", "meditation"]},
        "repo": {"type": "string"},
        "git_commit": {"type": "string"},
        "argv": {"type": "array", "items": {"type": "string"}},
        "input": {"type": "object"},
        "metrics": {
            "type": "object",
            "required": ["I_mean", "I_std", "I_final", "vort_mean", "n_steps",
                         "Qz_mean", "Qabs_mean", "f_dress"],
        },
        "artifacts": {
            "type": "object",
            "required": ["md_path", "json_path"],
        },
        "confounds": {"type": "array", "items": {"type": "string"}},
        "guardrails": {"type": "object"},
        "h8_falsifiers": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["prediction", "discriminator", "status"],
            },
        },
    },
}


def validate_run_record_dict(d: Dict[str, Any]) -> List[str]:
    """Return a list of validation errors (empty = valid). Validates the sim dict format."""
    errors: List[str] = []
    for key in RUN_RECORD_SCHEMA["required"]:
        if key not in d:
            errors.append(f"Missing required field: {key}")
    if "mode" in d and d["mode"] not in ("psi", "meditation"):
        errors.append(f"Invalid mode: {d['mode']!r}")
    if "metrics" in d:
        for mkey in RUN_RECORD_SCHEMA["properties"]["metrics"]["required"]:
            if mkey not in d["metrics"]:
                errors.append(f"Missing metric: {mkey}")
    if "artifacts" in d:
        for akey in ("md_path", "json_path"):
            if akey not in d["artifacts"]:
                errors.append(f"Missing artifact path: {akey}")
    return errors


# ── Module-level convenience functions ────────────────────────────────────────

def write_json(record: RunRecordV1, path: Path) -> Path:
    """Module-level convenience wrapper."""
    return record.write_json(path)


def read_json(path: Path) -> RunRecordV1:
    """Load a RunRecordV1 from a JSON file."""
    d = json.loads(Path(path).read_text(encoding="utf-8"))
    return RunRecordV1.from_dict(d)
