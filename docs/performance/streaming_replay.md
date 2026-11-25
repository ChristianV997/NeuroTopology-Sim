# Streaming Checkpoints & Replay Audits

Additive checkpoint / resume layer for bounded stream processing. Enables
long-run reproducibility and resumability **without materializing full
trajectories**.

| Artifact | Path |
| --- | --- |
| Checkpoint records | `tools/streaming/checkpoints.py` |
| Replay comparison | `tools/streaming/replay.py` |
| Audit CLI | `scripts/streaming_replay_audit.py` |
| Tests | `tests/performance/test_streaming_checkpoints.py` |

This layer sits on top of PR #211 (`bounded_stream`), PR #215 (memory
telemetry), and PR #224 (adaptive planning). It **does not modify**
`bounded.py`, `memory_telemetry.py`, `adaptive.py`, or `adaptive_types.py`.

> **Scientific-integrity note.** Fixtures and audit outputs are reproducibility
> scaffolding only — never scientific evidence. No topology, Bayes-factor, or
> clinical claims are involved.

## Checkpoint schema (`1.0`)

Each checkpoint is a single JSON object with:

| Field | Meaning |
| --- | --- |
| `schema_version` | `"1.0"` |
| `source_checksum` | SHA-256 of source array bytes + shape + dtype |
| `n_channels` / `n_samples` | Channel / sample dimensions |
| `dtype` | NumPy dtype string |
| `chunk_size` | Samples per window |
| `overlap` | Overlap between successive windows (`0` matches `bounded_stream`) |
| `current_offset` | Next sample index to process |
| `completed_window_count` | Windows folded into the aggregate |
| `aggregate_state` | Finite JSON-safe Chan mean/variance state |
| `aggregate_state_checksum` | SHA-256 of canonical `aggregate_state` |
| `backend` | Backend label (e.g. `numpy`) |
| `configuration_hash` | SHA-256 of resume-critical settings |
| `provenance_label` | Caller label |
| `timestamp` | ISO-8601 UTC **only when explicitly requested** |

Records are JSON-safe and finite (`allow_nan=False`). Empty aggregates serialize
`minimum`/`maximum` as `null` rather than `Infinity`.

## Semantics

### Atomic writes

`write_checkpoint` writes to a sibling temp file, `fsync`s, then `os.replace`s
onto the destination. A crash mid-write cannot leave a partially valid
destination file; readers either see the previous checkpoint or the new one.

### Resume equivalence

For fixed `chunk_size`, `overlap`, `backend`, and source data:

1. A clean `checkpointed_bounded_stream` run, and
2. An interrupted run followed by `resume=True`,

produce **identical** aggregates and checksums. When `overlap=0`, the clean
path also matches unmodified `bounded_stream` bit-for-bit.

### Guards (fail clearly, never silent)

| Condition | Error |
| --- | --- |
| Truncated / invalid JSON / missing fields / aggregate checksum mismatch | `CheckpointCorruptionError` |
| Different source bytes or dimensions | `CheckpointSourceMismatchError` |
| Different chunk/overlap/dtype/backend/`check_finite` | `CheckpointConfigMismatchError` |

Configuration and source checks run **before** any further aggregation on resume.

### No full trajectory

Only fixed-size aggregate state (`count`, `mean`, `M2`, min, max, checksum) is
stored. `store_history` defaults to `False`. Source checksumming hashes the
input in blocks without retaining transformed windows.

## API sketch

```python
from tools.streaming.checkpoints import checkpointed_bounded_stream, load_checkpoint
from tools.streaming.replay import build_replay_audit, make_fixture

sig = make_fixture(8000, 6, seed=0)

# Clean run
checkpointed_bounded_stream(sig, 256, "run.ckpt.json")

# Interrupt fixture then resume
checkpointed_bounded_stream(
    sig, 256, "run.ckpt.json", interrupt_after_windows=5, write_final_checkpoint=False
)
checkpointed_bounded_stream(sig, 256, "run.ckpt.json", resume=True)

# Audit: clean vs interrupted/resumed (+ bounded reference when overlap=0)
report = build_replay_audit(sig, 256, "artifacts/audit", interrupt_after_windows=5)
assert report.to_dict()["equivalence"]["clean_vs_resumed"]
```

## Replay audit CLI

```bash
PYTHONPATH=. python scripts/streaming_replay_audit.py \
  --samples 8000 --channels 6 --chunk-size 256 --interrupt-after 5 \
  --work-dir artifacts/streaming_replay_audit --json
```

Audit output compares:

- clean run aggregates + checksum
- interrupted (partial) aggregates
- resumed aggregates + final aggregate-state checksum
- optional `bounded_stream` reference (overlap=0)
- memory metadata (`tracemalloc` peaks when enabled)

Exit code `0` when `clean_vs_resumed` is true; `1` otherwise.

## Working with adaptive planning

Callers may size `chunk_size` with `tools.streaming.adaptive.plan_chunk_size` /
`adaptive_bounded_stream`, then pass that size into `checkpointed_bounded_stream`.
The adaptive modules are imported by callers only; this checkpoint layer does
not wrap or modify them.

## Memory limitations

- Checkpoint size is O(channels), not O(samples). Transient peak during a run
  still scales with `chunk_size` (same model as `bounded_stream`).
- `track_memory=True` reports Python-domain `tracemalloc` peaks only — not
  process RSS. Cross-check RSS with `tools.streaming.memory_telemetry` (PR #215).
- Process RSS includes interpreter + NumPy/SciPy/etc. and allocator retention;
  it is not resettable on POSIX. Do not treat checkpoint resumability as an RSS
  guarantee.
- Wall-clock and absolute peaks are hardware/BLAS/load dependent.

## Tests

```bash
PYTHONPATH=. python -m pytest tests/performance/test_streaming_checkpoints.py -q
```

Coverage includes: clean run, interrupted run, resumed run, corrupted
checkpoint, source checksum mismatch, configuration mismatch, deterministic
repeated runs, atomic write behavior, finite JSON output, and bounded-memory
behavior.
