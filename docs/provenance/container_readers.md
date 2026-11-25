# Container provenance readers

Lazy inspection of local EEG/MEG containers. This is not NPY/NPZ array
validation and is not independent empirical validation.

Owned files:

- `shared/provenance/readers.py`
- `tests/provenance/test_container_readers.py`
- `docs/provenance/container_readers.md`
- `scripts/inspect_local_recording_provenance.py`

Do not edit DatasetProvenance.v1 contract files, adapters, interop,
falsification, CI, dashboards, or datasets from this layer.

## Formats

| Format | How metadata is read | Optional dependency |
| --- | --- | --- |
| EDF/BDF | 256-byte + per-channel header only | none |
| BrainVision VHDR | text header; `.eeg` is not loaded | none |
| BIDS `*_eeg.json` / `*_meg.json` | sidecar JSON + optional `channels.tsv` | none |
| FIF / FIF.GZ | `mne.io.read_raw_fif(..., preload=False)` | `mne` |

Missing `mne` returns `capability=missing_optional_dependency`. Packages are
never installed. Files are never downloaded. Signal samples are never loaded.

## DatasetProvenance.v1 compatibility

`ContainerInspection.as_provenance_declaration()` emits the v1 field names
(`origin`, `local_path`, `file_checksum_sha256`, `sampling_rate_hz`,
`channel_count`, `montage_channels`, ...). It does not call the array
validator and does not set `evidence_claim_allowed`.

`synthetic_demo` versus `empirical_local` is preserved from the caller.

## Limits

- A SHA-256 of a local container is not empirical evidence.
- Channel names without digitization are `coordinate_status=inferred`.
- Duration is unavailable for VHDR unless stated in the header.
- FIF inspection without MNE cannot parse the binary header here.
