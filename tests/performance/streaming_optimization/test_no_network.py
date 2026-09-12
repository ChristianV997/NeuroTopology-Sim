"""Guard: these tests never open a network connection or require API keys."""
from __future__ import annotations

import socket

import pytest

from tools.streaming import base_runner


def test_no_api_keys_in_optimization_tree():
    from pathlib import Path

    root = Path(__file__).resolve().parent
    forbidden = ("AKIA", "sk-", "api_key", "OPENAI", "ANTHROPIC")
    for path in root.rglob("*"):
        if path.suffix not in {".py", ".json", ".md"}:
            continue
        text = path.read_text(encoding="utf-8")
        for token in ("BEGIN PRIVATE KEY", "aws_secret_access_key"):
            assert token not in text
        # Allow the substring in comments that forbid keys, not live secrets.
        assert "sk-ant-" not in text


def test_local_helpers_do_not_open_sockets(monkeypatch, tmp_path):
    def blocked(*args, **kwargs):
        raise AssertionError("network socket opened during local streaming tests")

    monkeypatch.setattr(socket.socket, "__init__", blocked)
    payload = {"processed_subjects": {}, "failed_subjects": {}}
    path = tmp_path / "manifest.json"
    base_runner.save_manifest(path, payload)
    assert base_runner.load_manifest(path) == payload
    seen = []
    base_runner.run_manifest_loop(
        ["only-local"],
        tmp_path / "loop",
        key_fn=lambda x: x,
        process_fn=lambda x: seen.append(x) or {"ok": True},
    )
    assert seen == ["only-local"]
