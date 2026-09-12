"""Subprocess timeout coverage for dataset-metadata sync."""
from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from tools.streaming import base_runner


def test_metadata_sync_passes_explicit_timeout(monkeypatch, tmp_path):
    seen = {}

    def fake_run(cmd, check=True, timeout=None):
        seen["cmd"] = cmd
        seen["check"] = check
        seen["timeout"] = timeout
        return None

    monkeypatch.setattr(base_runner.subprocess, "run", fake_run)
    monkeypatch.setattr(base_runner, "_aws_command", lambda: ["aws"])
    base_runner.sync_s3_dataset_metadata("openneuro.org", "ds000000", tmp_path)
    assert seen["check"] is True
    assert seen["timeout"] == base_runner.S3_METADATA_SYNC_TIMEOUT_S
    assert seen["timeout"] is not None
    assert seen["timeout"] > 0
    assert "--no-sign-request" in seen["cmd"]


def test_metadata_sync_timeout_becomes_timeout_error(monkeypatch, tmp_path):
    def fake_run(cmd, check=True, timeout=None):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=timeout)

    monkeypatch.setattr(base_runner.subprocess, "run", fake_run)
    monkeypatch.setattr(base_runner, "_aws_command", lambda: ["aws"])
    with pytest.raises(TimeoutError, match="metadata sync exceeded"):
        base_runner.sync_s3_dataset_metadata(
            "openneuro.org", "ds000000", tmp_path, timeout_s=1.5
        )


def test_timeout_constant_is_finite_positive():
    assert base_runner.S3_METADATA_SYNC_TIMEOUT_S == 300.0
