# Cross-Platform Research Execution Acceptance Harness

## 1. Overview and Operational Purpose

The **Research Execution Acceptance Harness** (`tools/platform_acceptance/research_execution/`) provides automated, tamper-evident verification of cross-platform guarantees across the NeuroTopology-Sim runtime environment.

Scientific simulation and topological data processing pipelines require predictable execution across disparate operating systems (Windows, Linux, macOS). Discrepancies in process termination, file locking semantics, path separators, PowerShell quoting, or cache eviction can lead to data corruption, orphan worker leaks, or silent execution failures.

The acceptance harness validates seven critical operational pillars:

1. **Approved Local-Only Metadata & Bounded Transfers**: Enforces manifest-first metadata registration; rejects downloads of unindexed or out-of-budget files.
2. **Cache Eviction & Partial Integrity**: Verifies LRU eviction under budget pressure, active lease protection (`LeaseHandle`), atomic partial-file cleanup (`.part.*`), and checksum mismatch abortion.
3. **Process Timeout & Descendant Cleanup**: Enforces hard wall-clock timeouts and whole-process-group termination (`CTRL_BREAK_EVENT` and `taskkill` on Windows; `killpg` on POSIX).
4. **Output-Root Containment**: Proves strict containment within output and cache roots, rejecting parent directory traversal (`..`), absolute path escapes, and illegal characters.
5. **Finite JSON & Artifact Integrity**: Guarantees `allow_nan=False` serialization, scrubbing non-finite floats (`NaN`, `Inf`, `-Inf`) and producing tamper-evident cryptographic checksums.
6. **PowerShell Wrapper Syntax & Execution**: Exercises single-quote argument escaping (`'plain'`, `'o''brien'`), non-interactive command formatting, and PowerShell child execution.
7. **Windows Native Primitives & POSIX Separation**: Exercises Windows-specific primitives (file locks via `msvcrt`, atomic replacement via `os.replace`, backslash normalization, and symlink privilege checks). **On non-Windows hosts, all Windows-specific test cases are classified as `UNSUPPORTED`, never `PASS`**.

---

## 2. Platform Matrix

Every harness execution generates an explicit `PlatformMatrix` summarizing environment properties and category support:

```json
{
  "os_name": "nt",
  "platform_release": "Windows-11-10.0.26100-SP0",
  "python_version": "3.14.7",
  "is_windows": true,
  "powershell_available": true,
  "powershell_version": "7.4.2",
  "supported_categories": [
    "data_access",
    "cache_eviction",
    "process_execution",
    "output_containment",
    "artifact_integrity",
    "powershell_operations",
    "windows_specifics"
  ],
  "unsupported_categories": []
}
```

On POSIX/Linux hosts, `windows_specifics` is automatically placed into `unsupported_categories`, and individual Windows-specific test cases report `UNSUPPORTED`.

---

## 3. Acceptance Test Case Catalog

| Test Case Name | Category | Scope | Guarantee Verified |
| :--- | :--- | :--- | :--- |
| `local_metadata_registration` | `data_access` | Cross-platform | Manifest-first rule: unregistered object access fails with `MISSING_OBJECT`. |
| `bounded_cache_budget_enforcement` | `data_access` | Cross-platform | Requests exceeding total cache capacity fail with `CACHE_BUDGET_EXCEEDED`. |
| `atomic_partial_and_checksum_mismatch` | `cache_eviction` | Cross-platform | Corrupt transferred bytes abort with `CHECKSUM_MISMATCH`; `.part.*` unlinked. |
| `retry_classification` | `cache_eviction` | Cross-platform | Transient network resets are retried; fatal errors are terminal. |
| `lru_eviction_and_lease_protection` | `cache_eviction` | Cross-platform | LRU eviction clears unleased items; active `LeaseHandle` chunks remain immune. |
| `process_timeout_and_cleanup` | `process_execution` | Cross-platform | Subprocesses exceeding deadline are terminated without leaving orphans. |
| `output_containment_and_traversal_rejection` | `output_containment` | Cross-platform | Traversal attempts (`..`, drive letters, invalid chars) are strictly rejected. |
| `finite_json_and_malformed_artifact_rejection` | `artifact_integrity` | Cross-platform | `allow_nan=False` serialization scrubs non-finite numbers to `null`. |
| `powershell_wrapper_syntax_and_quoting` | `powershell_operations` | Cross-platform | Single-quote escaping rules and `-NoProfile -NonInteractive` verified. |
| `powershell_execution` | `powershell_operations` | Host-dependent | Executes child command via PowerShell when available (`UNSUPPORTED` otherwise). |
| `windows_process_tree_termination` | `windows_specifics` | Windows-only | Process tree killed via `taskkill /F /T` (`UNSUPPORTED` on POSIX). |
| `windows_path_separators_normalization` | `windows_specifics` | Windows-only | Backslashes normalized to canonical forward slashes (`UNSUPPORTED` on POSIX). |
| `windows_file_locking` | `windows_specifics` | Windows-only | `msvcrt.locking` mandatory locking cycle verified (`UNSUPPORTED` on POSIX). |
| `windows_atomic_replacement` | `windows_specifics` | Windows-only | `os.replace` replaces target atomically on NTFS (`UNSUPPORTED` on POSIX). |
| `windows_symlink_privilege_handling` | `windows_specifics` | Windows-only | Inspects Developer Mode / admin privileges safely (`UNSUPPORTED` on POSIX). |

---

## 4. CLI Usage Reference

### 4.1 Basic Invocation
```bash
python scripts/run_research_execution_acceptance.py
```

### 4.2 JSON Output with Report File
```bash
python scripts/run_research_execution_acceptance.py \
    --output artifacts/acceptance_report.json \
    --format json
```

### 4.3 Strict Verification Mode
In strict mode, the runner exits with code `2` if any unsupported platform cases exist (useful in platform-specific CI matrices):
```bash
python scripts/run_research_execution_acceptance.py --strict
```

---

## 5. Security & Isolation Guardrails

- **Zero Network Operations**: All transfer tests use in-memory `MockTransferAdapter` fixtures. No HTTP requests, S3 calls, AWS Braket, or OpenNeuro endpoints are touched.
- **Temporary Containment**: All acceptance files and cache directories reside within isolated temporary directory trees (`tempfile.TemporaryDirectory`) that are automatically unlinked upon test completion.
- **No Git State Mutation**: Acceptance tests never modify git commits, index, or working trees.
