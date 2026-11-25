# Test Execution Contract & Dependency Profile Architecture

Status: **active contract.** This document specifies the resource-bounded, dependency-aware, and reproducible test execution contract for NeuroTopology-Sim.

---

## 1. Motivation and Core Invariants

Scientific Python workflows (MNE-Python, PyTorch, SciPy, GUDHI, QuTiP) rely heavily on compiled C/C++, Fortran, and CUDA libraries that allocate memory directly on native heaps outside Python's garbage-collected runtime. Running a monolithic `pytest tests/` process causes these native allocations to accumulate, degrading memory stability, triggering allocator fragmentation, and occasionally leading to unexplained process crashes or unkillable worker threads.

To provide bounded, reproducible, and transparent validation across diverse environments (from minimal laptop developer setups to high-throughput CI matrices), this contract enforces six invariants:

1. **Never turn real failures into silent skips**: If a test fails due to algorithmic regressions or logic errors, it must fail loudly and propagate its non-zero exit code.
2. **Explicit dependency reporting**: Missing optional dependencies must be classified and logged with explicit diagnostic notices, rather than silently omitting test coverage.
3. **Hard timeout termination**: Any process that hangs or exceeds its allotted budget must be forcefully terminated along with all spawned child processes.
4. **Strict offline boundary**: Standard test suites and CI jobs run completely offline. No automated HTTP requests to OpenNeuro, AWS, PDB, Zenodo, or HuggingFace are permitted.
5. **No cloud or real-data execution in standard CI**: CI executes mock fixtures and synthetic benchmarks only. Real-data contract activation requires human operator staging and explicit authorization.
6. **Preservation of K > 100 semantics**: Hypothesis confirmation requires Bayes factor $K > 100$; marginal, missing, or corrupt results fail closed to `NOT_SUPPORTED` or `INCONCLUSIVE`.

---

## 2. Dependency Profiles Specification

Dependencies are modularized into seven explicit profiles, allowing developers and CI runners to install only what is necessary for a given validation scope.

### Profile 1: Base Core (`requirements-base.txt`)
- **Purpose**: Minimal numerical, topological, and contract infrastructure.
- **Packages**: `numpy`, `scipy`, `pandas`, `matplotlib`, `scikit-learn`, `pyyaml`, `joblib`, `fastapi`, `httpx`, `h5py`, `networkx`, `statsmodels`, `persim`, `ripser`, `pytest`, `pytest-timeout`.
- **Optional Status**: **Mandatory**. Required for all repository operations.
- **Affected Tests**: Core schemas, `RunRecordV1`, persistent homology primitives (`core/topology.py`), benchmark registry verification, and governance gates.
- **Platform Constraints**: Universal wheel support (Linux, macOS, Windows).

### Profile 2: EEG & Electrophysiology (`requirements-eeg.txt`)
- **Purpose**: Electrophysiology ingestion (EDF, BDF, BrainVision), MNE-BIDS formatting, microstate segmentation, aperiodic spectral decomposition (1/f), and nonlinear fractal complexity (DFA, MFDFA, Permutation Entropy).
- **Packages**: `mne`, `mne-bids`, `edfio`, `eegdash`, `mne-connectivity`, `pycrostates`, `autoreject`, `mne-icalabel`, `antropy`, `specparam`, `MFDFA`, `fbm`.
- **Optional Status**: Optional. Required for real-EEG pipelines (DS005620, DS001787, DS003969) and Level M/T feature extraction.
- **Affected Tests**: `tests/test_connectivity_topology.py`, `tests/btc_icft/test_dfa_mfdfa_features.py`, `tests/btc_icft/test_eeg_mne_adapter.py`, `tests/btc_icft/test_eeg_signal_blocks.py`, `tests/test_preprocessing_artifact_rejection.py`.
- **Platform Constraints**: Python 3.10-3.12 recommended.

### Profile 3: NWB & DANDI Archive (`requirements-nwb.txt`)
- **Purpose**: Neurodata Without Borders object modeling and lazy HTTP streaming over HDF5 from DANDI public S3 (e.g. mouse anesthesia dataset `dandiset 000458`).
- **Packages**: `pynwb`, `remfile`, `hdmf`.
- **Optional Status**: Optional.
- **Affected Tests**: `tests/test_dandi_nwb_ingest.py`, `tests/test_nwb_adapters.py`.
- **Platform Constraints**: Universal pure Python / HDF5 wheels.

### Profile 4: Live Acquisition & Cloud Sync (`requirements-live.txt`)
- **Purpose**: Cloud dataset streaming (OpenNeuro AWS S3 sync), live sensor hardware interfacing, and remote bucket synchronization.
- **Packages**: `boto3`, `botocore`, `awscli`.
- **Optional Status**: Optional. Strictly forbidden from executing in offline CI.
- **Affected Tests**: `tests/test_cloud_payload_and_cross_validation.py`, `tests/tools/test_stream_process_openneuro.py`.
- **Platform Constraints**: Standard Python packages.

### Profile 5: Machine Learning & Graph Neural Networks (`requirements-ml.txt`)
- **Purpose**: Graph Neural Network (GNN) cross-modal embedding fusion, topological dimensionality reduction via Kepler Mapper, and training telemetry.
- **Packages**: `torch`, `torch-geometric`, `pytorch-lightning`, `tensorboard`, `wandb`, `kmapper`.
- **Optional Status**: Optional. Heavy native memory footprint.
- **Affected Tests**: `tests/test_dual_engine.py`, `tests/test_mapper_graph.py`, `tests/test_cross_modal_fusion.py`.
- **Platform Constraints**: Native C++/CUDA binaries; requires fresh process isolation to release CUDA/CPU context.

### Profile 6: Research Index & Brain Modeling (`requirements-research.txt`)
- **Purpose**: Whole-brain neural mass simulation (Wilson-Cowan via neurolib), cortical surface registration (TemplateFlow), scale-resolved cubical persistence (GUDHI, cripser), spatial null spin tests (neuromaps), fMRI neuroimaging (NiBabel, Nilearn), and active inference controllers (pymdp).
- **Packages**: `nibabel`, `nilearn`, `templateflow`, `neurolib`, `cripser`, `neuromaps`, `the_well`, `gudhi`, `inferactively-pymdp`.
- **Optional Status**: Optional.
- **Affected Tests**: `tests/test_run_neurolib.py`, `tests/test_fmri_tda_pipeline.py`, `tests/test_spatial_nulls.py`, `tests/test_speculative_boundary.py`.
- **Platform Constraints**: GUDHI requires compiled C++ extensions; TemplateFlow requires offline cache.

### Profile 7: Open Quantum Exact Dynamics (`requirements-quantum.txt`)
- **Purpose**: Non-Hermitian Hamiltonian and exceptional-point cross-validation (QuTiP), stochastic Langevin lattice PDE solving (py-pde), and quantum circuit mapping (Amazon Braket SDK, OQuPy).
- **Packages**: `py-pde`, `qutip`, `ipython<9`, `amazon-braket-sdk`, `oqupy`, `biopython`.
- **Optional Status**: Optional.
- **Affected Tests**: `tests/test_cloud_payload_and_cross_validation.py`, `tests/exact_dynamics/test_qpu_cloud_runner.py`.
- **Platform Constraints**: Python 3.10-3.12 (QuTiP 5.3 requires ipython<9).

---

## 3. Hardened Isolated Test Runner (`scripts/run_tests_isolated.py`)

The isolated test runner executes the test suite in fresh, bounded subprocess batches:

```bash
python scripts/run_tests_isolated.py --batch-size 8 --timeout-s 120 --report outputs/test_report.json
```

### Key Technical Mechanisms

1. **Deterministic Lexicographical Ordering**:
   File discovery resolves relative POSIX paths (`path.relative_to(root).as_posix()`) and sorts them alphabetically. Batch partitions are identical regardless of OS filesystem iteration order.

2. **Hard Process-Tree Termination**:
   When a batch exceeds `timeout_s`:
   - On Windows: Invokes `taskkill /F /T /PID <pid>` to terminate the worker and all child processes.
   - On POSIX: Sends `signal.SIGKILL` to the process group.
   - Propagates exit code `124` and records `"status": "timeout"`.

3. **Resource Caps per Subprocess**:
   Every worker environment explicitly sets:
   ```bash
   OMP_NUM_THREADS=1
   OPENBLAS_NUM_THREADS=1
   MKL_NUM_THREADS=1
   NUMEXPR_NUM_THREADS=1
   VECLIB_MAXIMUM_THREADS=1
   ```

4. **Temporary Directory Isolation**:
   Each batch receives a dedicated temporary directory passed via `--basetemp`, isolated from the git working tree and cleaned up after execution.

5. **Structured Telemetry Reporting**:
   When `--report <path>` is passed, writes a comprehensive JSON document:
   ```json
   {
     "summary": {
       "total_files": 9,
       "total_batches": 2,
       "passed_batches": 2,
       "failed_batches": 0,
       "timeout_batches": 0,
       "duration_s": 45.2,
       "overall_exit_code": 0
     },
     "batches": [
       {
         "batch_index": 1,
         "files": ["tests/test_run_record.py"],
         "status": "passed",
         "exit_code": 0,
         "duration_s": 4.8,
         "peak_memory_mb": 85.2,
         "failures": []
       }
     ]
   }
   ```

---

## 4. Test Markers (`pytest.ini`)

All custom markers are explicitly registered in `pytest.ini` to prevent unknown-marker warnings and enable targeted execution:

| Marker | Description | Typical Use Case |
|:---|:---|:---|
| `slow` | Tests taking > 5 seconds. | Exclude during rapid local iteration (`-m "not slow"`). |
| `native` | Involves C/C++/Fortran/Rust native code. | Flagged for memory audits. |
| `memory_heavy` | Heap consumption > 500 MB. | Isolated to dedicated single-batch runs. |
| `serial` | Cannot run concurrently; mutates state. | Run serially. |
| `network` | Requires external network connection. | Disabled by default; blocked by conftest guard. |
| `requires_mne` | Requires MNE-Python ecosystem. | Filtered when running in base profile. |
| `requires_torch` | Requires PyTorch / PyG. | Filtered when running on non-ML runners. |
| `requires_nwb` | Requires PyNWB / DANDI. | Filtered when running without NWB. |
| `requires_live_hardware` | Requires physical sensor or probe. | Skipped in standard automated CI. |

---

## 5. Deterministic Test Controls (`conftest.py`)

- **Automatic PRNG Seeding (`deterministic_seed` fixture)**:
  Every test automatically initializes `random.seed(42)` and `np.random.seed(42)` (and `torch.manual_seed(42)` if PyTorch is loaded). A test can customize its seed via `@pytest.mark.seed(1234)`.
- **Outbound Network Interception (`block_unauthorized_network` fixture)**:
  Monkeypatches `socket.socket.connect`. Any unexpected network connection to non-loopback hosts raises a fatal `RuntimeError`, enforcing strict offline test discipline.
- **Output Isolation (`isolated_test_dir` fixture)**:
  Provides a fresh temporary directory per test via `NEUROTOPOLOGY_TEST_SCRATCH`, eliminating cross-test race conditions in `outputs/` or `artifacts/`.
- **Garbage & Native Buffer Reclamation (`collect_numpy_garbage` fixture)**:
  Executes `gc.collect()` after every test to release cyclic references and free native buffers.

---

## 6. Makefile & make.cmd Target Reference

| Make Target | Command | Purpose |
|:---|:---|:---|
| `make test-runner` | `python -m pytest tests/runner/ -v` | Unit tests for the isolated runner itself. |
| `make test-core-isolated` | `python scripts/run_tests_isolated.py ...` | Runs base core test suite in isolated batches. |
| `make test-eeg-isolated` | `python scripts/run_tests_isolated.py ...` | Runs EEG profile test suite. |
| `make test-ml-isolated` | `python scripts/run_tests_isolated.py ...` | Runs ML profile test suite. |
| `make dependency-inventory` | Audits requirement profile declarations. | Displays count of packages per profile. |
| `make validate-governance` | `python -m governance.validate` | Validates YAML specs and contracts. |
| `make smoke` | `python main.py --mode synthetic` | Offline synthetic pipeline smoke test. |

---

## 7. CI Pipeline Topology

CI is partitioned into distinct, dependency-bounded jobs in `.github/workflows/ci.yml`:

```text
[ Push / PR Event ]
        │
        ├──> Job 1: governance-validate (Python 3.12)
        │
        ├──> Job 2: dependency-inventory (Audits profile manifests)
        │
        └──> Job 3: fast-contracts (Runner unit tests + core contracts)
                 │
                 ├──> Job 4: isolated-core-suite (Matrix: Python 3.10, 3.11, 3.12)
                 │         - requirements-base.txt only
                 │         - run_tests_isolated.py (batch-size 8, timeout 120s)
                 │         - Smoke test synthetic mode
                 │         - Artifact: core-test-report.json
                 │
                 ├──> Job 5: optional-eeg-suite (Python 3.11)
                 │         - requirements-eeg.txt
                 │         - run_tests_isolated.py on EEG tests
                 │         - Artifact: eeg-test-report.json
                 │
                 └──> Job 6: optional-ml-suite (Python 3.11)
                           - requirements-ml.txt
                           - run_tests_isolated.py on ML tests
                           - Artifact: ml-test-report.json
```
