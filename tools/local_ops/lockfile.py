"""
Lockfile implementation for the local continuous operations runner (P25).

Prevents overlapping runs. Uses a JSON lock file at a configurable path.

stdlib only.
"""
from __future__ import annotations

import datetime
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass
class LocalOpsLock:
    owner: str
    acquired_at: str
    ttl_seconds: int
    pid: int


def _now_iso() -> str:
    return datetime.datetime.utcnow().isoformat() + "Z"


def _parse_iso(ts: str) -> datetime.datetime:
    return datetime.datetime.fromisoformat(ts.rstrip("Z"))


def is_lock_stale(lock: LocalOpsLock, ttl_seconds: int) -> bool:
    """Return True if the lock was acquired more than ttl_seconds ago."""
    try:
        acquired = _parse_iso(lock.acquired_at)
        age = (datetime.datetime.utcnow() - acquired).total_seconds()
        return age > ttl_seconds
    except Exception:
        return True


def read_lock(path: str | Path) -> Optional[LocalOpsLock]:
    """Read and return the current lock, or None if not present/invalid."""
    p = Path(path)
    if not p.exists():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return LocalOpsLock(
            owner=data.get("owner", ""),
            acquired_at=data.get("acquired_at", ""),
            ttl_seconds=data.get("ttl_seconds", 7200),
            pid=data.get("pid", 0),
        )
    except Exception:
        return None


def acquire_lock(
    path: str | Path,
    ttl_seconds: int = 7200,
    owner: str = "local_ops_runner",
) -> bool:
    """
    Try to acquire the lock at path.

    Returns True if acquired, False if a live lock exists.
    Replaces a stale lock with a warning written to stderr.
    """
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)

    existing = read_lock(p)
    if existing is not None:
        if not is_lock_stale(existing, ttl_seconds):
            return False
        import sys
        print(
            f"[local_ops.lockfile] Replacing stale lock (owner={existing.owner}, "
            f"acquired_at={existing.acquired_at})",
            file=sys.stderr,
        )

    lock_data = {
        "owner": owner,
        "acquired_at": _now_iso(),
        "ttl_seconds": ttl_seconds,
        "pid": os.getpid(),
    }
    p.write_text(json.dumps(lock_data, indent=2), encoding="utf-8")
    return True


def release_lock(path: str | Path, owner: str = "local_ops_runner") -> bool:
    """
    Release the lock at path if owned by owner.

    Returns True if released, False if not found or owned by another.
    """
    p = Path(path)
    existing = read_lock(p)
    if existing is None:
        return False
    if existing.owner != owner:
        return False
    try:
        p.unlink()
        return True
    except FileNotFoundError:
        return False
