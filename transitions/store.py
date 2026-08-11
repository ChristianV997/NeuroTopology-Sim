"""Lightweight filesystem store for transition artifacts.

One directory per transition_id, following the
`sciencer_d.btc_icft.runtime.snapshots.ScienceRuntimeSnapshotStore` naming
convention (write / list / read) already established for similar
single-directory-per-artifact JSON stores in this repo. No database
dependency; deterministic and easy to test with `tmp_path`.

Layout::

    <root>/<transition_id>/TransitionRecord.json
    <root>/<transition_id>/TransitionTrajectory.csv   (only if a trajectory was written)
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Sequence

from transitions.record import TransitionRecordV1

RECORD_FILENAME = "TransitionRecord.json"
TRAJECTORY_FILENAME = "TransitionTrajectory.csv"


class TransitionStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def _record_dir(self, transition_id: str) -> Path:
        return self.root / transition_id

    def write(
        self,
        record: TransitionRecordV1,
        trajectory: Sequence[Sequence[float]] | None = None,
        trajectory_columns: list[str] | None = None,
    ) -> dict[str, Path]:
        """Write TransitionRecord.json, and TransitionTrajectory.csv if given.

        If `trajectory` is provided, `record.trajectory_artifact` and
        `record.artifact_paths['trajectory']` are set (relative to the
        record's own directory) before the JSON is written, so the on-disk
        record is self-consistent with what's next to it.
        """
        record_dir = self._record_dir(record.transition_id)
        record_dir.mkdir(parents=True, exist_ok=True)

        written: dict[str, Path] = {}

        if trajectory is not None:
            columns = trajectory_columns or record.feature_names
            trajectory_path = record_dir / TRAJECTORY_FILENAME
            with trajectory_path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.writer(handle)
                if columns:
                    writer.writerow(columns)
                for row in trajectory:
                    writer.writerow(list(row))
            record.trajectory_artifact = TRAJECTORY_FILENAME
            record.artifact_paths = dict(record.artifact_paths or {})
            record.artifact_paths["trajectory"] = TRAJECTORY_FILENAME
            written["trajectory"] = trajectory_path

        record_path = record_dir / RECORD_FILENAME
        record.write_json(record_path)
        written["record"] = record_path

        return written

    def read(self, transition_id: str) -> TransitionRecordV1:
        record_path = self._record_dir(transition_id) / RECORD_FILENAME
        if not record_path.exists():
            raise FileNotFoundError(record_path)
        return TransitionRecordV1.from_json(record_path.read_text(encoding="utf-8"))

    def read_trajectory(self, transition_id: str) -> tuple[list[str], list[list[float]]]:
        """Return (column_names, rows) for a stored trajectory CSV."""
        trajectory_path = self._record_dir(transition_id) / TRAJECTORY_FILENAME
        if not trajectory_path.exists():
            raise FileNotFoundError(trajectory_path)
        with trajectory_path.open(newline="", encoding="utf-8") as handle:
            reader = csv.reader(handle)
            rows = list(reader)
        if not rows:
            return [], []
        header, body = rows[0], rows[1:]
        return header, [[float(cell) for cell in row] for row in body]

    def list_records(self) -> list[str]:
        """List transition_ids that have a written TransitionRecord.json, sorted."""
        if not self.root.exists():
            return []
        return sorted(
            child.name
            for child in self.root.iterdir()
            if child.is_dir() and (child / RECORD_FILENAME).exists()
        )

    def read_all(self) -> list[TransitionRecordV1]:
        return [self.read(transition_id) for transition_id in self.list_records()]
