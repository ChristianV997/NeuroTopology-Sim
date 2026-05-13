"""Tests for science runtime event model (P18.2)."""
import json

import pytest

from sciencer_d.btc_icft.runtime.events import (
    ScienceEventEnvelope,
    build_event,
    deterministic_replay_hash,
    envelope_to_dict,
    envelope_to_json,
)


def test_deterministic_replay_hash_same_inputs_same_hash():
    h1 = deterministic_replay_hash("test_event", {"key": "val"})
    h2 = deterministic_replay_hash("test_event", {"key": "val"})
    assert h1 == h2


def test_deterministic_replay_hash_different_inputs_different_hash():
    h1 = deterministic_replay_hash("test_event", {"key": "a"})
    h2 = deterministic_replay_hash("test_event", {"key": "b"})
    assert h1 != h2


def test_replay_hash_is_16_hex_chars():
    h = deterministic_replay_hash("any_type", {"x": 1})
    assert len(h) == 16
    assert all(c in "0123456789abcdef" for c in h)


def test_build_event_fields():
    env = build_event("stage_completed", {"stage": "p12", "ok": True}, source="test_runner")
    assert env.type == "stage_completed"
    assert env.source == "test_runner"
    assert env.payload == {"stage": "p12", "ok": True}
    assert len(env.event_id) == 12
    assert len(env.replay_hash) == 16
    assert env.event_version == 1


def test_build_event_replay_hash_is_deterministic():
    payload = {"stage": "p11", "ok": False}
    env1 = build_event("stage_failed", payload, source="s")
    env2 = build_event("stage_failed", payload, source="s2")
    assert env1.replay_hash == env2.replay_hash


def test_envelope_to_dict_has_all_keys():
    env = build_event("e", {"a": 1}, source="src")
    d = envelope_to_dict(env)
    for key in ("event_id", "type", "ts", "source", "payload", "replay_hash", "event_version"):
        assert key in d


def test_envelope_to_json_is_valid_json():
    env = build_event("ev", {"x": 42}, source="s")
    js = envelope_to_json(env)
    parsed = json.loads(js)
    assert parsed["type"] == "ev"
    assert parsed["payload"]["x"] == 42
