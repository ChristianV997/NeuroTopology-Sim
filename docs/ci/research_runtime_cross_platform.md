# Research Runtime Cross-Platform Acceptance Specification

## 1. Overview and Purpose

The **Research Runtime Cross-Platform Acceptance Harness** provides an isolated, audited, and deterministic validation layer for the Batch 1 research-cycle infrastructure in `NeuroTopology-Sim`.

### Core Goals
- **Cross-Platform Verification**: Validate operational behavior across Windows (`nt`) and POSIX (`posix`) environments without modifying production code.
- **Strict Boundary Integrity**: Observe and test process lifecycle, file locking, PowerShell command construction, and path semantics through isolated subprocesses.
- **Black-Box Contract Compliance**: Provide typed contract models and fixtures for Batch 1 capabilities (bounded chunk caching, resumable transfers, cache eviction, atomic writes, and simulation checkpoints). If Batch 1 implementations are not yet merged to `origin/main`, integration tests are marked as `PENDING` while contracts are validated through black-box fixtures.
- **Zero Hallucinated Success**: On non-Windows hosts, Windows-specific behaviors are recorded as `UNSUPPORTED`, never `PASS`. On Windows hosts, POSIX-specific behaviors are recorded as `UNSUPPORTED`, never `PASS`.
- **Reproducibility & Safety**: All fixtures operate offline with synthetic data; no live networks, package installations, or dataset downloads.

---

## 2. Platform Acceptance Rules

Validators and scenarios strictly enforce the 10 cross-platform operating rules:

| Rule | Title | Enforcement Principle |
| :--- | :--- | :--- |
| **Rule 1** | Portable Execution | Portable contracts (paths, serialization, atomic writes, timeouts) run identically on all platforms. |
| **Rule 2** | Windows Specialization | Windows-specific tests (PowerShell, file locks, path normalization) execute only on Windows hosts. |
| **Rule 3** | POSIX Isolation | On POSIX hosts, Windows-specific behavior is recorded as `UNSUPPORTED`, never `PASS`. |
| **Rule 4** | Windows Isolation | On Windows hosts, POSIX-specific behavior (process groups, `os.killpg`, POSIX signals) is recorded as `UNSUPPORTED`, never `PASS`. |
| **Rule 5** | Empirical Execution | Never infer platform support from code inspection or static analysis alone; all checks execute live subprocesses. |
| **Rule 6** | Unsuppressed Failures | Never suppress a timeout, orphan leak, file-lock violation, or encoding failure. |
| **Rule 7** | Host Non-Conflation | Do not claim a Windows success result from a Linux or macOS host. |
| **Rule 8** | Zero Dataset Downloads | No external datasets (e.g. OpenNeuro) are downloaded; synthetic fixtures provide bounded data. |
| **Rule 9** | Zero Package Installs | No runtime `pip install` or environment modifications are allowed during runs. |
| **Rule 10** | Production Non-Modification | Do not modify production simulation runners, cache managers, or database files. |

---

## 3. Scenario Execution Matrix

The acceptance harness evaluates 14 discrete runtime scenarios:

| ID | Scenario | Category | Target OS | Description |
| :--- | :--- | :--- | :--- | :--- |
| 1 | `portable_path_and_serialization` | `portable_contracts` | All | Verifies cross-platform path manipulation and strictly finite JSON (`NaN`/`Inf` converted to `null`). |
| 2 | `windows_path_normalization` | `windows_reliability` | Windows | Verifies extended-length path prefix (`\\?\`), UNC path handling, and forward/backward slash normalization. |
| 3 | `powershell_smoke` | `powershell_command` | Windows/pwsh | Verifies injection-resistant PowerShell argument construction (`-NoProfile -NonInteractive -ExecutionPolicy Bypass`) without `shell=True`. |
| 4 | `atomic_replace` | `atomic_writes` | All | Verifies staged file writing (`.tmp_...`), synchronization (`os.fsync`), and atomic replacement (`os.replace`). |
| 5 | `locked_file_cleanup` | `windows_file_locks` | Windows | Probes Windows mandatory file locking (`ERROR_SHARING_VIOLATION` on open write handles) and verifies retry-backoff cleanup. |
| 6 | `timeout_termination` | `process_timeout` | All | Spawns a hanging process, enforces timeout, terminates the process, and verifies termination exit code. |
| 7 | `process_tree_cleanup` | `orphan_cleanup` | All | Spawns a multi-level process hierarchy, kills the root process, and verifies that no grandchild orphans survive. |
| 8 | `unicode_paths` | `unicode_support` | All | Creates deeply nested directory trees containing non-ASCII / Unicode characters (`αβγ_测试_🔬_日本語`), writes and verifies UTF-8 content. |
| 9 | `bounded_output` | `bounded_streaming` | All | Caps child process output to prevent memory explosion during high-volume stdout floods. |
| 10 | `malformed_child_output` | `error_resilience` | All | Ingests corrupted non-UTF8 binary byte streams from child stdout/stderr using `errors='replace'` without crashing. |
| 11 | `posix_signal_behavior` | `posix_signals` | POSIX | Validates POSIX process group signal propagation (`os.killpg`, `SIGKILL`). Recorded as `UNSUPPORTED` on Windows. |
| 12 | `bounded_chunk_cache_planning` | `batch1_cache` | All | Validates chunk budget sizing and LRU eviction planning. Probes production module; if missing, records integration as `PENDING`. |
| 13 | `resumable_transfer_metadata` | `batch1_transfer` | All | Validates multi-chunk download metadata tracking, SHA-256 validation, and resume token generation. |
| 14 | `simulation_checkpoint_recovery` | `batch1_simulation` | All | Validates simulation checkpoint state hash serialization and recovery pointer tracking. Probes production runner. |

---

## 4. Black-Box Contract Specifications

Batch 1 contracts are implemented in `tools.runner_acceptance.research_runtime.contracts`:

### 4.1. BoundedChunkCachePlan (`ResearchRuntime.ChunkCachePlan.v1`)
- `dataset_id`: Identifier for the cached dataset.
- `total_bytes`: Total byte size of source artifacts.
- `chunk_size_bytes`: Chunk division boundary (e.g., 1 MiB or 2 MiB).
- `max_cache_budget_bytes`: Strict upper bound on disk cache usage.
- `eviction_policy`: Eviction algorithm (default: `LRU`).
- `planned_chunks`: Ordered list of chunk offsets, byte lengths, and SHA-256 hashes.

### 4.2. ResumableTransferMetadata (`ResearchRuntime.ResumableTransfer.v1`)
- `transfer_id`: Unique transfer identifier.
- `source_uri`: Source URI (e.g. `openneuro://...`).
- `destination_path`: Target local file path.
- `total_expected_bytes`: Total expected payload size.
- `transferred_bytes`: Bytes written to disk so far.
- `completed_chunks`: Array of completed chunk indices.
- `resume_token`: Cryptographic token for resumable reconnection.
- `checksum_sha256`: Final payload SHA-256 digest.

### 4.3. SimulationCheckpointSpec (`ResearchRuntime.SimulationCheckpoint.v1`)
- `campaign_id`: Campaign execution ID.
- `run_id`: Run instance ID.
- `step_index`: Step/epoch number.
- `rng_state_hash`: Hash of pseudo-random number generator state.
- `state_payload_hash`: SHA-256 hash of serialized simulation state.
- `checkpoint_file`: Absolute path to checkpoint file.
- `is_recoverable`: Boolean recovery readiness flag.

---

## 5. CLI Reference

Run the acceptance suite via the CLI script:

```bash
# Run acceptance test suite and display formatted human-readable summary
python scripts/run_research_runtime_acceptance.py

# Emit strictly finite JSON report (NaN/Inf -> null)
python scripts/run_research_runtime_acceptance.py --json

# Save JSON and Markdown artifacts
python scripts/run_research_runtime_acceptance.py \
  --output outputs/acceptance/research_runtime_report.json \
  --markdown-output outputs/acceptance/research_runtime_report.md
```

### Exit Codes
- `0`: All supported scenarios passed. (Any `UNSUPPORTED` or `PENDING` cases do not fail the run).
- `1`: One or more scenarios encountered a `FAIL` or `ERROR` condition.

---

## 6. Known Platform Limitations & Behavioral Nuances

### Windows (`nt`)
- **File Locking**: Unshared open file handles on Windows cause immediate `PermissionError` (WinError 32: `ERROR_SHARING_VIOLATION`) if deletion or moving is attempted. Production cleanups must implement retry loops with exponential backoff or ensure handles are closed before unlinking.
- **Path Lengths**: Paths exceeding 260 characters require normalization with the `\\?\` prefix or long-path registry enablement.
- **Process Trees**: Windows does not support POSIX process groups natively; process trees must be terminated using `taskkill /F /T /PID <pid>` or Windows Job Objects to prevent orphan child processes.
- **PowerShell Execution Policy**: PowerShell commands must explicitly include `-ExecutionPolicy Bypass` and `-NoProfile` to avoid configuration prompts or permission blocks.

### POSIX (`posix`)
- **Advisory File Locking**: Unlinking an open file on Linux/macOS removes directory entry immediately while keeping inode alive until handle close. Windows-specific lock expectations are marked `UNSUPPORTED`.
- **Process Signals**: POSIX supports `os.killpg(pgid, signal.SIGKILL)` to terminate process groups; on Windows, this is marked `UNSUPPORTED`.
