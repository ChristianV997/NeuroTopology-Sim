"""No-network and safety guards for the offline integration harness."""
from __future__ import annotations

import contextlib
import socket
from typing import Iterator


@contextlib.contextmanager
def no_network() -> Iterator[None]:
    """Block socket construction for the duration of the harness."""

    def _blocked(*_args, **_kwargs):
        raise RuntimeError("network_disabled: batch3 offline integration forbids network access")

    originals = {
        "socket": socket.socket,
        "create_connection": socket.create_connection,
        "getaddrinfo": socket.getaddrinfo,
    }
    socket.socket = _blocked  # type: ignore[assignment]
    socket.create_connection = _blocked  # type: ignore[assignment]
    socket.getaddrinfo = _blocked  # type: ignore[assignment]
    try:
        yield
    finally:
        socket.socket = originals["socket"]  # type: ignore[assignment]
        socket.create_connection = originals["create_connection"]  # type: ignore[assignment]
        socket.getaddrinfo = originals["getaddrinfo"]  # type: ignore[assignment]
