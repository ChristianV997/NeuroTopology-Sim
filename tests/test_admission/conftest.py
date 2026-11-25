"""Fixtures for test admission matrix unit tests."""

from __future__ import annotations

import socket
import pytest

from tools.test_admission.models import PlatformCapabilities


@pytest.fixture
def base_capabilities() -> PlatformCapabilities:
    """Provides a baseline CPU-only Linux capability profile."""
    return PlatformCapabilities(
        os_name="linux",
        is_windows=False,
        is_posix=True,
        is_linux=True,
        is_darwin=False,
        has_symlinks=True,
        has_docker=True,
        has_cuda=False,
        has_gpu=False,
        has_cloud_qpu=False,
        has_external_solver=False,
        installed_packages={
            "numpy": "1.26.0",
            "scipy": "1.12.0",
            "pytest": "8.0.0",
            "pyyaml": "6.0.1",
        },
        network_available=False,
        cpu_cores=4,
        total_memory_gb=16.0,
    )


@pytest.fixture
def block_network():
    """Guarantees no socket connections are made during offline tests."""
    orig_socket = socket.socket

    def _fail_socket(*args, **kwargs):
        raise RuntimeError("Network socket call attempted during offline test admission operation!")

    socket.socket = _fail_socket
    try:
        yield
    finally:
        socket.socket = orig_socket
