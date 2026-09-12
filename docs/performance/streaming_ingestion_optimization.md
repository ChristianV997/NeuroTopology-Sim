# Streaming and BIDS-ingestion optimization

Engineering-runtime work on the **existing** bounded streaming skeleton and
BIDS EEG ingest path. This is not scientific evidence. No topology proof,
clinical, ontology, TOE, or consciousness claim is made. Synthetic local
fixtures only; this change does not download OpenNeuro/DANDI/AWS objects.

| Item | Path |
| --- | --- |
| Streaming skeleton | `tools/streaming/base_runner.py` |
| BIDS ingest | `data/bids_ingest.py` |
| Tests | `tests/performance/streaming_optimization/` |
| Pre-change baseline | `tests/performance/streaming_optimization/recorded_baseline.json` |

Owned-path only. Dataset acquisition policy, `tools/data_access/chunk_cache/**`,
simulation execution, Awareness Studio, solver equations, and CI workflows are
untouched.

## Baseline (unmodified `55edf5c`)

Measured on the isolated worktree **before** edits, synthetic 40 s / 8 ch EDF,
12 windows, `preprocess={l_freq: 1.0, h_freq: 40.0, reference: None}`:

| Probe | Baseline |
| --- | --- |
| `sync_s3_dataset_metadata` subprocess timeout | missing |
| `save_manifest` fsync | missing |
| `run_manifest_loop` checkpoint | non-atomic `Path.write_text` |
| Failed manifest items on resume | skipped forever (`key in processed`) |
| `list_s3_task_labels` | calls `list_s3_subjects` (full prefix listing) then slices |
| Empty S3 download batch | still starts a 12-thread pool |
| BIDS fallback discovery | `root.rglob("*")` |
| Preprocess cache | none |
| Window-cache lookup | after raw load / full-recording filter |
| `_read_raw` for 3 preprocess windows of one file | 1, then 2, then 3 |
| 12-window non-preprocess read | 0.022180 s, tracemalloc peak 343968 B |
| 12-window preprocess read | 1.897027 s, tracemalloc peak 30460560 B |
| 80-item manifest loop | 0.051194 s first pass; resume reprocessed 0 |
| 200 `save_manifest` writes | 0.026994 s |

These wall-clock figures are host-dependent engineering telemetry. They are
not scientific results and must not be promoted to evidence_class beyond
`performance_only`.

## Identified waste

1. **Repeated transfers** — empty metadata or EEG batches still constructed a
   `ThreadPoolExecutor`; complete objects were already size-reused (kept).
2. **Redundant metadata scans** — task-label discovery listed every `sub-*`
   prefix in the dataset to take the first three.
3. **Unnecessary allocations** — window cache stored `data.copy()` and copied
   again on hit; preprocess path allocated a new filtered raw per window.
4. **Cache retention** — LRU eviction and `clear_raw_cache` dropped dict
   entries without closing MNE handles.
5. **Unbounded preprocessing** — `preprocess_raw` ran on the full recording
   once per window even when the window cache already held that slice.
6. **Missing subprocess timeout** — `aws s3 sync` for dataset metadata could
   hang a run indefinitely.
7. **Non-atomic item-loop checkpoints** — `run_manifest_loop` used
   `write_text`, so a crash could truncate `manifest.json`.
8. **Resume hole** — error dicts stored under `processed` were never retried.

## Optimizations (semantics preserved)

### `tools/streaming/base_runner.py`

- `subprocess.run(..., timeout=S3_METADATA_SYNC_TIMEOUT_S)` default 300 s,
  wrapped as `TimeoutError`.
- `save_manifest`: write `.json.tmp`, `flush` + `fsync`, `os.replace`.
- Load-side recovery: if dest JSON is missing/corrupt, promote a complete
  `.tmp` sibling.
- `run_manifest_loop` checkpoints through `save_manifest`.
- Resume skips only **valid** work units; `{"error": ...}` entries retry.
- Streaming success pops the subject from `failed_subjects`.
- `list_s3_task_labels` paginates CommonPrefixes and stops at `max_subjects`.
- Empty download batches return without a thread pool.
- Atomic `.part` → `os.replace` object transfers are unchanged. Stale
  `.part*` files are still unlinked before a retry. Existing objects whose
  size matches the listing are still reused.

### `data/bids_ingest.py`

- Window cache is checked **before** opening or filtering a recording.
- Bounded preprocess cache, maxsize 1, keyed by
  `(path, mtime, size, preprocess_key)`, filled with `_read_raw` (never
  `_read_raw_cached`) so the shared preload=False raw is never mutated.
- LRU eviction and `clear_raw_cache` close MNE raws.
- `release_recording(path)` drops one recording after its final consumer.
  The streaming loop still calls `clear_raw_cache()` before deleting a
  subject directory.
- Bounds: 4 header raws, 64 window arrays, 1 preprocessed (preload=True)
  recording.
- Fallback discovery walks `sub-*/eeg` and `sub-*/ses-*/eeg` first; only if
  those directories are empty does it `rglob` by EEG extension. No
  `rglob("*")`.
- `preprocess=None` remains the default and stays byte-identical to an
  unfiltered `get_data` slice.

## Edge-effect behaviour (recorded, not changed)

`data.preprocessing.preprocess_raw` still filters the **full continuous
recording**, then `read_window_signal` slices the window. Per-window
filtering is cheaper but injects filter transients at each window edge.
Regression tests compare:

1. ingest path (full filter → slice), and
2. an explicit per-window filter of the same sample range,

and assert they are **not** interchangeable. The ingest path must keep (1).

## Measured improvements and regressions (same host, after change)

Paired files: `/opt/cursor/artifacts/streaming_opt_baseline.json` and
`streaming_opt_optimized.json`. `evidence_class=performance_only`.
RSS was not sampled (`rss_bytes: null`).

Structural (not wall-clock):

| Probe | Baseline | After |
| --- | --- | --- |
| subprocess timeout | missing | 300 s |
| manifest fsync + replace | no fsync; item loop `write_text` | fsync + `os.replace` |
| preprocess `_read_raw` for 3 windows of one file | 3 | 1 |
| failed item resume | never retried | retried |
| task-label subject listing | all prefixes | first `max_subjects` |
| empty download pool | spawned | skipped |
| fallback unbounded star glob | yes | no |
| preprocess cache occupancy after 12 windows | 0 | 1 |

Wall-clock on this 40 s / 8 ch synthetic EDF (one process, one host):

| Probe | Baseline | After | Notes |
| --- | --- | --- | --- |
| 12-window preprocess read | 1.897027 s | 1.753058 s | ~8 %; FIR setup dominates this tiny fixture |
| 12-window non-preprocess read | 0.022180 s | 0.022664 s | within noise; no speedup claimed |
| fallback discovery (400 junk files) | 0.002202 s | 0.000681 s | small absolute time |
| 200 `save_manifest` writes | 0.026994 s | 0.357468 s | **regression**: fsync durability cost |
| 80-item manifest loop | 0.051194 s | 0.265765 s | **regression**: per-item fsync |
| preprocess tracemalloc peak | 30460560 B | 30249998 B | within noise |

Do not generalize the ~8 % preprocess wall-clock drop to long recordings
without measuring those recordings. The count of full-recording filters
(12 → 1) is the portable improvement. The fsync regressions are intentional
reliability cost on checkpoint-only microbenchmarks; a real `process_fn`
dominates that overhead.

## Guardrails

- No real-dataset download.
- No live APIs in tests (boto3/AWS replaced with in-process stubs).
- No API keys in tests.
- No Q/Qabs/fdress proof framing.
- Missing metrics stay `null`; they are never coerced to `0`.
