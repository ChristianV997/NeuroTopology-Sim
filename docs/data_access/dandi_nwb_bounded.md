# Bounded DANDI/NWB Ingestion Contract

Engineering contract for fail-closed, bounded DANDI/NWB access. This document
describes engineering integrity controls only. It is not empirical, clinical,
or biological evidence.

## Owned paths

- `data/dandi_nwb_ingest.py`
- `tools/stream_process_dandi000458.py`
- `tests/data_access/dandi_nwb_bounded/`
- `docs/data_access/dandi_nwb_bounded.md`

## Network policy

- Default: offline / network denied.
- Remote metadata listing (`resolve_asset_blobs`) and remote NWB open
  (`open_nwb_lazy`) require `network_permission=True`.
- CLI default is offline; callers must pass `--allow-network`.
- Tests never contact DANDI, AWS, or other live services.

## NWB / window contract

Every signal read requires an explicit `WindowRequest` with:

| Field | Rule |
|---|---|
| provenance | dataset + object identity, source kind/URI; filesystem fallbacks rejected |
| start/stop/unit | non-empty bounded range in `bytes` or `samples` |
| expected_size | explicit and positive; must match byte ranges |
| cache_budget_bytes | window must fit |
| consumer_lease | required; protects cache entry until release |
| eviction_policy | `release_after_final_consumer` or `retain_until_evicted` |
| checksum_policy | `none` or `sha256` |
| expected_checksum | optional; missing stays **unknown**, never fabricated as verified |
| network_permission / offline | remote DANDI/NWB windows need explicit permission |

Full-object and full-recording materialization are rejected
(`reject_full_recording_materialization` /
`reject_full_object_materialization`, and `read_nwb_eeg_window` refuses a
window that spans the entire recording).

## Checksums

`checksum_status(expected, observed)` returns:

- `unknown` when no expected digest is supplied
- `verified` only when both digests are present and equal
- `mismatch` when both are present and unequal

Window result JSON embeds signal-free metadata only. Incomplete reads never
emit a verified status.

## Handles and leases

- `ManagedNwbHandle` closes HDF5 and optional remfile handles together.
- `read_bounded_window` closes each source handle after the attempt.
- `WindowCache` is lease-aware; active leases block eviction; final consumers
  release entries.

## Output containment

- `require_output_root` and `resolve_under_root` keep all writes inside an
  approved root.
- The 000458 CLI requires `--output-root`; `--out` must be a child path.

## Metadata preservation

`nwb_eeg_info` preserves, when present:

- sampling rate / rate_hz
- timestamps presence and units
- data/series units
- channel identity
- montage
- source series name

Missing fields remain `null`. Labels are never invented.

## Scientific limitations

Bounded engineering access does not validate a scientific claim, clinical
effect, ontology promotion, or theory of everything. Synthetic fixtures are
`engineering_fixture_only`.

## Usage

```bash
# Offline by default — blocked without --allow-network
python tools/stream_process_dandi000458.py \
  --out outputs/btc_icft/dandi000458/stream \
  --output-root outputs

# Explicit opt-in (still bounded windows; no full-object download)
python tools/stream_process_dandi000458.py \
  --allow-network \
  --out outputs/btc_icft/dandi000458/stream \
  --output-root outputs \
  --limit 1
```

```bash
pytest tests/data_access/dandi_nwb_bounded -q
```
