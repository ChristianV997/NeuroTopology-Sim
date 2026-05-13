"""
Science runtime snapshot store (P18.2).
Write and restore named runtime snapshots.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from sciencer_d.btc_icft.runtime.state import ScienceRuntimeSnapshot


class ScienceRuntimeSnapshotStore:
    def __init__(self, store_dir: str) -> None:
        self.store_dir = Path(store_dir)

    def _snap_path(self, snapshot_id: str) -> Path:
        return self.store_dir / f"snapshot_{snapshot_id}.json"

    def write(self, snapshot: ScienceRuntimeSnapshot) -> Path:
        self.store_dir.mkdir(parents=True, exist_ok=True)
        p = self._snap_path(snapshot.snapshot_id)
        p.write_text(json.dumps(asdict(snapshot), indent=2, default=str), encoding="utf-8")
        return p

    def restore(self, snapshot_id: str) -> Optional[ScienceRuntimeSnapshot]:
        p = self._snap_path(snapshot_id)
        if not p.exists():
            return None
        data = json.loads(p.read_text(encoding="utf-8"))
        return ScienceRuntimeSnapshot(
            snapshot_id=data["snapshot_id"],
            created_at=data["created_at"],
            state=data["state"],
            source_artifacts=data.get("source_artifacts", []),
        )

    def list_snapshots(self) -> list[str]:
        if not self.store_dir.exists():
            return []
        return sorted(
            p.stem.removeprefix("snapshot_")
            for p in self.store_dir.glob("snapshot_*.json")
        )


def write_runtime_snapshot(snapshot: ScienceRuntimeSnapshot, out_dir: str) -> str:
    store = ScienceRuntimeSnapshotStore(out_dir)
    p = store.write(snapshot)
    return str(p)


def restore_runtime_snapshot(snapshot_id: str, store_dir: str) -> Optional[ScienceRuntimeSnapshot]:
    store = ScienceRuntimeSnapshotStore(store_dir)
    return store.restore(snapshot_id)
