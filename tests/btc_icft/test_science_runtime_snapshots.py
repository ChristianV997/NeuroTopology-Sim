"""Tests for science runtime snapshot store (P18.2)."""
import json

import pytest

from sciencer_d.btc_icft.runtime.snapshots import (
    ScienceRuntimeSnapshotStore,
    restore_runtime_snapshot,
    write_runtime_snapshot,
)
from sciencer_d.btc_icft.runtime.state import ScienceRuntimeSnapshot


def _make_snapshot(sid: str) -> ScienceRuntimeSnapshot:
    return ScienceRuntimeSnapshot(
        snapshot_id=sid,
        created_at="2026-01-01T00:00:00+00:00",
        state={"benchmark_completed": True, "next_action": "done"},
        source_artifacts=["/some/path.json"],
    )


def test_write_and_restore_snapshot(tmp_path):
    snap = _make_snapshot("abc123")
    store = ScienceRuntimeSnapshotStore(str(tmp_path))
    p = store.write(snap)
    assert p.exists()
    restored = store.restore("abc123")
    assert restored is not None
    assert restored.snapshot_id == "abc123"
    assert restored.state["benchmark_completed"] is True


def test_restore_missing_snapshot_returns_none(tmp_path):
    store = ScienceRuntimeSnapshotStore(str(tmp_path))
    assert store.restore("does_not_exist") is None
