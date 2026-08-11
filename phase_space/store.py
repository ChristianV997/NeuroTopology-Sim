"""Filesystem store for phase-space artifacts.

Follows `transitions.store.TransitionStore`'s conventions (one directory per
source transition, `write`/`read`/`list`, plain `pathlib`/`json`, no database
dependency) so the two layers' output trees look and behave alike.

Layout::

    <root>/<transition_id>/PhaseSpaceCoordinates.json   (list of coordinates)
    <root>/<transition_id>/PhaseSpaceTrajectory.json    (only if written)
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional, Sequence

from phase_space.coordinate import PhaseSpaceCoordinateV1
from phase_space.trajectory import PhaseSpaceTrajectoryV1

COORDINATES_FILENAME = "PhaseSpaceCoordinates.json"
TRAJECTORY_FILENAME = "PhaseSpaceTrajectory.json"


class PhaseSpaceStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def _record_dir(self, transition_id: str) -> Path:
        return self.root / transition_id

    def write(
        self,
        transition_id: str,
        coordinates: Sequence[PhaseSpaceCoordinateV1],
        trajectory: Optional[PhaseSpaceTrajectoryV1] = None,
    ) -> dict[str, Path]:
        """Write the coordinate list, and a trajectory JSON if supplied."""
        record_dir = self._record_dir(transition_id)
        record_dir.mkdir(parents=True, exist_ok=True)

        written: dict[str, Path] = {}

        coordinates_path = record_dir / COORDINATES_FILENAME
        payload = {
            "schema": "NeuroTopologySim.PhaseSpaceCoordinates.v1",
            "transition_id": transition_id,
            "coordinates": [c.to_dict() for c in coordinates],
        }
        coordinates_path.write_text(
            json.dumps(payload, indent=2, default=str) + "\n", encoding="utf-8"
        )
        written["coordinates"] = coordinates_path

        if trajectory is not None:
            written["trajectory"] = trajectory.write_json(record_dir / TRAJECTORY_FILENAME)

        return written

    def read(self, transition_id: str) -> list[PhaseSpaceCoordinateV1]:
        path = self._record_dir(transition_id) / COORDINATES_FILENAME
        if not path.exists():
            raise FileNotFoundError(path)
        payload = json.loads(path.read_text(encoding="utf-8"))
        return [
            PhaseSpaceCoordinateV1.from_dict(c) for c in payload.get("coordinates", [])
        ]

    def read_trajectory(self, transition_id: str) -> PhaseSpaceTrajectoryV1:
        path = self._record_dir(transition_id) / TRAJECTORY_FILENAME
        if not path.exists():
            raise FileNotFoundError(path)
        return PhaseSpaceTrajectoryV1.from_json(path.read_text(encoding="utf-8"))

    def list_records(self) -> list[str]:
        """Transition IDs that have written coordinates, sorted."""
        if not self.root.exists():
            return []
        return sorted(
            child.name
            for child in self.root.iterdir()
            if child.is_dir() and (child / COORDINATES_FILENAME).exists()
        )

    def read_all(self) -> dict[str, list[PhaseSpaceCoordinateV1]]:
        return {tid: self.read(tid) for tid in self.list_records()}
