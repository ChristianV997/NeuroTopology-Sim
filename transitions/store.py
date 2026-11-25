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
import io
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Sequence

from transitions.record import TransitionRecordV1

RECORD_FILENAME = "TransitionRecord.json"
TRAJECTORY_FILENAME = "TransitionTrajectory.csv"


class TransitionConflictError(FileExistsError):
    """Raised when a store write would overwrite a different existing transition."""


def _serialize_trajectory_csv(
    trajectory: Sequence[Sequence[float]],
    columns: list[str],
) -> tuple[str, list[list[str]]]:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    if columns:
        writer.writerow(columns)
    for row in trajectory:
        writer.writerow(list(row))
    csv_text = buf.getvalue()
    parsed = list(csv.reader(io.StringIO(csv_text)))
    return csv_text, parsed


def _record_semantic_payload(record: TransitionRecordV1) -> dict[str, Any]:
    payload = record.to_dict()
    payload.pop("created_at", None)
    return payload


def _atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        os.replace(tmp_path, path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise


class TransitionStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def _record_dir(self, transition_id: str) -> Path:
        if (
            not transition_id
            or "/" in transition_id
            or "\\" in transition_id
            or ".." in transition_id
        ):
            raise ValueError(f"invalid transition_id for store directory: {transition_id!r}")
        return self.root / transition_id

    def write(
        self,
        record: TransitionRecordV1,
        trajectory: Sequence[Sequence[float]] | None = None,
        trajectory_columns: list[str] | None = None,
        *,
        overwrite: bool = False,
    ) -> dict[str, Path]:
        """Write TransitionRecord.json, and TransitionTrajectory.csv if given.

        If `trajectory` is provided, `record.trajectory_artifact` and
        `record.artifact_paths['trajectory']` are set (relative to the
        record's own directory) before the JSON is written, so the on-disk
        record is self-consistent with what's next to it.

        When `overwrite=False` (default), raises `TransitionConflictError` if
        target files already exist and differ in semantic record content or
        trajectory data (or if an orphan trajectory/corrupt record sits at the
        destination). Idempotent re-writes of the exact same transition succeed.
        """
        record_dir = self._record_dir(record.transition_id)
        record_path = record_dir / RECORD_FILENAME
        trajectory_path = record_dir / TRAJECTORY_FILENAME

        candidate = TransitionRecordV1.from_dict(record.to_dict())
        csv_text: str | None = None
        incoming_csv_rows: list[list[str]] | None = None
        if trajectory is not None:
            columns = list(trajectory_columns or candidate.feature_names)
            csv_text, incoming_csv_rows = _serialize_trajectory_csv(trajectory, columns)
            candidate.trajectory_artifact = TRAJECTORY_FILENAME
            candidate.artifact_paths = dict(candidate.artifact_paths or {})
            candidate.artifact_paths["trajectory"] = TRAJECTORY_FILENAME

        written: dict[str, Path] = {}
        if trajectory is not None:
            written["trajectory"] = trajectory_path
        written["record"] = record_path

        if not overwrite and (record_path.exists() or trajectory_path.exists()):
            if not record_path.exists():
                raise TransitionConflictError(
                    f"orphan trajectory file already exists at '{trajectory_path}'; "
                    "refusing to overwrite without overwrite=True"
                )
            try:
                existing = TransitionRecordV1.from_json(record_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError, TypeError, ValueError) as exc:
                raise TransitionConflictError(
                    f"existing record at '{record_path}' could not be parsed cleanly; "
                    "refusing to overwrite"
                ) from exc

            if _record_semantic_payload(existing) != _record_semantic_payload(candidate):
                raise TransitionConflictError(
                    f"conflicting write for transition_id '{record.transition_id}': "
                    f"existing TransitionRecord at '{record_path}' differs from incoming record"
                )

            if (trajectory is not None) != trajectory_path.exists():
                raise TransitionConflictError(
                    f"conflicting write for transition_id '{record.transition_id}': "
                    "trajectory presence differs from existing store artifact"
                )

            if trajectory is not None and incoming_csv_rows is not None:
                with trajectory_path.open(newline="", encoding="utf-8") as handle:
                    existing_csv_rows = list(csv.reader(handle))
                if existing_csv_rows != incoming_csv_rows:
                    raise TransitionConflictError(
                        f"conflicting write for transition_id '{record.transition_id}': "
                        f"existing trajectory at '{trajectory_path}' differs from incoming data"
                    )

            if trajectory is not None:
                record.trajectory_artifact = TRAJECTORY_FILENAME
                record.artifact_paths = dict(record.artifact_paths or {})
                record.artifact_paths["trajectory"] = TRAJECTORY_FILENAME
            return written

        record_dir.mkdir(parents=True, exist_ok=True)
        if trajectory is not None and csv_text is not None:
            _atomic_write_text(trajectory_path, csv_text)
            record.trajectory_artifact = TRAJECTORY_FILENAME
            record.artifact_paths = dict(record.artifact_paths or {})
            record.artifact_paths["trajectory"] = TRAJECTORY_FILENAME
        elif overwrite and trajectory is None and trajectory_path.exists():
            trajectory_path.unlink()

        _atomic_write_text(record_path, record.to_json() + "\n")
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
