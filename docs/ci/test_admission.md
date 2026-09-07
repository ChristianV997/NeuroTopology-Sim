# Test Admission Matrix and Capability Gating Specification

## 1. Overview and Scientific Motivation

In complex neurocomputational and topological workflows, test execution encounters environments with diverse optional hardware, external software toolchains, and platform constraints:
- Heavy deep learning frameworks (`torch`, CUDA acceleration)
- Accelerated topological data analysis backends (`cripser`)
- Electrophysiological file format exporters (`pybv`, `edfio`)
- External daemon virtualization (`Docker`)
- Quantum hardware endpoints (`cloud/QPU`)
- Operating system specific IPC primitives (Windows named pipes vs. POSIX domain sockets)

Previously, tests requiring optional backends risked emitting false test failures or, conversely, silently converting missing required dependencies into false passes.

The **Test Admission Matrix** provides a typed, deterministic admission and capability gating engine for `NeuroTopology-Sim`. It ensures that missing optional dependencies produce structured skips with explicit provenance, while missing required dependencies immediately block execution as reproducible errors without hiding failures.

---

## 2. Core Architecture

```
                 [Test Admission Record]
             (Category, Packages, Capabilities,
               NetworkPolicy, DockerPolicy)
                           │
                           ▼
             [Deterministic Offline Probe]
             (OS, Packages, Symlinks, Docker,
                CUDA, Cloud QPU, Solvers)
                           │
                           ▼
               [Admission Evaluator]
                           │
         ┌─────────────────┼─────────────────┐
         ▼                 ▼                 ▼
       [RUN]             [SKIP]           [BLOCK]
   All required     Optional package   Missing required
    satisfied        or OS mismatch       or policy
                                         violation
                           │
                           ▼
          [Finite JSON Conformance Report]
```

---

## 3. The 9 Admission Categories

Every test group or command belongs to one of nine standardized admission categories:

1. **`core CPU`**: Pure mathematical, algorithmic, and governance tests running on standard Python/NumPy/SciPy CPU environments without external backends.
2. **`MNE/EEG`**: Electrophysiology ingestion and windowing adapters requiring MNE and format-specific companions (`pybv`, `edfio`).
3. **`TDA`**: Topological Data Analysis pipelines relying on persistent homology solvers (`ripser`, `cripser`).
4. **`GPU`**: Hardware-accelerated tensor and vector field evolution requiring CUDA/GPU capability and PyTorch.
5. **`Docker`**: Sandboxed container isolation and verification tests requiring an active, local Docker daemon.
6. **`cloud/QPU`**: Remote quantum hardware compilers and cloud endpoints requiring valid API tokens.
7. **`Windows-only`**: Platform-specific tests exercising Win32 APIs, named pipes, or Windows file semantics.
8. **`POSIX-only`**: Platform-specific tests exercising Unix domain sockets, fork semantics, or POSIX signals.
9. **`optional external solver`**: Mathematical benchmarks utilizing optional mathematical optimization packages (CVXPY, Z3, GLPK).

---

## 4. Allowed Decisions and Rules

| Decision | State | Trigger Condition |
| :--- | :--- | :--- |
| `RUN` | Runnable | All required dependencies, optional packages, and platform capabilities are fully satisfied. |
| `SKIP_OPTIONAL_DEPENDENCY` | Skipped | An optional package or acceleration capability is absent, and the test's `action_when_unavailable` is `"skip"`. |
| `SKIP_UNSUPPORTED_PLATFORM` | Skipped | The test requires an OS (e.g. POSIX) or platform primitive not supported by the host OS. |
| `BLOCK_MISSING_REQUIRED_DEPENDENCY` | Blocked | A strictly required package listed in `required_packages` is missing from the environment. |
| `BLOCK_NETWORK_POLICY` | Blocked | The test requires live network connectivity, violating repository offline policy. |
| `BLOCK_DOCKER_UNAVAILABLE` | Blocked | A test with `docker_policy: required` is run on a host lacking an active Docker daemon. |
| `BLOCK_CLOUD_UNAVAILABLE` | Blocked | Cloud/QPU hardware is required (`action_when_unavailable: block`) but credentials are not configured. |
| `INVALID_CONFIGURATION` | Blocked | The admission record contains an unrecognized category, invalid policy, or unknown capability. |

### Core Invariants
- **No False Failures**: Missing optional dependencies never surface as broken unit tests.
- **No False Passes**: Missing required dependencies never surface as green passes.
- **No Silent Skips**: Every skipped test includes an explicit human-readable reason and capability diagnostic record.
- **Strictly Offline**: Probing performs no socket calls, external downloads, or background installations.
- **Null-Safe JSON**: Non-finite numbers or unmeasured attributes serialize strictly as `null` (`allow_nan=False`).
- **No Scientific Inference on Skips**: Scientific claims or falsification gates cannot be satisfied by skipped tests.

---

## 5. CLI Usage

```bash
# Display summary table of all test groups
python scripts/validate_test_admission.py --format summary

# Output strict null-safe JSON report to file
python scripts/validate_test_admission.py --format json --output artifacts/test_admission_report.json

# Enforce strict gating in CI (exit code 1 if any BLOCK or INVALID decision occurs)
python scripts/validate_test_admission.py --strict

# Evaluate a specific test group
python scripts/validate_test_admission.py --target-group mne_streaming_eeg
```

---

## 6. Configuration Schema (`configs/test_admission/admission_matrix.yaml`)

```yaml
schema: NeuroTopologySim.TestAdmissionMatrixConfig.v1
admission_records:
  - test_group: core_governance
    category: "core CPU"
    required_packages: [pytest, pyyaml]
    optional_packages: []
    required_platform_capabilities: []
    network_policy: forbidden
    docker_policy: not_required
    expected_memory_class: low
    expected_timeout_class: short
    scientific_relevance: core_gate
    action_when_unavailable: block
    target_path: governance/validate.py
```
