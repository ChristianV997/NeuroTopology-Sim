# Synthetic Pipeline Replay and Structural Conformance Harness

## 1. Executive Summary and Epistemic Boundaries

> **Engineering Disclaimer**  
> *A deterministic structural replay is an integration and conformance verification, not scientific validation.*  
> This harness verifies that synthetic pipeline stages on `origin/main` pass data artifacts across inter-stage boundaries without silent coercion of shapes, channel ordering, units, timing, or metadata. Structural compatibility does not constitute evidence of biological validity, statistical significance, consciousness detection, or research claim promotion. The harness reuses established schemas and status vocabularies and does not emit `VALIDATED` or create secondary claim/evidence state machines.

The `tools.synthetic_pipeline_replay` package and `tests.integration.synthetic_pipeline_replay` test suite establish an offline, deterministic integration verification lane across four sequential pipeline stages:
1. **Synthetic Signal Generation**: Produces multi-channel raw signals adhering to the `SignalChunk` contract (`shared.interop.contracts`).
2. **Preprocessing & Windowing**: Extracts bounded analysis windows with strict timestamp progression and channel stability.
3. **Canonical Feature Extraction**: Constructs versioned `CanonicalFeatureRecord` and `CanonicalFeatureBundle` containers (`shared.feature_contracts.models`) covering Power Spectral Density (PSD) and Pairwise Functional Connectivity (PLV).
4. **Topological Summary**: Derives persistent homology Betti numbers ($\beta_0, \beta_1$) and filtration summaries from pairwise connectivity via `ripser`.

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
| `stage_2_preprocessing` | `PreprocessingWindowStage` | `SignalChunk` | `PreprocessedWindow`<br>`NeuroTopologySim.PreprocessedWindow.v1` | Bounded window extraction ($T = 1.0\,\text{s}$), channel ordering stability, sampling rate preservation. |
| `stage_3_feature_extraction` | `FeatureExtractionStage` | `PreprocessedWindow` | `CanonicalFeatureBundle`<br>`NeuroTopologySim.CanonicalFeatureBundle.v1` | Explicit feature families (`psd`, `pairwise_fc`), derived spectral units (`uV^2/Hz`, `dimensionless`), channel node identity preservation. |
| `stage_4_topology_summary` | `TopologySummaryStage` | `CanonicalFeatureBundle` | `TopologicalSummary`<br>`NeuroTopologySim.TopologicalSummary.v1` | Symmetric non-negative distance matrix, persistent homology interval extraction, finite Betti counts ($\beta_0, \beta_1$). |

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
4. **Timing & Sample Rate**:
   - Sampling rate $f_s$ must be finite, strictly positive ($f_s > 0$), and match expected rates.
   - Timestamps must be 1D, finite, and strictly monotonically increasing: $\Delta t > 0$.
   - Missing sampling rate yields `missing_required_field`.
5. **Sensor Coordinates**:
   - When 3D montage coordinates are declared, coordinate count must match channel count: `coords.shape[0] == n_channels`.
   - Mismatched coordinate counts (e.g. 2 coordinate rows for 4 channels) fail as `incompatible`.
6. **Finite Value Rule**:
   - Payload arrays must contain only finite numbers. Any occurrence of $\text{NaN}$, $+\infty$, or $-\infty$ fails closed as `incompatible`.
   - Silent zero-imputation is strictly forbidden.
7. **Schema & Versioning**:
   - Schema version strings must match active major contracts on `origin/main`.
   - Deprecated or stale schemas (e.g. containing `v0_legacy`) fail as `incompatible`.
8. **Optional Dependency Availability**:
   - Stages requiring optional external packages (e.g. `ripser`, `mne`) explicitly probe availability.
   - If an optional dependency is missing, the boundary yields `not_comparable` and downstream execution safely halts (`blocked`), without simulating or faking calculations.

---

## 4. Status Vocabulary

In accordance with repository governance, the harness reuses existing status vocabularies and does not invent speculative claim tiers:

### Per-Boundary Status (`BoundaryStatus`)
- **`compatible`**: All expected shapes, channel sequences, units, sample rates, schemas, and finite payload values match.
- **`incompatible`**: One or more structural invariants violated (e.g. reordered channels, mismatched units, shape error, non-finite values).
- **`missing_required_field`**: Mandatory metadata (e.g. `sampling_rate_hz`, units) is absent or null.
- **`not_comparable`**: Required optional backend dependency is not installed.

### Overall Replay Status (`ReplayStatus`)
- **`compatible`**: All boundaries evaluated as `compatible`.
- **`incompatible`**: One or more boundaries evaluated as `incompatible`.
- **`inconclusive`**: Mandatory fields missing; replay cannot be evaluated reliably.
- **`blocked`**: Execution halted due to unavailable optional dependency.

---

## 5. Negative Test Coverage Matrix

The test suite in `tests/integration/synthetic_pipeline_replay/test_replay_negative_cases.py` verifies the following negative conditions:

| Perturbation Condition | Injected Defect | Target Boundary | Expected Boundary Status | Expected Overall Status | Asserted Diagnostic / Mismatch Pattern |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Reordered Channels** | Swapped `["Fp2", "Fp1", "C3", "C4"]` | Boundary 1 | `incompatible` | `incompatible` | `"permuting channels is forbidden"` |
| **Mismatched Units** | Observed unit `"V"` instead of `"uV"` | Boundary 1 | `incompatible` | `incompatible` | `"Unit mismatch: expected 'uV', observed 'V'"` |
| **Missing Time Metadata** | `sampling_rate_hz = None` | Boundary 1 | `missing_required_field` | `inconclusive` | `"sampling_rate_hz"` in `missing_fields` |
| **Changed Feature Dimension** | Shape `[4, 300]` instead of `[4, 250]` | Boundary 2 | `incompatible` | `incompatible` | `"Shape mismatch"` |
| **Non-Finite Values** | Injected $\text{NaN}$ and $+\infty$ | Boundary 1 | `incompatible` | `incompatible` | `"contains non-finite values"` |
| **Stale Schema Version** | Version `NeuroTopologySim.SignalChunk.v0_legacy_deprecated` | Boundary 1 | `incompatible` | `incompatible` | `"Stale/deprecated schema version"` |
| **Unavailable Dependency** | `ripser` simulated unavailable | Boundary 3 | `not_comparable` | `blocked` | `"Required optional dependency 'ripser' is not available"` |
| **Incompatible Stages** | Passed `directed_hypergraph` instead of `pairwise_fc` | Boundary 3 | `incompatible` | `incompatible` | `"Incompatible feature family"` |
| **Contradictory Coordinates** | 2 coordinate rows for 4 channels | Boundary 1 | `incompatible` | `incompatible` | `"Coordinate channel count (2) does not match"` |

---

## 6. Upstream Interfaces and Optional Software Audit

The replay harness exercises existing stable interfaces on `origin/main` and records upstream dependency versions and licenses:

| Package | Role in Pipeline Replay | License | Version Verified | Fallback / Isolation Behavior |
| :--- | :--- | :--- | :--- | :--- |
| **NumPy** | Array storage, FFT periodogram, numeric verification | BSD-3-Clause | 2.4.6 | Core runtime dependency; required. |
| **SciPy** | Analytic phase extraction via Hilbert transform | BSD-3-Clause | 1.15.2 | Standard scientific library; required. |
| **scikit-learn** | Downstream classifier and manifold reference | BSD-3-Clause | 1.6.1 | Optional; evaluated only when imported. |
| **Ripser** | Persistent homology Betti intervals ($\beta_0, \beta_1$) | MIT | 0.6.15 | Optional; if unavailable, boundary yields `not_comparable` and Stage 4 halts (`blocked`). |
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

### Programmatic Python Usage
```python
from tools.synthetic_pipeline_replay import SyntheticPipelineReplayRunner

runner = SyntheticPipelineReplayRunner(
    channels=("Fp1", "Fp2", "C3", "C4"),
    sfreq_hz=250.0,
    duration_s=2.0,
    seed=42,
)

report = runner.run_replay()
print(f"Pipeline replay status: {report.status}")
for boundary in report.boundaries:
    print(f"Boundary {boundary.boundary_id}: {boundary.status}")
```
