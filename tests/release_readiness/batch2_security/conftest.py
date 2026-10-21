"""Shared fixtures for Batch 2 security tests (no network, no neurodata)."""
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _block_external_services(monkeypatch):
    """Fail closed if a test accidentally opens a socket."""
    import socket

    def _blocked(*_a, **_k):
        raise AssertionError("batch2 security tests forbid network sockets")

    monkeypatch.setattr(socket, "socket", _blocked)
    monkeypatch.setattr(socket, "create_connection", _blocked)
