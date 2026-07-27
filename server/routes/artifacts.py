"""Static artifact endpoints; these routes never execute scientific solvers."""
from __future__ import annotations

import json
from pathlib import Path
from fastapi import APIRouter, HTTPException
from dashboard.adapters.artifact_reader import ArtifactReader


def build_artifact_router(science_root: Path, neuro_root: Path | None = None) -> APIRouter:
    reader = ArtifactReader(science_root, neuro_root)
    router = APIRouter(prefix="/api/artifacts", tags=["artifacts"])

    def response(kind: str) -> dict:
        try: return reader.read(kind).model_dump()
        except FileNotFoundError as exc: raise HTTPException(status_code=404, detail=f"artifact unavailable: {exc.name}") from exc
        except (KeyError, ValueError, json.JSONDecodeError) as exc: raise HTTPException(status_code=500, detail=str(exc)) from exc

    @router.get("/quantum-sweeps")
    def quantum_sweeps() -> dict: return response("quantum_sweeps")

    @router.get("/topology-cohort")
    def topology_cohort() -> dict: return response("topology_cohort")

    @router.get("/multi-lattice")
    def multi_lattice() -> dict: return response("multi_lattice")

    return router
