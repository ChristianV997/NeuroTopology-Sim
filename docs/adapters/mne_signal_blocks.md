# In-memory MNE → canonical signal-block boundary

**Schema:** `MNE.InMemorySignalBlock.v1`
**Package:** `adapters/mne_signal_blocks/`
**Lane:** Batch 2 / Cursor Agent A (exclusive)

## Purpose

Represent an MNE `Raw`/`Epochs` object, or an equivalent in-memory fixture mapping, as a canonical signal block **without silent scientific or metadata transformations**.

This is an engineering conformance boundary only. Successful conversion is **not** evidence of scientific validity, clinical utility, or topology proof.

## Non-goals

- Not a BIDS reader
- Not an OpenNeuro / dataset downloader
- Not a feature extractor or empirical-analysis pipeline
- Does not duplicate `shared/interop/adapters/mne_adapter.py` (FIF file streaming) or `sciencer_d/btc_icft/io/mne_signal_block_conversion.py` (JSON/CSV window conversion)

## Public API

| Entry point | Role |
|---|---|
| `convert_in_memory_block(payload)` | Fixture / plain mapping path (no MNE required) |
| `convert_from_mne_object(obj)` | Optional Raw/Epochs bridge; errors with `MNE_UNAVAILABLE` if MNE is absent |
| `validate_block(metadata)` | Re-validate serialized metadata |

## Preserved fields (when declared)

Channel order and names, channel types, units, sample rate, time origin, block sample bounds, bad channels, events/annotations, reference, montage name/coordinates, preprocessing history, source id/hash, and data shape `(n_channels, n_samples)`.

## Fail-closed / no-inference rules

- Missing or ambiguous units, channel types, reference, or montage → explicit unknown values and status `inconclusive` (never invent `V`, average-ref, or standard montages). Literal `unknown`/`unspecified` tokens are not treated as verified declarations.
- Channel names and unit labels must be non-empty strings. Sampling rate must be a finite positive numeric value; booleans and numeric-looking strings are not coerced into rates. Missing/invalid values remain unknown and cannot produce `converted`.
- A montage name, or a complete finite coordinate row for every channel, is required. Null coordinate rows do not stand in for a montage when no montage name is declared.
- Hard failures (`rejected`): empty blocks, shape mismatches, non-finite values, channel-order mismatches, unsupported channel types, event sample out of range.
- Never silently resample, filter, rereference, interpolate, reorder, or drop channels.
- Input arrays and metadata mappings are not mutated; data is copied by default.
- `scientific_pass` is always `false`.
- Declared sample bounds, when present, must be non-negative integer half-open
  bounds whose span matches the signal sample dimension.
- `validate_block` checks serialized schema/status and required reference and
  montage metadata; it never upgrades a producer's more restrictive status.
  It requires two-dimensional shape and channel/sample counts to agree with
  included signal data, or with declared shape when data is omitted. If signal
  data is omitted from serialized metadata, finite sample values cannot be
  revalidated.

## Optional MNE bridge

When MNE is installed, `convert_from_mne_object` reads declared `mne.Info` fields only:

- `ch_names`, `chs`, `sfreq`, `bads`, `meas_date`, `highpass`, `lowpass`
- Channel types via `mne.channel_type` when available
- Annotations when present
- Montage name via `get_montage()` when set

FIF integer `unit` codes are **not** mapped to SI strings here (would invent units). String units attached on channel dicts are preserved as-is. `custom_ref_applied` is an integer flag in MNE Info, not a named reference; without an explicit string, reference stays unknown.

For 3D Epochs arrays, epoch 0 is taken only, with an explicit warning (no averaging/concatenation).

## MNE license / docs (researched)

| Item | Value |
|---|---|
| Project | MNE-Python |
| License | BSD-3-Clause (Copyright 2011–2025 MNE-Python authors) |
| License source | https://github.com/mne-tools/mne-python/blob/main/LICENSE.txt |
| Info API docs | https://mne.tools/stable/generated/mne.Info.html |
| Compatibility | Optional runtime dependency; fixtures and core tests run without MNE |

## Status vocabulary

`converted` | `inconclusive` | `rejected` | `error`

## Limitations

- Does not decode MNE FIF unit integers into physical units.
- Does not interpret `custom_ref_applied` as a named reference scheme.
- Epochs multi-epoch handling is intentionally narrow (epoch 0 + warning).
- No network I/O; no participant recordings; synthetic fixtures only in tests.
- Source IDs, provenance text, and a declared source SHA-256 are carried as
  metadata; this adapter does not authenticate the source or verify that hash
  against an external recording.
