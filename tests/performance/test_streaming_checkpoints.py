"""Tests for deterministic streaming checkpoints and replay audits.

Assert reproducibility / resumability contracts (not wall-clock speed).
Synthetic fixtures are performance scaffolding only — never scientific evidence.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path

import numpy as np
import pytest

from tools.streaming.bounded import bounded_stream
from tools.streaming.checkpoints import (
    CHECKPOINT_SCHEMA_VERSION,
    CheckpointConfigMismatchError,
    CheckpointCorruptionError,
    CheckpointSourceMismatchError,
    StreamInterrupt,
    aggregate_state_checksum,
    aggregate_state_from_stream,
    build_checkpoint,
    checkpointed_bounded_stream,
    compute_configuration_hash,
    compute_source_checksum,
    load_checkpoint,
    restore_aggregate,
    validate_resume,
    write_checkpoint,
)
from tools.streaming.replay import (
    aggregates_equal,
    build_replay_audit,
    make_fixture,
    run_clean,
    run_interrupted_resume,
)


def _sig(n=4000, c=4, seed=0):
    return make_fixture(n, c, seed=seed)


# --------------------------------------------------------------------------- #
# Clean / interrupted / resumed
# --------------------------------------------------------------------------- #


def test_clean_run_matches_bounded_stream(tmp_path):
    sig = _sig()
    ckpt = tmp_path / "clean.json"
    result = run_clean(sig, 256, ckpt)
    ref = bounded_stream(sig, 256)
    assert aggregates_equal(result.stream, ref)
    assert result.interrupted is False
    assert result.resumed is False
    assert ckpt.exists()
    loaded = load_checkpoint(ckpt)
    assert loaded.schema_version == CHECKPOINT_SCHEMA_VERSION
    assert loaded.current_offset == sig.shape[0]
    assert loaded.timestamp is None  # timestamp only when explicitly requested


def test_interrupted_run_writes_partial_checkpoint(tmp_path):
    sig = _sig()
    ckpt = tmp_path / "partial.json"
    result = checkpointed_bounded_stream(
        sig, 200, ckpt, interrupt_after_windows=3, write_final_checkpoint=False
    )
    assert result.interrupted is True
    assert result.stream.n_chunks == 3
    loaded = load_checkpoint(ckpt)
    assert loaded.completed_window_count == 3
    assert 0 < loaded.current_offset < sig.shape[0]


def test_resumed_run_matches_clean(tmp_path):
    sig = _sig(n=5000, c=5)
    parts = run_interrupted_resume(
        sig, 250, tmp_path / "resume.json", interrupt_after_windows=4
    )
    clean = run_clean(sig, 250, tmp_path / "clean.json")
    assert parts["interrupted"].interrupted is True
    assert parts["resumed"].resumed is True
    assert parts["resumed"].interrupted is False
    assert aggregates_equal(clean.stream, parts["resumed"].stream)
    assert clean.stream.checksum == parts["resumed"].stream.checksum


def test_deterministic_repeated_runs(tmp_path):
    sig = _sig()
    a = run_clean(sig, 128, tmp_path / "a.json")
    b = run_clean(sig, 128, tmp_path / "b.json")
    assert aggregates_equal(a.stream, b.stream)
    assert compute_source_checksum(sig) == compute_source_checksum(sig)
    ca = load_checkpoint(tmp_path / "a.json")
    cb = load_checkpoint(tmp_path / "b.json")
    assert ca.aggregate_state_checksum == cb.aggregate_state_checksum
    assert ca.configuration_hash == cb.configuration_hash
    assert ca.source_checksum == cb.source_checksum


# --------------------------------------------------------------------------- #
# Corruption / mismatch guards
# --------------------------------------------------------------------------- #


def test_corrupted_checkpoint_fails_clearly(tmp_path):
    sig = _sig()
    path = tmp_path / "bad.json"
    run_clean(sig, 256, path)
    # Truncate / corrupt JSON
    path.write_text("{not-json", encoding="utf-8")
    with pytest.raises(CheckpointCorruptionError):
        load_checkpoint(path)
    # Valid JSON but wrong aggregate checksum
    run_clean(sig, 256, path)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["aggregate_state_checksum"] = "0" * 64
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(CheckpointCorruptionError, match="aggregate_state_checksum"):
        load_checkpoint(path)
    # Empty file
    path.write_text("", encoding="utf-8")
    with pytest.raises(CheckpointCorruptionError, match="empty"):
        load_checkpoint(path)


def test_source_checksum_mismatch_refuses_resume(tmp_path):
    sig = _sig(seed=1)
    other = _sig(seed=2)
    path = tmp_path / "src.json"
    checkpointed_bounded_stream(
        sig, 256, path, interrupt_after_windows=2, write_final_checkpoint=False
    )
    with pytest.raises(CheckpointSourceMismatchError):
        checkpointed_bounded_stream(other, 256, path, resume=True)


def test_configuration_mismatch_refuses_resume(tmp_path):
    sig = _sig()
    path = tmp_path / "cfg.json"
    checkpointed_bounded_stream(
        sig, 256, path, interrupt_after_windows=2, write_final_checkpoint=False
    )
    with pytest.raises(CheckpointConfigMismatchError):
        checkpointed_bounded_stream(sig, 128, path, resume=True)
    with pytest.raises(CheckpointConfigMismatchError):
        checkpointed_bounded_stream(
            sig, 256, path, resume=True, backend="other-backend"
        )
    with pytest.raises(CheckpointConfigMismatchError):
        checkpointed_bounded_stream(sig, 256, path, resume=True, overlap=1)


# --------------------------------------------------------------------------- #
# Atomic write / JSON / memory
# --------------------------------------------------------------------------- #


def test_atomic_write_behavior(tmp_path, monkeypatch):
    sig = _sig(n=1000, c=2)
    path = tmp_path / "atomic.json"
    # First successful write
    run_clean(sig, 100, path)
    original = path.read_text(encoding="utf-8")
    assert json.loads(original)  # valid

    # Simulate failure after temp write but before replace: patch os.replace
    calls = {"n": 0}
    real_replace = os.replace

    def boom(src, dst):
        calls["n"] += 1
        if calls["n"] == 1:
            raise OSError("simulated replace failure")
        return real_replace(src, dst)

    monkeypatch.setattr(os, "replace", boom)
    cp = load_checkpoint(path)
    with pytest.raises(OSError, match="simulated"):
        write_checkpoint(path, cp)
    # Original file must remain intact (atomic failure leaves prior content).
    assert path.read_text(encoding="utf-8") == original
    # No leftover readable partial at the destination path.
    assert json.loads(path.read_text(encoding="utf-8"))


def test_finite_json_output(tmp_path):
    sig = _sig()
    path = tmp_path / "finite.json"
    run_clean(sig, 200, path, track_memory=False)
    text = path.read_text(encoding="utf-8")
    assert "NaN" not in text
    assert "Infinity" not in text
    data = json.loads(text)
    # Round-trip through allow_nan=False
    json.dumps(data, allow_nan=False)
    assert data.get("timestamp") is None


def test_timestamp_only_when_requested(tmp_path):
    sig = _sig(n=500, c=2)
    path = tmp_path / "ts.json"
    checkpointed_bounded_stream(
        sig, 100, path, include_timestamp=True, write_final_checkpoint=True
    )
    loaded = load_checkpoint(path)
    assert loaded.timestamp is not None
    assert loaded.timestamp.endswith("Z")


def test_bounded_memory_behavior(tmp_path):
    sig = _sig(n=30000, c=8)
    small = checkpointed_bounded_stream(
        sig, 256, tmp_path / "small.json", track_memory=True
    )
    large = checkpointed_bounded_stream(
        sig, 30000, tmp_path / "large.json", track_memory=True
    )
    assert isinstance(small.stream.peak_bytes, int)
    assert isinstance(large.stream.peak_bytes, int)
    # Chunked checkpointed run stays below full-array transient peak.
    assert small.stream.peak_bytes < large.stream.peak_bytes
    # History suppressed: no full trajectory retained.
    assert small.stream.history is None


def test_no_full_trajectory_materialization(tmp_path):
    sig = _sig(n=8000, c=3)
    result = run_clean(sig, 200, tmp_path / "nt.json")
    assert result.stream.history is None
    # Aggregate state size independent of n_samples.
    ckpt = load_checkpoint(tmp_path / "nt.json")
    assert len(ckpt.aggregate_state["mean"]) == 3
    assert ckpt.aggregate_state["count"] == sig.shape[0]


def test_aggregate_round_trip():
    sig = _sig()
    ref = bounded_stream(sig, 300)
    # Build aggregate via checkpointed path state helpers
    from tools.streaming.bounded import StreamAggregate

    agg = StreamAggregate.empty(sig.shape[1])
    for chunk in (sig[i:i + 300] for i in range(0, sig.shape[0], 300)):
        agg.update(chunk)
    state = aggregate_state_from_stream(agg)
    assert aggregate_state_checksum(state) == aggregate_state_checksum(state)
    restored = restore_aggregate(state)
    assert restored.count == ref.count
    assert np.array_equal(restored.mean, ref.mean)
    assert restored.checksum == ref.checksum


def test_validate_resume_helpers(tmp_path):
    sig = _sig()
    path = tmp_path / "v.json"
    run_clean(sig, 256, path)
    cp = load_checkpoint(path)
    validate_resume(cp, sig, chunk_size=256, overlap=0, backend="numpy")
    with pytest.raises(CheckpointSourceMismatchError):
        validate_resume(cp, _sig(seed=99), chunk_size=256, overlap=0, backend="numpy")
    cfg = compute_configuration_hash(
        chunk_size=256,
        overlap=0,
        dtype=str(sig.dtype),
        n_channels=sig.shape[1],
        n_samples=sig.shape[0],
        backend="numpy",
    )
    assert cfg == cp.configuration_hash


def test_build_replay_audit_equivalence(tmp_path):
    sig = _sig(n=6000, c=4)
    report = build_replay_audit(
        sig,
        200,
        tmp_path / "audit",
        interrupt_after_windows=5,
        track_memory=True,
    )
    d = report.to_dict()
    json.dumps(d, allow_nan=False)
    assert d["equivalence"]["clean_vs_resumed"] is True
    assert d["equivalence"]["clean_vs_bounded_reference"] is True
    assert d["checkpoint_schema_version"] == CHECKPOINT_SCHEMA_VERSION
    assert math.isfinite(d["equivalence"]["checksum_clean"])
    assert d["clean"]["aggregates"]["checksum"] == d["resumed"]["aggregates"]["checksum"]
    # Memory metadata present (may be int peaks).
    assert "clean_peak_bytes" in d["memory_metadata"]


def test_overlap_resume_equivalence(tmp_path):
    sig = _sig(n=5000, c=3)
    chunk, overlap = 128, 32
    parts = run_interrupted_resume(
        sig,
        chunk,
        tmp_path / "ov.json",
        interrupt_after_windows=3,
        overlap=overlap,
    )
    clean = run_clean(sig, chunk, tmp_path / "ovc.json", overlap=overlap)
    assert aggregates_equal(clean.stream, parts["resumed"].stream)


def test_stream_interrupt_is_internal():
    # Public module should expose the interrupt type for fixtures but it is not
    # raised out of checkpointed_bounded_stream.
    assert issubclass(StreamInterrupt, Exception)
