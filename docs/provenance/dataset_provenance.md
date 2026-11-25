# Dataset provenance contract

Local-first contract for EEG/MEG/TDA inputs. A file that exists is not
empirical evidence. A source URL is metadata only and is never fetched.

Owned files:

- `shared/provenance/**`
- `scripts/validate_dataset_provenance.py`
- `tests/provenance/**`
- `docs/provenance/**`

Do not edit capability registry, interop, MNE adapters, Bayesian
falsification, `RunRecordV1`, CI, dashboards, or datasets from this layer.

## Schema

`NeuroTopologySim.DatasetProvenance.v1`

Origin labels:

- `synthetic_demo`
- `empirical_local`
- `external_solver`
- `unavailable`

Statuses:

- `PASS_SYNTHETIC` — valid local synthetic file; `evidence_claim_allowed=false`
- `PASS_EMPIRICAL_LOCAL` — complete local empirical provenance; only this status may set `evidence_claim_allowed=true`
- `PASS_EXTERNAL_SOLVER` — valid solver artifact; not independently acquired data
- `INCOMPLETE` — file readable but required provenance is missing
- `FAIL` — missing file, checksum mismatch, invalid rate/shape, or non-finite data
- `UNAVAILABLE` — no usable local input

Missing provenance always blocks formal evidence claims.

## Attachment without changing RunRecordV1

```text
runs/<run_id>/RunRecord.json
runs/<run_id>/dataset_provenance.json
```

```python
from shared.provenance.contract import validate_declaration, write_sidecar, attach_provenance

record = validate_declaration(declaration)
write_sidecar(record, "runs/abc123")
sidecar = attach_provenance({"run_id_ref": "abc123"}, record)
```

`attach_provenance` refuses mappings that look like `RunRecordV1`.

## Consumers

`consumer_view(record)` exposes origin, status, evidence gate, sampling
rate, channel/sample counts, units, filter bands, and TDA configuration
for Bayesian falsification, topology, and report generators.

## Limits

- Local `.npy` / `.npz` arrays only (`samples x channels`).
- `.fif` / `.edf` / BIDS are not parsed here; convert offline first.
- Checksums are SHA-256 of the local file bytes.
- Validation performs no network I/O.
