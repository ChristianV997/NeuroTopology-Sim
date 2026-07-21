# Streaming Pipeline Profiling (OPTIMIZE pillar)

Real, measured profiling of `tools/stream_process_openneuro_dataset.py`'s
per-subject processing (`process_subject_generic`), against a real S3 subject
(ds003800), using `cProfile`/`pstats` -- not guessed bottlenecks.

## Methodology note: warm-up vs. steady state

The first profile of a cold subject showed 4.833s total, but ~3.2s of that
was one-time `mne_bids`/`mne` module import cost (traced via `cumtime` to the
`mne_bids.report` -> `mne.io.kit` -> `mne.epochs` import chain) -- not
representative of per-subject cost in a multi-subject streaming run where
imports happen once. Fixed by warming up imports on a throwaway subject
first, then profiling a fresh subject for the true steady-state number.

## Finding: recording header re-parsed once per window

Steady-state profiling (`tottime`-sorted) showed the dominant real cost was
`mne`'s EEGLAB/BrainVision file-header parse, repeated on every call site
that opened the recording: `read_window_signal`, `get_sample_rate`,
`get_channel_names`, `get_recording_duration`. Each of these called
`_read_raw` independently, and the same recording is read up to
`max_windows_per_file` times in the Level-M pass and again in the Level-T
pass -- so one recording's header was parsed roughly `2 * max_windows`
times for a 10-window subject.

## Fix: bounded per-recording read cache

`data/bids_ingest.py` -- `_read_raw_cached`, a bounded `OrderedDict` keyed by
`(path, mtime_ns, size)` so a modified file is never served stale, LRU-evicted
past `_RAW_CACHE_MAXSIZE=4`. Wired into the four non-mutating readers.
`read_window_signal`'s `preprocess != None` branch (which filters the raw
object in place) deliberately keeps using the uncached `_read_raw`, since
sharing a cached instance there would corrupt it for every other caller.
`clear_raw_cache()` lets the streaming loop release file handles
deterministically before deleting a subject's raw files.

**Byte-identical proof:** `_read_raw_cached` returns the exact same
`preload=False` MNE raw object `_read_raw` would; `get_data(picks, start,
stop)` reads deterministically from disk regardless of caching. Verified via
exact `np.array_equal` between cached and fresh reads, plus re-running the
full 3-dataset streaming oracle (ds005620/ds003969/ds003816 Level-M +
Level-T JSON output) with no diff.

**Measured:** 0.90s -> 0.16s per real ds003800 subject (~5.6x), steady state.

## Second optimization this session (pre-existing, for context)

Earlier in this session, the pairwise-correlation topology computation in
`base_real_topology.py` was found (also via profiling, not guessing) to
recompute an O(n_channels^2) correlation matrix independently per metric
that needed it; caching the matrix once per window gave a measured ~5.9x
speedup on the same real-subject benchmark, also proven byte-identical.

## Deliberately not taken: per-subject parallelism

Running subjects concurrently would trade away the disk-bounded streaming
guarantee (`run_streaming_loop` syncs one subject, processes it, deletes its
raw files, then advances) for peak-disk-usage risk on datasets sized for
exactly this bound. Out of scope without an explicit opt-in flag; not
implemented here.
