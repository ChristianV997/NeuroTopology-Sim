# Provenance-preserving BIDS adapter

`data/bids_ingest.py` and `data/openneuro_loader.py` expose a narrow,
metadata-first BIDS access contract. The adapter validates **BIDS structure**;
it does **not** validate scientific truth.

Schema: `BIDSAdapterManifest.v1`.

## Guarantees

- Network is **disabled by default** (`allow_network=False`).
- Full-dataset downloads and unrestricted remote reads are **rejected**.
- Access requires an **explicit local root** or a **bounded approved remote window**
  (`relative_path` + time window).
- PyBIDS queries (when installed) are metadata-only and do not materialize
  full datasets.
- MNE-BIDS is optional for indexing; when absent, a structural filesystem
  index is used and labelled `local_bids_unvalidated` / recorded in
  `optional_dependencies`.
- Condition labels are accepted only from an **explicit condition manifest**
  with `confirmed=true`. Filename task tokens are structural entities, not
  confirmed conditions.
- Source checksums may be `null` with `checksum_state="unknown"`; checksums are
  never fabricated.
- Lazy window reads are allowed only for bounded local windows.
- Manifests are deterministic strict JSON (`allow_nan=False`) with
  `scientific_pass: false`.

## Primary APIs

```python
from data.bids_ingest import (
    BIDSAccessRequest,
    BoundedWindowRequest,
    index_bids_metadata,
    plan_bounded_window_access,
    read_bounded_window_lazy,
)
from data.openneuro_loader import (
    ensure_local_bids_index,
    plan_openneuro_bounded_window,
    reject_full_dataset_download,
    openneuro_download,
)
```

### Metadata index

```python
manifest = index_bids_metadata(
    BIDSAccessRequest(dataset_id="dsFIX001", local_root="/path/to/bids")
)
# manifest["bids_validation"] holds structural / optional validator results
```

### Bounded window

```python
plan = plan_bounded_window_access(
    BIDSAccessRequest(
        dataset_id="dsFIX001",
        local_root="/path/to/bids",
        relative_path="sub-01/eeg/sub-01_task-rest_run-01_eeg.edf",
        window=BoundedWindowRequest(start_s=0.0, end_s=2.0),
    )
)
```

### Rejected patterns

- `allow_full_dataset=True`
- remote URI without network opt-in
- remote URI without `relative_path` and bounded window
- `openneuro_download(...)` / `reject_full_dataset_download(...)`
- condition labels with `confirmed=false` or missing manifest entries used as
  inferred labels
- condition labels with non-boolean `confirmed` values (e.g. string `"true"` or int `1`)
- bare string labels (flat `{relative_path: label}` or a `recordings` string
  entry) without `confirmed=true`
- `relative_path` that resolves outside `local_root` or contains traversal/anchored
  segments in local or remote window plans (parent traversal `..`, absolute path,
  drive prefix, or a symlink that leaves the root)
- `relative_path` that is empty, whitespace, or resolves to `local_root` itself (`"."`)
- boolean, non-finite, non-positive, or out-of-range `BoundedWindowRequest` bounds
  (`start_s`, `end_s`, `max_duration_s > 600.0`, or non-integer `max_bytes`)
- `expected_checksum` mismatch against computed file digest or unmatched `relative_path`
- malformed BIDS entities (empty entity values like `sub-`, `run-`, or non-alphanumeric tokens)
  or empty/non-string `Name`/`BIDSVersion` in `dataset_description.json`

## Scientific limitation

A valid BIDS structure, a complete manifest, or a successful bounded window
read is **not** empirical confirmation, biological validation, or a scientific
`PASS`. Missing metrics remain JSON `null`.
