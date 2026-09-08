# Cross-Platform Compatibility Harness (`tools.platform_compat`)

## Overview

The `tools.platform_compat` package provides a unified, platform-neutral compatibility and audit subsystem for `NeuroTopology-Sim`. It addresses common cross-platform friction points across Windows, macOS, and Linux—including separator differences, case-folding, path length restrictions, non-admin symlink privileges, atomic file updates, process tree termination, and optional package classification—without changing core scientific semantics or importing heavy runtime engines.

## Subsystem Architecture

```
tools/platform_compat/
├── __init__.py           # Unified public API exports
├── types.py              # Enums (CapabilityStatus, DependencyStatus), dataclasses, serialization
├── paths.py              # Path normalization, cross-platform comparison, extended length (\\?\)
├── filesystem.py         # Managed tempdirs with lock retry, atomic JSON, symlink/hardlink probing
├── subprocess_ops.py     # Subprocess command construction, execution guards, process tree termination
├── dependencies.py       # Non-invasive dependency probing via importlib spec (no auto-install/download)
├── serialization.py      # Null-safe finite JSON serialization strictly rejecting NaN/Infinity
├── decisions.py          # Structured test decisions preventing silent test skips
└── audit.py              # Platform audit engine with deterministic SHA-256 checksums
```

## Core Invariants and Capabilities

### 1. Path Normalization & Comparison
- **Mixed Separators**: Canonicalizes paths containing `/`, `\`, redundant `./`, and trailing slashes.
- **Case Sensitivity**: On Windows, path comparisons respect filesystem case-insensitivity (`C:\Data` == `c:/data`). On POSIX systems, exact case matching is preserved by default.
- **Extended Length Paths**: On Windows, `to_extended_length_path()` prepends the `\\?\` (or `\\?\UNC\`) prefix to bypass the historical 260-character `MAX_PATH` limitation.
- **Unicode Support**: Directory and file operations handle multi-byte UTF-8 paths (Greek, Cyrillic, CJK) cleanly.

### 2. Filesystem Management & Atomic Writes
- **Lock-Tolerant Temporary Directories**: `safe_temp_dir()` provides guaranteed cleanup with exponential backoff retries and Windows read-only flag removal (`stat.S_IWRITE`), mitigating transient file locks from indexers and antivirus scanners.
- **Atomic JSON Writes**: `atomic_write_json()` writes to a temporary sibling file (`.tmp_<target>_<id>`) on the same filesystem volume, flushes buffers, executes `os.fsync()`, and performs an atomic replace via `os.replace()`. Target files are never left in a corrupted or truncated state.
- **Symlink & Hardlink Detection**: Non-destructively probes symlink and hardlink capabilities. On Windows, non-admin accounts without Developer Mode are classified accurately as `PERMISSION_DENIED` rather than a generic failure.

### 3. Subprocess Execution & Process Tree Cleanup
- **Process Group / Tree Termination**: `terminate_process_tree()` uses Windows `taskkill /F /T /PID` or POSIX `os.killpg()` to prevent orphaned child processes and hanging tasks on timeout.
- **Guarded Timeouts**: `run_guarded_subprocess()` captures stdout/stderr, measures execution duration, and returns a structured `ProcessResult`.

### 4. Optional Dependency Classification
- Evaluates installed optional packages (e.g. `ripser`, `gudhi`, `gtda`, `ripserplusplus`, `mne`, `scipy`) without executing heavy package initializers:
  - `AVAILABLE`: Module is importable; reports version and origin.
  - `MISSING`: Module is not installed.
  - `INCOMPATIBLE`: Binary ABI mismatch or missing system DLL.
  - `IMPORT_ERROR`: Package raised an unhandled error during import.
- **Zero Auto-Install / Zero Downloads**: Never invokes pip, package managers, or network calls.

### 5. Null-Safe Finite JSON Serialization
- Standard JSON specification does not support `NaN`, `Infinity`, or `-Infinity`.
- `dumps_finite_json()` strictly rejects non-finite values by default (`ValueError`).
- In `replace_non_finite=True` mode, non-finite values are mapped to `null` (`None`).

### 6. Structured Test Decisions (No Silent Skips)
When a test depends on platform-specific features (such as symlinks or optional packages):
- `evaluate_test_prerequisite()` returns a `PlatformTestDecision`:
  - `can_run`: Boolean indicator.
  - `status`: One of `AVAILABLE`, `UNAVAILABLE`, `UNSUPPORTED`, `PERMISSION_DENIED`, `FAILED`.
  - `reason`: Diagnostic explanation.
  - `mitigation`: Concrete actionable steps (e.g., "Enable Windows Developer Mode").
- `require_platform_capability()` marks the test with an explicit, structured skip message rather than silently dropping execution.

## Audit CLI Usage

Run a non-destructive audit of the host environment:

```bash
python scripts/run_platform_compat_audit.py --output audit.json
```

Query a specific prerequisite:

```bash
python scripts/run_platform_compat_audit.py --check-prereq symlinks
```

Verbose diagnostic output:

```bash
python scripts/run_platform_compat_audit.py --verbose
```
