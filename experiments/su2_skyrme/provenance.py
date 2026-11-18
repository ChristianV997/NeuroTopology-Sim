"""Provenance capture for SU(2)/Skyrme experiment runs.

Records seed, config hash, git revision, discretization, boundary conditions,
initial condition, and model/solver settings. Does not evaluate solver math.
"""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Optional

from .schema import ExperimentConfig

_REPO_ROOT = Path(__file__).resolve().parents[2]


def canonical_json(payload: Mapping[str, Any]) -> str:
    """Deterministic JSON used for hashing and replay identity."""
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    )


def sha256_hex(payload: Mapping[str, Any] | str | bytes) -> str:
    if isinstance(payload, Mapping):
        data = canonical_json(payload).encode("utf-8")
    elif isinstance(payload, str):
        data = payload.encode("utf-8")
    else:
        data = payload
    return hashlib.sha256(data).hexdigest()


def config_hash(config: ExperimentConfig) -> str:
    """SHA-256 of the canonical config subset (excludes free-form notes)."""
    return sha256_hex(config.canonical_dict())


def git_revision(repo_root: Path | None = None) -> dict[str, Any]:
    """Best-effort git revision metadata; missing git is labeled unavailable."""
    root = repo_root or _REPO_ROOT
    record: dict[str, Any] = {
        "git_revision": None,
        "git_revision_status": "unavailable",
        "git_dirty": None,
        "epistemic_tag": "computed",
    }
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        if head.returncode != 0:
            record["git_revision_status"] = "unavailable"
            record["detail"] = (head.stderr or head.stdout or "").strip() or "git rev-parse failed"
            return record
        revision = head.stdout.strip()
        dirty_proc = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        dirty = bool(dirty_proc.stdout.strip()) if dirty_proc.returncode == 0 else None
        record.update(
            {
                "git_revision": revision,
                "git_revision_status": "available",
                "git_dirty": dirty,
            }
        )
        return record
    except (OSError, subprocess.SubprocessError) as exc:
        record["git_revision_status"] = "unavailable"
        record["detail"] = f"{type(exc).__name__}: {exc}"
        return record


def run_id_for(config: ExperimentConfig, *, config_digest: str | None = None) -> str:
    """Deterministic run id from experiment id + config hash + seed."""
    digest = config_digest or config_hash(config)
    material = {
        "experiment_id": config.experiment_id,
        "config_hash": digest,
        "seed": config.seed,
        "schema_version": config.schema_version,
    }
    return sha256_hex(material)[:16]


@dataclass(frozen=True)
class ProvenanceRecord:
    run_id: str
    seed: int
    config_hash: str
    created_at: str
    git: dict[str, Any]
    discretization: dict[str, Any]
    boundary_conditions: str
    initial_condition: dict[str, Any]
    model: dict[str, Any]
    solver: dict[str, Any]
    environment: dict[str, Any]
    claim_scope: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "seed": self.seed,
            "config_hash": self.config_hash,
            "created_at": self.created_at,
            "git": self.git,
            "discretization": self.discretization,
            "boundary_conditions": self.boundary_conditions,
            "initial_condition": self.initial_condition,
            "model": self.model,
            "solver": self.solver,
            "environment": self.environment,
            "claim_scope": self.claim_scope,
            "consciousness_implication": "none",
        }


def build_provenance(
    config: ExperimentConfig,
    *,
    created_at: Optional[str] = None,
    repo_root: Path | None = None,
) -> ProvenanceRecord:
    digest = config_hash(config)
    return ProvenanceRecord(
        run_id=run_id_for(config, config_digest=digest),
        seed=config.seed,
        config_hash=digest,
        created_at=created_at or datetime.now(timezone.utc).isoformat(),
        git=git_revision(repo_root),
        discretization={
            **config.discretization.to_dict(),
            "epistemic_tag": "assumed",
        },
        boundary_conditions=config.boundary_conditions,
        initial_condition={
            **config.initial_condition.to_dict(),
            "epistemic_tag": "assumed",
        },
        model=config.model.to_dict(),
        solver=config.solver.to_dict(),
        environment={
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "epistemic_tag": "computed",
        },
        claim_scope=config.claim_scope,
    )
