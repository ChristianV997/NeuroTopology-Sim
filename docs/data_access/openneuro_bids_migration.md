# OpenNeuro/BIDS bounded-caller migration

This document records the migration of the highest-risk legacy callers.  It
is an engineering access contract; checksums, manifests, and successful
transfers are not scientific evidence.

## Scope and findings

Before this migration:

| Caller | Legacy behavior | Risk |
| --- | --- | --- |
| `tools/fetch_ds000245.py` | Listed an OpenNeuro S3 prefix and concurrently downloaded every matching full NIfTI object. | Unbounded dataset/object transfer and disk growth. |
| `scripts/eeg_topology_ds005620.py` | Invoked `openneuro download` when `--download` was supplied. | Full-dataset materialization outside the bounded cache. |
| `scripts/fetch_real_datasets.py` | Downloaded a PDB object and a three-file EEG triplet directly. | Direct transfer, no manifest-first admission, and no cache budget. |

After this migration, those paths either perform metadata-only planning or
use the canonical `tools.data_access.chunk_cache.BoundedChunkCache` for one
declared byte range.  A legacy full-object/full-dataset request is rejected
with an actionable error.

## Required request contract

Every data-bearing request must declare:

- the BIDS dataset ID and normalized relative BIDS path;
- source URI, expected object size, and a 64-character source SHA-256;
- an inclusive `start_byte`/`end_byte` range smaller than the source object and
  within the 64 MiB caller bound;
- a cache root, output root, and maximum cache byte budget;
- `allow_network`, which defaults to `false`;
- a final consumer and eviction metadata with
  `delete_after_final_consumer: true`.

The cache's optional `chunk_sha256` can verify the returned range.  A full
source checksum is retained as provenance and is never replaced by a guessed
digest.  A checksum that is absent or malformed is a rejected request.

`BoundedChunkCache` registers metadata before a transfer, performs disk and
budget preflight, stages bytes through atomic partial files, retries only a
bounded number of times, and preserves manifest records through eviction.
The callers do not use direct `boto3`, AWS CLI, `urllib` body reads, or the
OpenNeuro CLI downloader.

## Metadata versus bytes

`openneuro_file_inventory(..., allow_network=True)` is an explicit metadata
operation only.  The default is offline and fails before opening a socket.
`ensure_dataset` can read a matching local `openneuro_inventory.json`; it never
turns an inventory into a download.  To plan data windows,
`plan_bounded_windows` requires a manifest row with size, source URI, and
source SHA-256 for every requested BIDS path.  It never infers identity from a
filename or creates a checksum.

The EEG topology analysis remains a local-reader operation.  It analyzes an
already available local recording window and does not materialize a remote
recording.  A missing local manifest, unavailable provenance, or offline
metadata request is an explicit blocked access state, not an empty empirical
result.

## Lifecycle and eviction

The cache uses the repository's manifest, atomic partial-file staging, and
lease-aware LRU eviction.  The `consume` callback in the ds000245 adapter is
the explicit boundary for a final consumer.  After it returns, the caller
asks the canonical cache to evict the consumed range and reports whether the
target was deleted or remains pending behind another lease/LRU item.  It does
not silently unlink files or claim cleanup when the cache did not confirm it.

Interrupted transfers remain partial and are not marked complete.  The
canonical `cleanup_stale_partials` operation can remove abandoned staging
files within the configured cache root.  Manifest history is retained for
auditability.

## Offline and synthetic-data rules

Network access is disabled by default and no tests contact OpenNeuro, AWS,
PDB, or any other external service.  Tests use the canonical in-memory mock
transfer adapter and local byte fixtures.  Synthetic bytes validate range,
checksum, atomicity, and cleanup behavior only; they are not empirical data
and cannot support a scientific claim.

## Compatibility and remaining migration posture

The old function names remain only where a caller needs an actionable,
fail-closed compatibility seam.  `download=True` and the old no-argument
fetch behavior no longer perform work.  Existing unrelated legacy callers,
including streaming and other dataset acquisition paths, are intentionally
outside this migration and remain for their designated migration lane.

This migration does not change topology, Bayesian, simulation, or scientific
model semantics.  A bounded transfer or a successful local analysis is not a
scientific PASS and does not establish data validity, causality, biology, or
mechanism.
