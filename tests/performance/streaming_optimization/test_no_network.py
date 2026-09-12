"""Guard: these tests never open a network connection or require API keys."""
from __future__ import annotations

import socket

import pytest

from tools.streaming import base_runner


def test_no_api_keys_in_optimization_tree():
    from pathlib import Path

    root = Path(__file__).resolve().parent
    needle_a = "BEGIN" + " PRIVATE KEY"
    needle_b = "aws_secret" + "_access_key"
    needle_c = "sk-ant-"
    for path in root.rglob("*"):
        if path.suffix not in {".py", ".json", ".md"}:
            continue
        if path.name == "test_no_network.py":
            continue
        text = path.read_text(encoding="utf-8")
        assert needle_a not in text
        assert needle_b not in text
        assert needle_c not in text


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
