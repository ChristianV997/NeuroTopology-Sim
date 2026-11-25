# P0 legacy acquisition migration

## Scope and base

This migration starts from `origin/main` at
`ad1d480828b23bf9daf7272d8747302dcca138b7`.  It covers only the owned
workflow, BIDS ingestion, DANDI streaming caller, and the requested tests and
documentation.  `orchestrator/job_router.py` was not present at that base, so
no production router change is claimed.

## Findings removed

The previous `fmri_tda_ds000245.yml` workflow contained four unsafe acquisition
operations:

| Finding | Previous location | Disposition |
| --- | --- | --- |
| recursive OpenNeuro object transfer | workflow line 86 | removed; workflow is now metadata-only |
| dataset-level object copy for `participants.tsv` | workflow line 89 | removed; metadata inventory is bounded and not materialized |
| dataset-level object copy for `dataset_description.json` | workflow line 90 | removed; metadata inventory is bounded and not materialized |
| unbounded atlas URL transfer | workflow line 97 | removed; atlas input is not accepted by this preflight |

The workflow now has an explicit `allow_metadata_network` boolean that defaults
to `false`.  Offline runs emit a `BLOCKED_OFFLINE` JSON record.  An explicitly
enabled run performs only a bounded `list-objects-v2` metadata inventory with a
120-second timeout and a 1,000-object limit.  It never runs the fMRI pipeline,
materializes BOLD or atlas bytes, or produces an empirical result.

## DANDI contract

The DANDI caller already used `data.dandi_nwb_ingest`'s bounded lazy reader;
this migration makes that contract explicit at the caller boundary:

- network permission is opt-in and omitted permission fails before metadata access;
- a DANDI assets-manifest record is required before opening an NWB object;
- dataset/version/path identity and positive manifest content size are recorded;
- `checksum_status=unknown` is explicit because this manifest path does not
  provide a verified SHA-256 digest;
- the maximum lazy window is bounded by `MAX_WINDOW_BYTES` and the same value
  is recorded as the cache budget;
- output files are resolved under the explicit output root;
- metadata is written atomically to `access_manifest.json` before lazy reads;
- NWB reads are bounded windows and the object is closed after processing.

The streamer now performs the window extraction locally in the owned caller so
the actual `open_nwb_lazy` call receives explicit permission.  It does not
copy a complete NWB object or label an unknown checksum as verified.

## BIDS provenance

The standard `mne-bids` path remains labelled `real_bids`.  The non-standard
filesystem fallback is now labelled `local_bids_unvalidated`, and its inventory
is `unvalidated_or_mixed`.  This prevents a fallback scan from being promoted to
validated empirical provenance merely because an EEG-looking filename exists.
The BIDS module is local-only and does not perform remote retrieval.

## Residual findings and separate ownership

The current static scanner reports eight findings in `data/bids_ingest.py`:

- three `MISSING_CACHE_BOUND` findings;
- three `MISSING_CHECKSUM` findings;
- two `MISSING_EVICTION` findings.

They arise from the scanner's conservative naming heuristic on local cache
helpers (`_preprocess_cache_key`, `_read_raw_cached`, and
`_read_preprocessed_raw`); there are no remote calls, subprocess transfers, or
object readers in those functions.  They are not suppressed or reclassified by
this migration.  Correcting that heuristic belongs to the policy-enforcement
owner and is outside this branch.

The repository-wide scan also contains findings in production paths outside
this task, including existing OpenNeuro streamers, the legacy S3 fetchers, and
shared streaming code.  Those paths remain residual violations requiring their
respective owners.  This branch therefore does **not** claim repository-wide
policy compliance.

## Test policy

Tests use `MockTransferAdapter`, local records, and temporary directories only.
They exercise offline defaults, explicit permission, manifest-first ordering,
bounded ranges, missing checksums, cache release, path containment, full-object
rejection, deterministic JSON, and the workflow's absence of legacy transfer
commands.  No real dataset or external service is contacted.

The data-access policy remains engineering evidence only.  A metadata inventory,
a bounded transfer, or a lazy signal window does not establish biological
causation, consciousness, or any other scientific claim by itself.
