# Reliable Simulation Campaign Runner

## 1. Overview and Threat Model

Simulation campaigns in computational neuroscience and topological data analysis often execute over long durations across multiple subjects, sessions, runs, parameter sweeps, and temporal windows. Traditional execution scripts suffer from three critical failure modes:

1. **Silent Partial Success**: A campaign completes a fraction of its scheduled work units (e.g. 80 out of 100), encounters an unhandled exception or silent timeout on unit 81, and terminates. Downstream pipelines ingest the output directory as if the entire cohort or parameter sweep succeeded, generating biased scientific findings without raising an error.
2. **Infinite Retries of Broken Logic**: Scripts with coarse retry loops blindly retry correctness bugs, syntax errors, or missing dependencies repeatedly, consuming compute budgets and obscuring root causes.
3. **Leaked Orphan Processes**: Long-running or hung simulation kernels killed via simple parent `SIGTERM` leave orphaned worker child processes or GPU/CPU threads consuming memory and pinning locks.

The **Reliable Simulation Campaign Runner** (`tools/simulation_runtime/`) eliminates these risks through a formal manifest-driven execution contract, strict resource guards, process-tree sandboxing, atomic checkpointing, and unambiguous outcome classification.

---

## 2. Core Architectural Guarantees

- **Manifest-First Execution**: The campaign workload must be fully declared in a validated `CampaignManifest` before execution begins. Dynamic, unbounded ad-hoc iteration is disallowed.
- **Single-Unit Bounded Execution**: By default, work units execute sequentially (`max_workers=1`) in isolated child processes with deterministic ordering. Concurrency is configurable but capped by a strict resource policy.
- **Process-Tree Cleanup**: On timeout or termination, the runner signals the entire process group (`CTRL_BREAK_EVENT` and `taskkill /F /T` on Windows; `killpg(SIGTERM/SIGKILL)` on POSIX), guaranteeing zero orphan processes.
- **Atomic Per-Unit Persistence**: Each unit writes its individual result to `units/<unit_id>.json` using temporary files and atomic filesystem replacement (`os.replace` with `os.fsync`).
- **Continuous Checkpointing**: The aggregated campaign state (`checkpoint.json`) is updated atomically after *every* completed unit.
- **Idempotent Resumption**: When resumed, the runner loads the checkpoint, validates the configuration hash, verifies output checksums, and skips already completed units without recomputation.
- **Visible Partiality**: If interrupted or cancelled, campaigns remain marked `is_complete: false` and `is_partial: true`. Unreached units are explicitly recorded as `NOT_RUN`. A campaign is complete *only* when every unit has reached an explicit terminal status.
- **Selective Retries**: Only explicitly retryable infrastructure failures (`NETWORK_FAILURE`, `DISK_FAILURE`, `MEMORY_FAILURE`) are retried up to a bounded retry count. Correctness failures (`CORRECTNESS_FAILURE`) and missing dependencies (`DEPENDENCY_MISSING`) are recorded immediately as terminal failures and never retried.
- **Honest Telemetry**: Unavailable metrics are strictly serialized as `null` (never `0` or synthetic placeholders). Finite JSON serialization (`allow_nan=False`) is enforced throughout.

---

## 3. Terminal Outcome Taxonomy

Every unit attempt terminates in exactly one of nine mutually exclusive outcome states:

| Outcome State | Category | Description | Retry Policy |
| :--- | :--- | :--- | :--- |
| `PASS` | Success | Unit executed to completion; all declared outputs exist and verified. | Terminal (no retry needed) |
| `CORRECTNESS_FAILURE` | Algorithmic | Child process failed due to assertion error, mathematical invalidity, or non-zero exit code from test logic. | **Never retried** |
| `TIMEOUT` | Budget | Child process exceeded its allotted wall-clock `timeout_s`. Process tree killed. | Non-retryable budget cut |
| `DEPENDENCY_MISSING` | Environment | Required Python module, shared library, or binary was missing in the execution environment. | **Never retried** |
| `NETWORK_FAILURE` | Infrastructure | Network connection error or socket timeout during operation. | Retryable up to `max_retries` |
| `DISK_FAILURE` | Infrastructure | Insufficient disk space detected before execution, disk full during write, or I/O failure. | Retryable up to `max_retries` |
| `MEMORY_FAILURE` | Infrastructure | Process terminated by OS OOM killer (SIGKILL/137) or exceeded configured memory budget. | Retryable up to `max_retries` |
| `UNKNOWN_FAILURE` | Unclassified | Process died from unclassified signal or unexpected runtime fault. | Non-retryable |
| `NOT_RUN` | Pending | Unit was scheduled in manifest but campaign was interrupted or cancelled before execution began. | Pending execution |

---

## 4. Schema Specifications

### 4.1 Campaign Manifest (`simulation_campaign_manifest_v1`)

```json
{
  "schema_version": "simulation_campaign_manifest_v1",
  "campaign_id": "campaign_20260910_ds005620_cohort",
  "created_at": "2026-09-10T23:00:00Z",
  "code_commit": "618ca081039759510d27a7a772cd47c95985600f",
  "configuration_hash": "a1b2c3d4e5f6...",
  "seed": 42,
  "units": [
    {
      "unit_id": "sub-01_ses-01_run-01_win-000",
      "command": ["python", "-m", "sim.worker", "--subject", "sub-01"],
      "subject_id": "sub-01",
      "session_id": "ses-01",
      "run_id": "run-01",
      "window_id": "win-000",
      "parameter_case": {"n_nodes": 100, "dt": 0.001},
      "expected_outputs": ["outputs/sub-01_win-000.h5"],
      "timeout_s": 120.0,
      "dependencies": ["numpy", "scipy"],
      "estimated_disk_mb": 25.0,
      "estimated_memory_mb": 256.0,
      "retryable": true,
      "max_retries": 2
    }
  ],
  "environment": {
    "python_version": "3.14.7",
    "platform": "Windows-11",
    "processor": "AMD64",
    "os": "nt",
    "hostname": "NODE-01"
  },
  "resource_policy": {
    "max_workers": 1,
    "concurrency_cap": 8,
    "min_disk_free_mb": 500.0,
    "max_memory_mb": 4096.0,
    "max_retries_per_unit": 2,
    "default_timeout_s": 60.0
  }
}
```

### 4.2 Checkpoint State (`simulation_campaign_state_v1`)

Located at `<output_dir>/checkpoint.json`:

```json
{
  "schema_version": "simulation_campaign_state_v1",
  "campaign_id": "campaign_20260910_ds005620_cohort",
  "manifest_hash": "a1b2c3d4e5f6...",
  "completed_units": {
    "sub-01_ses-01_run-01_win-000": {
      "unit_id": "sub-01_ses-01_run-01_win-000",
      "outcome": "PASS",
      "status": "COMPLETED",
      "exit_code": 0,
      "elapsed_s": 12.45,
      "retry_count": 0,
      "stdout": "Processing complete.\n",
      "stderr": "",
      "error_message": null,
      "peak_memory_bytes": 145236992,
      "output_checksums": {
        "outputs/sub-01_win-000.h5": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
      },
      "metrics": null,
      "started_at": "2026-09-10T23:01:00Z",
      "completed_at": "2026-09-10T23:01:12Z"
    }
  },
  "active_unit": null,
  "is_complete": false,
  "is_partial": true,
  "cancelled": false,
  "summary": {
    "PASS": 1,
    "CORRECTNESS_FAILURE": 0,
    "TIMEOUT": 0,
    "DEPENDENCY_MISSING": 0,
    "NETWORK_FAILURE": 0,
    "DISK_FAILURE": 0,
    "MEMORY_FAILURE": 0,
    "UNKNOWN_FAILURE": 0,
    "NOT_RUN": 99
  },
  "last_checkpoint_at": "2026-09-10T23:01:12Z"
}
```

---

## 5. Pre-Execution Budget Guards

Before launching each unit, the runner executes three mandatory pre-execution checks:

1. **Dependency Guard (`check_dependencies`)**:
   Verifies that every module specified in `unit.dependencies` can be imported via Python's `importlib.util.find_spec`, or exists as an executable binary on `PATH`. If missing, the unit immediately transitions to `DEPENDENCY_MISSING` without launching a subprocess.
2. **Memory Guard (`check_memory_budget`)**:
   Compares `unit.estimated_memory_mb` against `policy.max_memory_mb`. If the estimate exceeds the campaign policy, or if available host RAM is insufficient, the unit is rejected with `MEMORY_FAILURE`.
3. **Disk Guard (`check_disk_budget`)**:
   Inspects filesystem free space via `shutil.disk_usage`. Ensures available space exceeds `unit.estimated_disk_mb + policy.min_disk_free_mb`. If headroom is exhausted, the unit transitions to `DISK_FAILURE` to avoid crashing the host or corrupting filesystem state.

---

## 6. CLI Usage Guide

### 6.1 Validate Manifest (Dry-Run)
```bash
python scripts/run_simulation_reliable.py --manifest configs/campaign_example.json --dry-run
```

### 6.2 Execute Campaign
```bash
python scripts/run_simulation_reliable.py \
    --manifest configs/campaign_example.json \
    --output-dir outputs/campaign_run_01 \
    --max-workers 1 \
    --format summary
```

### 6.3 Resuming an Interrupted Campaign
If a campaign was stopped, simply rerun pointing to the same `--output-dir`. Completed units will be read from the checkpoint and verified, continuing from the first unexecuted unit:
```bash
python scripts/run_simulation_reliable.py \
    --manifest configs/campaign_example.json \
    --output-dir outputs/campaign_run_01
```

---

## 7. Guardrails and Scientific Non-Claims

1. **No Consciousness or Clinical Inferences**: Execution telemetry, wall-clock timing, and peak memory metrics provide computational accounting only. They carry zero implications regarding consciousness, subjective experience, or clinical diagnosis.
2. **No Fabricated Placeholder Metrics**: Missing metrics must remain serialized as `null`. No heuristic default or placeholder numbers may be inserted.
3. **Finite JSON Integrity**: All output structures enforce `allow_nan=False` during serialization. Floating-point non-finite values (`NaN`, `Inf`, `-Inf`) are strictly scrubbed to `null` before writing to disk.
