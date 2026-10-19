# Synthetic Pipeline Replay and Structural Conformance Harness

## 1. Executive Summary and Epistemic Boundaries

> **Engineering Disclaimer**  
> *A deterministic structural replay is an integration and conformance verification, not scientific validation.*  
> This harness verifies that synthetic pipeline stages on `origin/main` pass data artifacts across inter-stage boundaries without silent coercion of shapes, channel ordering, units, timing, or metadata. Structural compatibility does not constitute evidence of biological validity, statistical significance, consciousness detection, or research claim promotion. The harness reuses established schemas and status vocabularies and does not emit `VALIDATED` or create secondary claim/evidence state machines.

The `tools.synthetic_pipeline_replay` package and `tests.integration.synthetic_pipeline_replay` test suite establish an offline, deterministic integration verification lane across four sequential pipeline stages:
1. **Synthetic Signal Generation**: Produces multi-channel raw signals adhering to the `SignalChunk` contract (`shared.interop.contracts`).
2. **Preprocessing & Windowing**: Extracts bounded analysis windows with strict timestamp progression and channel stability.
3. **Canonical Feature Extraction**: Constructs versioned `CanonicalFeatureRecord` and `CanonicalFeatureBundle` containers (`shared.feature_contracts.models`) covering one-sided Power Spectral Density (PSD) with interior-bin doubling and Pairwise Functional Connectivity (PLV).
4. **Topological Summary**: Derives persistent homology persistence-interval counts ($H_0, H_1$) and optional thresholded Betti numbers $\beta_k(\epsilon)$ from pairwise connectivity via `ripser`.

---

## 2. Tested Pipeline Stages on `origin/main`

```
┌─────────────────────────────────┐
│ Stage 1: SignalGenerationStage  │ (schema: NeuroTopologySim.SignalChunk.v1)
└─────────────────────────────────┘
                 │
                 ▼ [Boundary 1: b1_signal_to_preprocessing]
┌─────────────────────────────────┐
│ Stage 2: PreprocessingWindow    │ (schema: NeuroTopologySim.PreprocessedWindow.v1)
└─────────────────────────────────┘
                 │
                 ▼ [Boundary 2: b2_preprocessing_to_feature_extraction]
┌─────────────────────────────────┐
│ Stage 3: FeatureExtractionStage │ (schema: NeuroTopologySim.CanonicalFeatureBundle.v1)
└─────────────────────────────────┘
                 │
                 ▼ [Boundary 3: b3_feature_extraction_to_topology]
┌─────────────────────────────────┐
│ Stage 4: TopologySummaryStage   │ (schema: NeuroTopologySim.TopologicalSummary.v1)
└─────────────────────────────────┘
```

### Stage Details

| Stage Identifier | Class | Input Contract | Output Artifact & Schema | Core Invariants Checked |
| :--- | :--- | :--- | :--- | :--- |
| `stage_1_signal_generation` | `SignalGenerationStage` | Local parameters (channels, $f_s$, duration, seed) | `SignalChunk`<br>`NeuroTopologySim.SignalChunk.v1` | Multi-channel 2D shape `(n_ch, n_samples)`, strictly increasing timestamps, physical calibration units (`uV`), 3D montage coordinates. |
| `stage_2_preprocessing` | `PreprocessingWindowStage` | `SignalChunk` | `PreprocessedWindow`<br>`NeuroTopologySim.PreprocessedWindow.v1` | Bounded window extraction ($T = 1.0\,\text{s}$), channel ordering stability, sampling rate preservation, timestamp continuity. |
| `stage_3_feature_extraction` | `FeatureExtractionStage` | `PreprocessedWindow` | `CanonicalFeatureBundle`<br>`NeuroTopologySim.CanonicalFeatureBundle.v1` | Explicit feature families (`psd`, `pairwise_fc`), one-sided spectral density with interior-bin doubling (`uV^2/Hz`, conserving Parseval energy), dimensionless PLV. |
| `stage_4_topology_summary` | `TopologySummaryStage` | `CanonicalFeatureBundle` | `TopologicalSummary`<br>`NeuroTopologySim.TopologicalSummary.v1` | Symmetric non-negative distance matrix, persistent homology interval extraction, finite persistence-interval counts ($H_0, H_1$), and thresholded Betti numbers when filtration threshold is declared. |

---

## 3. Boundary Conformance Rules (Zero Silent Coercion)

The checker enforces strict structural conformance at each inter-stage boundary. Implicit defaults, silent reshapes, and silent channel reorderings are forbidden:

1. **Shape Conformance**:
   - The observed tensor shape must match the expected shape exactly: `list(expected_shape) == list(observed_shape)`.
   - Transpositions (e.g. `(samples, channels)` vs `(channels, samples)`) are treated as structural failures (`incompatible`), never coerced silently.
2. **Channel & Node Ordering**:
   - Channel names must match in identical sequence: `["Fp1", "Fp2", "C3", "C4"]` $\neq$ `["Fp2", "Fp1", "C3", "C4"]`.
   - Permuting or sorting channels behind the caller's back corrupts spatial derivative metrics and adjacency indices; any sequence difference fails as `incompatible`.
3. **Physical & Calibration Units**:
   - Physical units must match declared expectations (e.g. `uV` $\neq$ `V`).
   - Mismatched units fail as `incompatible`. Missing or `"unknown"` units yield `missing_required_field`.
4. **Timing, Sample Rate & Timestamps**:
   - Sampling rate $f_s$ must be finite, strictly positive ($f_s > 0$), and match expected rates.
   - When the timing contract specifies `require_timestamps=True` (e.g. for continuous time-series stages), timestamps must be present. Absent timestamps fail with `missing_required_field`.
   - Present timestamps are validated against malformations: must be 1D, strictly monotonic ($\Delta t > 0$), finite (no NaN/Inf), count-matched to sample count, and step-consistent with $1/f_s$. Any malformation fails closed as `incompatible`.
5. **Sensor Coordinates**:
   - When 3D montage coordinates are declared, coordinate count must match channel count: `coords.shape[0] == n_channels`.
   - Mismatched coordinate counts (e.g. 2 coordinate rows for 4 channels) fail as `incompatible`.
6. **Finite Value Rule & Serializer Contract**:
   - Payload arrays and metadata must contain only finite numbers. Any occurrence of $\text{NaN}$, $+\infty$, or $-\infty$ fails closed as `incompatible`.
   - The serializer function `safe_json_dict` strictly rejects non-finite floats fail-closed by raising `ValueError`. Silent conversion to `null` or zero-imputation is strictly prohibited.
7. **One-Sided PSD Scaling & Parseval Energy Conservation**:
   - For real-valued signals $x[n]$ sampled at $f_s$ with $N$ samples, discrete periodogram values are computed via `np.fft.rfft`.
   - DC bin ($k = 0$) and Nyquist bin ($k = N/2$ for even $N$) have no negative frequency conjugates and remain unscaled.
   - All interior positive-frequency bins ($0 < k < N/2$) are scaled by $2.0$.
   - Conformance requires exact conservation of discrete Parseval power: $\sum_{k=0}^{M-1} S_1[k] \Delta f = \frac{1}{N} \sum_{n=0}^{N-1} x[n]^2$ across both even and odd sample lengths.
8. **Persistence Intervals vs. Thresholded Betti Numbers**:
   - Diagram lengths `len(dgm0)` and `len(dgm1)` represent total persistence intervals across the entire filtration, not Betti numbers.
   - These counts are explicitly designated `persistence_interval_count_h0` and `persistence_interval_count_h1`.
   - Betti numbers $\beta_k(\epsilon) = \#\{(b, d) \mid b \le \epsilon < d\}$ are computed and reported only when an explicit `filtration_threshold` $\epsilon$ is declared; otherwise, Betti status is declared `not_evaluated_no_declared_threshold`.
9. **Schema & Versioning**:
   - Schema version strings must match active major contracts on `origin/main`.
   - Deprecated or stale schemas (e.g. containing `v0_legacy`) fail as `incompatible`.
10. **Optional Dependency Availability**:
    - Stages requiring optional external packages (e.g. `ripser`, `mne`) explicitly probe availability.
    - If an optional dependency is missing, the boundary yields `not_comparable` and downstream execution safely halts (`blocked`), without simulating or faking calculations.

---

## 4. Status Vocabulary

In accordance with repository governance, the harness reuses existing status vocabularies and does not invent speculative claim tiers:

### Per-Boundary Status (`BoundaryStatus`)
- **`compatible`**: All expected shapes, channel sequences, units, sample rates, schemas, and finite payload values match.
- **`incompatible`**: One or more structural invariants violated (e.g. reordered channels, mismatched units, shape error, malformed timestamps, non-finite values).
- **`missing_required_field`**: Mandatory metadata (e.g. `sampling_rate_hz`, units, timestamps when required) is absent or null.
- **`not_comparable`**: Required optional backend dependency is not installed.

### Overall Replay Status (`ReplayStatus`)
- **`compatible`**: All boundaries evaluated as `compatible`.
- **`incompatible`**: One or more boundaries evaluated as `incompatible`.
- **`inconclusive`**: Mandatory fields missing; replay cannot be evaluated reliably.
- **`blocked`**: Execution halted due to unavailable optional dependency.

---

## 5. Negative Test Coverage Matrix

The test suite in `tests/integration/synthetic_pipeline_replay/` verifies the following conditions (20 passed tests):

| Perturbation Condition | Injected Defect | Target Boundary | Expected Boundary Status | Expected Overall Status | Asserted Diagnostic / Mismatch Pattern |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Reordered Channels** | Swapped `["Fp2", "Fp1", "C3", "C4"]` | Boundary 1 | `incompatible` | `incompatible` | `"permuting channels is forbidden"` |
| **Mismatched Units** | Observed unit `"V"` instead of `"uV"` | Boundary 1 | `incompatible` | `incompatible` | `"Unit mismatch: expected 'uV', observed 'V'"` |
| **Missing Time Metadata** | `sampling_rate_hz = None` | Boundary 1 | `missing_required_field` | `inconclusive` | `"sampling_rate_hz"` in `missing_fields` |
| **Absent Timestamps** | `timestamps = None` (required) | Boundary 1 | `missing_required_field` | `inconclusive` | `"timestamps"` in `missing_fields`, halts downstream |
| **Non-Monotonic Timestamps** | Step $\Delta t \le 0$ in timestamps | Boundary 1 | `incompatible` | `incompatible` | `"not strictly monotonically increasing"` |
| **Non-Finite Timestamps** | Injected $\text{NaN}$ in timestamps | Boundary 1 | `incompatible` | `incompatible` | `"contain non-finite values"` |
| **Wrong Timestamp Shape** | 2D array instead of 1D | Boundary 1 | `incompatible` | `incompatible` | `"must be 1D"` |
| **Timestamp Count Mismatch** | 450 timestamps for 500 samples | Boundary 1 | `incompatible` | `incompatible` | `"timestamp count (450) does not match sample count (500)"` |
| **Changed Feature Dimension** | Shape `[4, 300]` instead of `[4, 250]` | Boundary 2 | `incompatible` | `incompatible` | `"Shape mismatch"` |
| **Non-Finite Payload Values** | Injected $\text{NaN}$ and $+\infty$ | Boundary 1 | `incompatible` | `incompatible` | `"contains non-finite values"` |
| **Serializer Non-Finite Rejection**| `safe_json_dict` on NaN/Inf | Serializer | `ValueError` raised | N/A | `"Non-finite float value"` fail-closed |
| **Stale Schema Version** | Version `v0_legacy_deprecated` | Boundary 1 | `incompatible` | `incompatible` | `"Stale/deprecated schema version"` |
| **Unavailable Dependency** | `ripser` simulated unavailable | Boundary 3 | `not_comparable` | `blocked` | `"Required optional dependency 'ripser' is not available"` |
| **Incompatible Stages** | Passed `directed_hypergraph` | Boundary 3 | `incompatible` | `incompatible` | `"Incompatible feature family"` |
| **Contradictory Coordinates** | 2 coordinate rows for 4 channels | Boundary 1 | `incompatible` | `incompatible` | `"Coordinate channel count (2) does not match"` |
| **Parseval Energy Scaling** | One-sided PSD interior doubling | Stage 3 | `compatible` | `compatible` | Exact Parseval equality for even & odd $N$ ($< 10^{-10}$) |
| **Persistence Intervals vs Betti** | Thresholded vs unthesholded | Stage 4 | `compatible` | `compatible` | `betti_number_status` declared accurately |

---

## 6. Upstream Interfaces and Optional Software Audit

The replay harness exercises existing stable interfaces on `origin/main` and records upstream dependency versions and licenses:

| Package | Role in Pipeline Replay | License | Version Verified | Fallback / Isolation Behavior |
| :--- | :--- | :--- | :--- | :--- |
| **NumPy** | Array storage, FFT periodogram, numeric verification | BSD-3-Clause | 2.4.6 | Core runtime dependency; required. |
| **SciPy** | Analytic phase extraction via Hilbert transform | BSD-3-Clause | 1.15.2 | Standard scientific library; required. |
| **scikit-learn** | Downstream classifier and manifold reference | BSD-3-Clause | 1.6.1 | Optional; evaluated only when imported. |
| **Ripser** | Persistent homology persistence intervals & Betti numbers | MIT | 0.6.15 | Optional; if unavailable, boundary yields `not_comparable` and Stage 4 halts (`blocked`). |
| **MNE-Python** | Electrophysiology container reference | BSD-3-Clause | 1.9.0 | Optional; contract wrappers avoid direct hard imports. |

---

## 7. CLI and Programmatic Usage

### Command Line Execution
```powershell
# Run the synthetic pipeline replay checker and emit JSON report
python -m tools.synthetic_pipeline_replay.runner --output outputs/synthetic_pipeline_replay/replay_report.json

# Custom configuration (channels, sampling frequency, duration, seed)
python -m tools.synthetic_pipeline_replay.runner --sfreq 500.0 --duration 4.0 --seed 101 --output outputs/replay_report.json
```

---

## 8. Hosted Candidate Discovery Mapping Specification

For the workflow owner maintaining `.github/workflows/round6_experimental_tests.py`, the exact specification to map `synthetic_pipeline_replay` into `COMPONENTS` is provided below:

```python
    "synthetic_pipeline_replay": {
        "triggers": (
            "tools/synthetic_pipeline_replay/",
            "tests/integration/synthetic_pipeline_replay/",
            "docs/integration/synthetic_pipeline_replay.md",
        ),
        "implementation_any": (
            "tools/synthetic_pipeline_replay/checker.py",
            "tools/synthetic_pipeline_replay/contracts.py",
            "tools/synthetic_pipeline_replay/runner.py",
            "tools/synthetic_pipeline_replay/stages.py",
        ),
        "tests": (
            "tests/integration/synthetic_pipeline_replay/test_replay_harness.py",
            "tests/integration/synthetic_pipeline_replay/test_replay_negative_cases.py",
        ),
        "candidate_pairs": (
            {"implementation": "tools/synthetic_pipeline_replay/checker.py", "test": "tests/integration/synthetic_pipeline_replay/test_replay_negative_cases.py"},
            {"implementation": "tools/synthetic_pipeline_replay/runner.py", "test": "tests/integration/synthetic_pipeline_replay/test_replay_harness.py"},
            {"implementation": "tools/synthetic_pipeline_replay/stages.py", "test": "tests/integration/synthetic_pipeline_replay/test_replay_harness.py"},
            {"implementation": "tools/synthetic_pipeline_replay/contracts.py", "test": "tests/integration/synthetic_pipeline_replay/test_replay_negative_cases.py"},
        ),
        "implementation_roots": ("tools/synthetic_pipeline_replay/",),
        "test_roots": ("tests/integration/synthetic_pipeline_replay/",),
    },
```
