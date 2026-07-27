"""Allowlisted, read-only artifact schemas for the dashboard API."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel


class ArtifactEnvelope(BaseModel):
    """Stable wrapper around a static on-disk JSON artifact."""

    kind: Literal["quantum_sweeps", "topology_cohort", "multi_lattice"]
    path: str
    payload: dict[str, Any]


class ArtifactReader:
    """Resolve only known static files below configured artifact roots."""

    _FILES = {
        "quantum_sweeps": Path("open_quantum/pdb_disorder_benchmark/decoherence_sweep.json"),
        "topology_cohort": Path("topology_monitoring/cohort_sedation/cohort_topology_summary.json"),
        "multi_lattice": Path("open_quantum/multi_lattice_coupling/multi_lattice_benchmark.json"),
    }

    def __init__(self, science_root: Path, neuro_root: Path | None = None) -> None:
        self.science_root = Path(science_root).resolve()
        self.neuro_root = Path(neuro_root).resolve() if neuro_root else self.science_root.parent / "NeuroTopology-Sim"

    def _path_for(self, kind: str) -> Path:
        if kind not in self._FILES: raise KeyError(kind)
        root = self.neuro_root / "artifacts" if kind == "topology_cohort" else self.science_root / "artifacts"
        path = (root / self._FILES[kind]).resolve()
        if root.resolve() not in path.parents: raise ValueError("artifact path escapes configured root")
        return path

    def read(self, kind: Literal["quantum_sweeps", "topology_cohort", "multi_lattice"]) -> ArtifactEnvelope:
        """Read one document without importing or initialising a solver."""
        path = self._path_for(kind)
        if not path.is_file(): raise FileNotFoundError(path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict): raise ValueError("artifact root must be a JSON object")
        return ArtifactEnvelope(kind=kind, path=str(path), payload=payload)
