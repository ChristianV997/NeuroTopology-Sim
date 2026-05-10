from __future__ import annotations

import subprocess
import sys


def _run_mode(mode: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "main.py", "--mode", mode],
        check=False,
        capture_output=True,
        text=True,
    )


def test_smoke_synthetic_mode_runs() -> None:
    proc = _run_mode("synthetic")
    assert proc.returncode == 0, proc.stderr


def test_smoke_db_mode_runs() -> None:
    proc = _run_mode("db")
    assert proc.returncode == 0, proc.stderr
    assert "db ok" in proc.stdout
