# Approved Acquisition Adapter

## 1. Overview & Architecture

The **Approved Acquisition Adapter** (`tools.data_access.approved_adapter`) provides an approved, policy-enforcing data acquisition layer for OpenNeuro, BIDS, DANDI, and custom scientific data sources in `NeuroTopology-Sim`.

It is an **additive** layer that wraps and reuses the canonical `BoundedChunkCache` interface (`tools.data_access.chunk_cache`), providing:
- **Metadata-first planning** prior to downloading data bytes.
- **Fail-closed network admission control** (`allow_network=False` by default).
- **Mandatory byte bounding** (rejection of unconstrained full-object and full-dataset downloads).
- **Mandatory license access gating** (rejection of non-open or restricted data access).
- **Active lease protection** for declared consumers.
- **Immediate post-consumption eviction** (`delete_on_final_consumer`).
- **Legacy acquisition detection and migration reporting**.

```
+-----------------------------------------------------------------------------------+
|                        Approved Acquisition Adapter Layer                         |
|                                                                                   |
|  +---------------------------+       +-----------------------------------------+  |
|  | BoundedAcquisitionRequest | ----> | ApprovedAcquisitionAdapter.plan()       |  |
|  +---------------------------+       +-----------------------------------------+  |
|                                                           |                       |
|                                            (Metadata-First Dry-Run Plan)          |
|                                            - Validates size > 0                   |
|                                            - Rejects full objects by default      |
|                                            - Validates license (CC0 / CC-BY / OA) |
|                                            - Verifies disk headroom & budget      |
|                                            - Emits RFC 8259 JSON + SHA-256        |
|                                                           v                       |
|                                      +-----------------------------------------+  |
|                                      | ApprovedAcquisitionAdapter.acquire()    |  |
|                                      +-----------------------------------------+  |
|                                                           |                       |
|                                          (Fail-Closed Gate: allow_network=True)   |
|                                          - Manifest Registration                  |
|                                          - Protective Lease Acquisition           |
|                                          - Consumer Registry Entry                |
|                                                           v                       |
|                                      +-----------------------------------------+  |
|                                      | BoundedChunkCache (transfer & staging)  |  |
|                                      +-----------------------------------------+  |
|                                                           |                       |
|                                          (Pipeline Consumers Process Chunk)       |
|                                                           v                       |
|                                      +-----------------------------------------+  |
|                                      | ApprovedAcquisitionAdapter.consume()    |  |
|                                      +-----------------------------------------+  |
|                                                           |                       |
|                                          (When final consumer acknowledges)       |
|                                          - Protective lease released              |
|                                          - Chunk unlinked from disk immediately   |
|                                          - Cache record status set to EVICTED     |
+-----------------------------------------------------------------------------------+
```

---

## 2. Key Guardrails & Invariants

### 2.1 Metadata-First Dry-Run Planning
The `plan()` method evaluates request feasibility with **zero network data-byte downloads**. It verifies disk space, memory/cache budget, source path safety, byte bounding, and licensing, returning a cryptographically signed `BoundedAcquisitionPlan`.

### 2.2 Rejection of Unknown Sizes
Requests where `expected_size_bytes` is `0`, negative, or omitted are rejected with `UNKNOWN_SIZE_REJECTED`. Size must always be pre-negotiated from manifest metadata.

### 2.3 Strict Rejection of Full Objects and Full Datasets
- **Full Objects**: Full-object requests (where `start_byte == 0` and `end_byte >= expected_size_bytes - 1`, or 1-byte files covering `[0, 0]`) are **strictly rejected** in production with `FULL_OBJECT_REJECTED`. There is no production escape hatch. In test suites only, internal mocking can specify `_test_only_allow_full_object=True`, which is ignored unless the environment variable `NEUROTOPOLOGY_ALLOW_TEST_FULL_OBJECT=1` is explicitly set.
- **Full Datasets & Wildcards**: Any request targeting wildcard patterns (`*`, `**/*`, `sub-*`, `?`, `[a-z]`) or dataset-level/directory-level identifiers (`.`, empty path) is **strictly rejected** with `FULL_DATASET_REJECTED`.
- **Unrestricted Path Escapes**: Paths containing directory traversal (`..`), absolute roots (`/`), or drive letters (`C:`) are **strictly rejected** with `UNRESTRICTED_PATH_REJECTED`.

### 2.4 Mandatory License Access Gating
Requests must specify an explicit `license_state`. Only open licenses (`open_cc0`, `open_cc_by`, `open_access`) are approved for automated acquisition. Unspecified, restricted, or unknown licenses are rejected with `LICENSE_RESTRICTED`.

### 2.5 Fail-Closed Network Permission Gate
Acquisitions strictly require `allow_network=True`. If omitted or `False`, `acquire()` fails immediately with `NETWORK_DISABLED` and performs zero network calls.

### 2.6 Consumer Lifecycle & `delete_on_final_consumer`
When a chunk is acquired with declared pipeline consumers (e.g., `["filter_step", "spectral_step"]`):
1. A protective lease is held on the chunk so background LRU eviction will not reclaim it during processing.
2. Each consumer calls `consume(dataset_id, object_path, consumer_id)`.
3. When the final declared consumer completes, the lease is released and the file is immediately unlinked from disk, setting its status in the manifest to `EVICTED`.

### 2.7 Strict RFC 8259 Finite JSON & Machine-Readable Policy Registration
All serializations use `finite_value()`, which explicitly rejects `NaN`, `Infinity`, and `-Infinity`, preserving exact integer and null fidelity.
Furthermore, the adapter exports machine-readable policy metadata via `adapter.get_policy_registration()` and `get_approved_adapter_policy_record()`, guaranteeing compliance with downstream policy enforcement without direct coupling.

---

## 3. Error Taxonomy (`AdapterErrorCode`)

| Error Code | Trigger Condition |
| :--- | :--- |
| `FULL_DATASET_REJECTED` | Request path contains wildcard characters (`*`, `?`, `[]`) or dataset-level target (`.`). |
| `FULL_OBJECT_REJECTED` | Request covers the full file range `[0, expected_size - 1]`. |
| `UNRESTRICTED_PATH_REJECTED` | Path contains directory traversal (`..`), leading slashes, or drive letters. |
| `UNKNOWN_SIZE_REJECTED` | `expected_size_bytes` is missing, 0, or negative. |
| `MISSING_CACHE_BUDGET` | `cache_budget_bytes` is missing, 0, or negative. |
| `MISSING_EVICTION_POLICY` | `eviction_policy` is missing or not a recognized `EvictionPolicy`. |
| `MISSING_CHECKSUM_POLICY` | `checksum_policy` is missing or not a recognized `ChecksumPolicy`. |
| `NETWORK_DISABLED` | `allow_network=False` during an acquisition attempt. |
| `LICENSE_RESTRICTED` | `license_state` is not in `{open_cc0, open_cc_by, open_access}`. |
| `CHECKSUM_MISMATCH` | Actual SHA-256 of downloaded chunk does not match `expected_checksum`. |
| `DISK_EXHAUSTION` | Free disk space minus headroom reserve is insufficient. |
| `CACHE_BUDGET_EXCEEDED` | Requested chunk size exceeds maximum configured cache budget. |
| `ACTIVE_LEASE_LOCKED` | Item cannot be modified/evicted due to active consumer lease lock. |
| `INVALID_SOURCE_PATH` | Path contains invalid or empty components. |
| `INCOMPLETE_METADATA` | Required request fields are empty or invalid. |
| `TRANSIENT_RETRY_EXHAUSTED` | Network resets or dropouts exceeded `max_retries`. |

---

## 4. CLI Reference (`scripts/plan_bounded_acquisition.py`)

### 4.1 Dry-Run Planning (`plan`)
```bash
python scripts/plan_bounded_acquisition.py plan \
  --dataset-id "ds004504" \
  --object-path "sub-01/eeg/sub-01_task-rest_eeg.edf" \
  --source-uri "https://openneuro.org/crn/datasets/ds004504/files/sub-01/eeg/sub-01_task-rest_eeg.edf" \
  --expected-size 1048576 \
  --start-byte 0 \
  --end-byte 65535 \
  --catalog-type "openneuro" \
  --license-state "open_cc0" \
  --format markdown
```

### 4.2 Executing Bounded Acquisition (`acquire`)
```bash
python scripts/plan_bounded_acquisition.py acquire \
  --dataset-id "ds004504" \
  --object-path "sub-01/eeg/sub-01_task-rest_eeg.edf" \
  --source-uri "https://openneuro.org/crn/datasets/ds004504/files/sub-01/eeg/sub-01_task-rest_eeg.edf" \
  --expected-size 1048576 \
  --start-byte 0 \
  --end-byte 65535 \
  --license-state "open_cc0" \
  --allow-network \
  --consumer-id "feature_extraction_pipeline" \
  --format json
```

### 4.3 Acknowledging Consumer Completion (`consume`)
```bash
python scripts/plan_bounded_acquisition.py consume \
  --dataset-id "ds004504" \
  --object-path "sub-01/eeg/sub-01_task-rest_eeg.edf" \
  --consumer-id "feature_extraction_pipeline" \
  --format markdown
```

### 4.4 Scanning Legacy Unconstrained Callers (`report-legacy`)
```bash
python scripts/plan_bounded_acquisition.py report-legacy \
  --repo-root . \
  --format markdown
```

---

## 5. Python API Reference

### 5.1 `BoundedAcquisitionRequest`
```python
from tools.data_access.approved_adapter import (
    BoundedAcquisitionRequest,
    ChecksumPolicy,
    EvictionPolicy,
    LicenseAccessState,
    SourceCatalogType,
)

req = BoundedAcquisitionRequest(
    dataset_id="ds004504",
    object_path="sub-01/eeg/sub-01_task-rest_eeg.edf",
    source_uri="https://openneuro.org/crn/datasets/ds004504/files/sub-01/eeg/sub-01_task-rest_eeg.edf",
    expected_size_bytes=25000000,
    start_byte=0,
    end_byte=65535,
    catalog_type=SourceCatalogType.OPENNEURO.value,
    license_state=LicenseAccessState.OPEN_CC0.value,
    checksum_policy=ChecksumPolicy.SHA256_IF_AVAILABLE.value,
    declared_consumers=["eeg_pipeline_step_1", "eeg_pipeline_step_2"],
    eviction_policy=EvictionPolicy.DELETE_ON_FINAL_CONSUMER.value,
    allow_network=True,
)
```

### 5.2 `ApprovedAcquisitionAdapter`
```python
from tools.data_access.approved_adapter import ApprovedAcquisitionAdapter

adapter = ApprovedAcquisitionAdapter(
    cache_root=".cache/approved_adapter",
    max_cache_bytes=500 * 1024 * 1024,
)

# 1. Plan dry-run (zero bytes downloaded)
plan = adapter.plan(req)
if not plan.is_executable:
    print("Rejected:", plan.rejection_reasons)

# 2. Acquire chunk
result = adapter.acquire(req)
if result.success:
    print(f"Acquired chunk at {result.cached_path}")

# 3. Release / consume
adapter.consume("ds004504", "sub-01/eeg/sub-01_task-rest_eeg.edf", "eeg_pipeline_step_1")
adapter.consume("ds004504", "sub-01/eeg/sub-01_task-rest_eeg.edf", "eeg_pipeline_step_2")
# Chunk is now unlinked and evicted automatically
```

---

## 6. Legacy Callers Inventory & Migration Plan

The scanner (`tools.data_access.approved_adapter.legacy_reporter`) detected existing legacy download scripts in the repository that perform unconstrained or unbudgeted acquisitions:

1. **`dataset_acquisition/download_eeg.py`**:
   - Uses unbudgeted direct downloads without byte-range restrictions.
   - **Migration**: Wrap with `ApprovedAcquisitionAdapter` supplying dataset ID, manifest sizes, and bounded byte ranges.
2. **`scripts/fetch_real_datasets.py`**:
   - Downloads full datasets into local disk directories.
   - **Migration**: Replace bulk fetches with metadata manifest indexing and on-demand chunk leases using `plan_bounded_acquisition.py`.
3. **`scripts/download_sample_data.py`**:
   - Downloads sample files using unconstrained HTTP requests.
   - **Migration**: Use `MockTransferAdapter` in local unit tests and `ApprovedAcquisitionAdapter` for external assets.
