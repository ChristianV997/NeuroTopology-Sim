"""Tests verifying zero-network operation for the research runtime acceptance harness."""
from __future__ import annotations

from pathlib import Path
import socket
from typing import Any

import pytest

from tools.runner_acceptance.research_runtime.fixtures import (
    build_chunk_cache_plan_fixture,
    build_simulation_checkpoint_fixture,
    execute_atomic_write_fixture,
)
from tools.runner_acceptance.research_runtime.scenarios import (
    run_atomic_replace,
    run_portable_path_and_serialization,
    run_unicode_and_utf8_paths,
)


def test_offline_execution_enforced(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Verifies that all contract serialization and scenarios operate strictly offline."""
    def forbidden_connect(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("CRITICAL: Network socket connection attempted during offline acceptance tests.")

    monkeypatch.setattr(socket.socket, "connect", forbidden_connect)

    # 1. Test fixtures offline
    plan = build_chunk_cache_plan_fixture()
    assert plan.chunk_count > 0

    ckpt = build_simulation_checkpoint_fixture(tmp_path / "sim")
    assert ckpt.is_recoverable is True

    # 2. Test scenarios offline
    res_path = run_portable_path_and_serialization(tmp_path / "path")
    assert res_path.status.value == "PASS"

    res_atomic = run_atomic_replace(tmp_path / "atomic")
    assert res_atomic.status.value == "PASS"

    res_uni = run_unicode_and_utf8_paths(tmp_path / "uni")
    assert res_uni.status.value == "PASS"
