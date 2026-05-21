"""
Tests for P25 lockfile and retention modules.

Covers:
- acquire lock succeeds when absent
- active lock blocks second run
- stale lock can be replaced
- release lock works
- retention keeps last N runs
- retention never deletes outside outputs/local_ops/runs
"""
import json
import sys
import time
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.local_ops.lockfile import (
    acquire_lock,
    release_lock,
    read_lock,
    is_lock_stale,
    LocalOpsLock,
)
from tools.local_ops.retention import archive_current_run, rotate_run_outputs


# ---------------------------------------------------------------------------
# Lock tests
# ---------------------------------------------------------------------------

def test_acquire_lock_succeeds_when_absent(tmp_path):
    lock_path = tmp_path / "test_lock.json"
    ok = acquire_lock(lock_path, ttl_seconds=3600, owner="test_runner")
    assert ok is True
    assert lock_path.exists()


def test_acquire_lock_writes_owner(tmp_path):
    lock_path = tmp_path / "test_lock.json"
    acquire_lock(lock_path, ttl_seconds=3600, owner="my_runner")
    lock = read_lock(lock_path)
    assert lock is not None
    assert lock.owner == "my_runner"


def test_active_lock_blocks_second_run(tmp_path):
    lock_path = tmp_path / "test_lock.json"
    ok1 = acquire_lock(lock_path, ttl_seconds=3600, owner="runner_a")
    ok2 = acquire_lock(lock_path, ttl_seconds=3600, owner="runner_b")
    assert ok1 is True
    assert ok2 is False


def test_stale_lock_can_be_replaced(tmp_path):
    lock_path = tmp_path / "test_lock.json"
    # Write a lock with very old timestamp
    import datetime
    old_ts = (datetime.datetime.utcnow() - datetime.timedelta(hours=5)).isoformat() + "Z"
    lock_data = {"owner": "old_runner", "acquired_at": old_ts, "ttl_seconds": 60, "pid": 0}
    lock_path.write_text(json.dumps(lock_data), encoding="utf-8")

    # Lock is stale (60s TTL, 5h old) — should be replaceable
    ok = acquire_lock(lock_path, ttl_seconds=60, owner="new_runner")
    assert ok is True
    lock = read_lock(lock_path)
    assert lock.owner == "new_runner"


def test_is_lock_stale_fresh():
    import datetime
    lock = LocalOpsLock(
        owner="runner",
        acquired_at=datetime.datetime.utcnow().isoformat() + "Z",
        ttl_seconds=3600,
        pid=1,
    )
    assert is_lock_stale(lock, 3600) is False


def test_is_lock_stale_expired():
    import datetime
    old_ts = (datetime.datetime.utcnow() - datetime.timedelta(hours=3)).isoformat() + "Z"
    lock = LocalOpsLock(owner="runner", acquired_at=old_ts, ttl_seconds=60, pid=1)
    assert is_lock_stale(lock, 60) is True


def test_release_lock_works(tmp_path):
    lock_path = tmp_path / "test_lock.json"
    acquire_lock(lock_path, ttl_seconds=3600, owner="runner_x")
    released = release_lock(lock_path, owner="runner_x")
    assert released is True
    assert not lock_path.exists()


def test_release_lock_wrong_owner(tmp_path):
    lock_path = tmp_path / "test_lock.json"
    acquire_lock(lock_path, ttl_seconds=3600, owner="runner_a")
    released = release_lock(lock_path, owner="runner_b")
    assert released is False
    assert lock_path.exists()


def test_release_lock_absent(tmp_path):
    lock_path = tmp_path / "nonexistent_lock.json"
    released = release_lock(lock_path, owner="runner")
    assert released is False


def test_read_lock_returns_none_when_absent(tmp_path):
    lock_path = tmp_path / "no_lock.json"
    result = read_lock(lock_path)
    assert result is None


def test_runner_with_lock_prevents_overlap(tmp_path):
    """Integration: runner should exit with 'locked' if lock is held."""
    from tools.local_ops.runner import LocalOpsRunnerConfig, run_local_ops

    out = tmp_path / "local_ops"
    out.mkdir()
    lock_path = out / "local_ops_lock.json"

    # Pre-acquire the lock
    acquire_lock(lock_path, ttl_seconds=3600, owner="other_runner")

    config = LocalOpsRunnerConfig(
        mode="once",
        out_dir=str(out),
        local_agent_root=str(tmp_path / "agents"),
        safe_commands=["make local-agent-healthcheck"],
        no_lock=False,
    )
    result = run_local_ops(config)
    assert result.status == "locked"


# ---------------------------------------------------------------------------
# Retention tests
# ---------------------------------------------------------------------------

def _make_fake_outputs(out: Path) -> None:
    """Write dummy output files into out/."""
    out.mkdir(parents=True, exist_ok=True)
    (out / "local_ops_state.json").write_text('{"status": "succeeded"}', encoding="utf-8")
    (out / "local_ops_plan.json").write_text('{}', encoding="utf-8")
    (out / "local_ops_report.md").write_text("# Report", encoding="utf-8")


def test_archive_current_run_creates_archive(tmp_path):
    out = tmp_path / "local_ops"
    _make_fake_outputs(out)
    archive_dir = archive_current_run(out)
    assert archive_dir is not None
    assert archive_dir.exists()
    assert (archive_dir / "local_ops_state.json").exists()


def test_archive_returns_none_when_no_outputs(tmp_path):
    out = tmp_path / "local_ops"
    out.mkdir()
    result = archive_current_run(out)
    assert result is None


def test_retention_keeps_last_n(tmp_path):
    out = tmp_path / "local_ops"
    runs_dir = out / "runs"

    # Create 5 fake run dirs
    for i in range(5):
        run_dir = runs_dir / f"2024010{i}T120000Z"
        run_dir.mkdir(parents=True)
        (run_dir / "local_ops_state.json").write_text("{}", encoding="utf-8")

    deleted = rotate_run_outputs(out, keep_last=3)
    assert len(deleted) == 2
    remaining = list(runs_dir.iterdir())
    assert len(remaining) == 3


def test_retention_keeps_all_when_fewer_than_n(tmp_path):
    out = tmp_path / "local_ops"
    runs_dir = out / "runs"

    for i in range(2):
        run_dir = runs_dir / f"2024010{i}T120000Z"
        run_dir.mkdir(parents=True)

    deleted = rotate_run_outputs(out, keep_last=10)
    assert len(deleted) == 0
    remaining = list(runs_dir.iterdir())
    assert len(remaining) == 2


def test_retention_never_deletes_outside_runs(tmp_path):
    out = tmp_path / "local_ops"
    runs_dir = out / "runs"

    # Create run dirs
    for i in range(5):
        (runs_dir / f"2024010{i}T000000Z").mkdir(parents=True)

    # Create a sentinel file outside runs/
    sentinel = out / "local_ops_state.json"
    sentinel.write_text("{}", encoding="utf-8")

    rotate_run_outputs(out, keep_last=2)

    # Sentinel must still exist
    assert sentinel.exists()


def test_retention_returns_empty_when_no_runs_dir(tmp_path):
    out = tmp_path / "local_ops"
    out.mkdir()
    deleted = rotate_run_outputs(out, keep_last=5)
    assert deleted == []
