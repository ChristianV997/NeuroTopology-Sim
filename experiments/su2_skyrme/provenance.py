"""Provenance helpers for reproducible SU(2)/Skyrme experiment runs."""

from __future__ import annotations

import hashlib
import json
import platform
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

import numpy as np

from .schema import ExperimentConfig


def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def config_sha256(config: ExperimentConfig | Mapping[str, Any]) -> str:
    """Stable SHA-256 over the canonical experiment config payload."""
    payload = config.to_dict() if isinstance(config, ExperimentConfig) else dict(config)
    # Exclude wall-clock / host-only notes that are not part of scientific identity.
    # Keep claim_guardrail and unavailable_fields because they define interpretation.
    encoded = _canonical_json(payload).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def detect_git_revision(repo_root: str | None = None) -> dict[str, Any]:
    """Return git revision metadata; missing git is recorded, not invented."""
    try:
        rev = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=repo_root,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        dirty = subprocess.call(
            ["git", "diff", "--quiet"],
            cwd=repo_root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        branch = subprocess.check_output(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=repo_root,
            stderr=subprocess.DEVNULL,
            text=True,
        ).strip()
        return {
            "git_revision": rev,
            "git_branch": branch,
            "git_dirty": bool(dirty != 0),
            "git_status": "ok",
        }
    except (OSError, subprocess.SubprocessError):
        return {
            "git_revision": None,
            "git_branch": None,
            "git_dirty": None,
            "git_status": "unavailable",
        }


@dataclass(frozen=True)
class ProvenanceRecord:
    seed: int
    config_sha256: str
    git_revision: str | None
    git_branch: str | None
    git_dirty: bool | None
    git_status: str
    python_version: str
    numpy_version: str
    platform: str
    created_at_utc: str
    experiment_layer_version: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "seed": self.seed,
            "config_sha256": self.config_sha256,
            "git_revision": self.git_revision,
            "git_branch": self.git_branch,
            "git_dirty": self.git_dirty,
            "git_status": self.git_status,
            "python_version": self.python_version,
            "numpy_version": self.numpy_version,
            "platform": self.platform,
            "created_at_utc": self.created_at_utc,
            "experiment_layer_version": self.experiment_layer_version,
        }


def build_provenance(
    config: ExperimentConfig,
    *,
    repo_root: str | None = None,
    created_at: datetime | None = None,
    experiment_layer_version: str = "0.1.0",
) -> ProvenanceRecord:
    """Assemble seed / config-hash / git / environment provenance."""
    git_meta = detect_git_revision(repo_root)
    ts = (created_at or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()
    return ProvenanceRecord(
        seed=config.seed,
        config_sha256=config_sha256(config),
        git_revision=git_meta["git_revision"],
        git_branch=git_meta["git_branch"],
        git_dirty=git_meta["git_dirty"],
        git_status=git_meta["git_status"],
        python_version=platform.python_version(),
        numpy_version=np.__version__,
        platform=platform.platform(),
        created_at_utc=ts,
        experiment_layer_version=experiment_layer_version,
    )
