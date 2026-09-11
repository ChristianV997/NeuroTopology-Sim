"""Local-only / no-network / bounded-resource guards for the smoke harness."""
from __future__ import annotations

import resource
import socket
from contextlib import contextmanager
from typing import Iterator, List


class NetworkGuardError(RuntimeError):
    """Raised when a smoke run attempts network I/O."""


@contextmanager
def no_network() -> Iterator[None]:
    """Block outbound socket creation during smoke execution."""

    def _blocked(*_args, **_kwargs):
        raise NetworkGuardError("research-cycle smoke harness forbids network access")

    original_socket = socket.socket
    original_create = socket.create_connection
    socket.socket = _blocked  # type: ignore[assignment]
    socket.create_connection = _blocked  # type: ignore[assignment]
    try:
        yield
    finally:
        socket.socket = original_socket  # type: ignore[assignment]
        socket.create_connection = original_create  # type: ignore[assignment]


def bounded_resources_ok(*, max_rss_mb: float = 1024.0) -> tuple[bool, List[str]]:
    """Best-effort advisory resource bound (does not fail the suite alone)."""
    notes: List[str] = []
    try:
        usage = resource.getrusage(resource.RUSAGE_SELF)
        # ru_maxrss is kilobytes on Linux.
        rss_mb = float(usage.ru_maxrss) / 1024.0
        notes.append(f"rss_mb={rss_mb:.2f}")
        if rss_mb > max_rss_mb:
            notes.append(f"rss_exceeded_advisory_limit:{max_rss_mb}")
            return False, notes
        return True, notes
    except Exception as exc:  # pragma: no cover
        notes.append(f"resource_probe_unavailable:{exc}")
        return True, notes
