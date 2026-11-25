# Signal Interoperability Conformance Specification

This specification and test suite defines and enforces cross-adapter interoperability standards for `NeuroTopology-Sim`. It ensures that signal streaming adapters (including PR #212 contracts, PR #214 MNE/SciPy streaming, and PR #220 native format adapters) satisfy deterministic scientific and architectural invariants.

---

## 1. Conformance Rules (16 Contract Properties)

Every signal chunk and adapter pipeline must satisfy the following 16 properties:

1. **Shape Invariance**: Signal data chunks must have shape `(channels, samples)`. No transposed or implicit dimension permutations are permitted.
2. **Deterministic Channel Order**: Channels must preserve an exact, deterministic sequence matching the source header or explicit configuration.
3. **Exact Sampling Frequency**: The sampling rate (`sample_rate_hz`) must be a positive finite float preserved without downsampling or roundoff drift.
4. **Explicit Units and Scaling**: Every channel must declare explicit engineering units (e.g., `"uV"`), preventing ambiguous uncalibrated integer readings.
5. **Deterministic Source Checksum**: Every chunk must carry the deterministic 64-character lowercase SHA-256 hex digest of the raw source file.
6. **Montage Coordinate States**: Spatial sensor coordinates must be either:
   - *Native*: Derived directly from source digpoints.
   - *Safely Inferred*: Mapped from a known standard montage (e.g. `standard_1020`) where channel names match exactly.
   - *Unavailable*: Explicitly `None` when absent.
7. **Provenance on Inferred Coordinates**: Any inferred coordinates must explicitly record their montage provenance (e.g., `montage_name="standard_1020"`).
8. **No Silent Coordinate Fabrication**: Adapters must never inject dummy, zeroed, or `NaN` coordinates for missing channels.
9. **Reproducible Chunk Boundaries**: Timestamps must be strictly monotonic, and repeated runs on identical sources must produce identical window boundaries and chunk indices.
10. **Structured Capability State**: If optional dependencies (e.g., `mne`, `pybv`, `edfio`) are absent, the system must report a structured capability state rather than crashing.
11. **Actionable Errors on Malformed Inputs**: Corrupted headers, incomplete records, or invalid formats must produce explicit, actionable exceptions (`ValueError`, `InteropValidationError`, `OSError`).
12. **Zero Network Access**: Adapters must execute strictly offline without outbound network requests or background downloads.
13. **Lazy Optional Imports**: Modules must not import heavy packages (e.g. `mne`, `scipy`) eagerly at top-level package-import time.
14. **Metadata Preservation**: Key metadata (sample rate, channel names, source checksum) must be preserved without loss across conversions.
15. **Deterministic Edge Case Handling**: Empty files, single-channel recordings, or truncated chunks must be handled cleanly and deterministically.
16. **Finite Numeric Values**: All data arrays, timestamps, and coordinates must consist solely of finite floating-point values (no unhandled `NaN` or `Inf`).

---

## 2. Deterministic Conformance Fixtures

Located under `tests/interop_conformance/fixtures/`:

- `numpy_fixture.npy`: Standard 2D floating-point NumPy array fixture shaped `(channels, samples)`.
- `signal_fixture.csv`: Deterministic multi-channel time-series CSV fixture with header.
- `fif_metadata.json`: Deterministic FIF header metadata containing native 3D electrode coordinates.
- `edf_metadata.json`: Deterministic EDF header metadata specifying channel labels for standard 10-20 montage inference.
- `brainvision_metadata.json`: Deterministic BrainVision header metadata.
- `missing_montage.json`: Specification fixture for signals with explicitly unavailable spatial coordinates.
- `inferred_montage.json`: Specification fixture verifying montage inference and provenance tags.
- `malformed_input.bin`: Deliberately corrupted binary file for actionable error validation.

---

## 3. Running Conformance Validation

### Quick Conformance Run via pytest
```bash
python -m pytest tests/interop_conformance/ -v
```

### Full Multi-Suite Conformance Runner
The standalone runner evaluates the 16 rules, inspects active adapter capabilities (PR #212, PR #214, PR #220), runs existing interop tests when available, checks governance policies, and outputs a structured JSON report:
```bash
python scripts/validate_interop_conformance.py
```

### Structured Conformance Report Example
```json
{
  "status": "PASS",
  "contracts_tested": [
    "1. Signal chunks have shape (channels, samples)",
    "2. Channel order is deterministic",
    "..."
  ],
  "adapters_tested": [
    "Reference_Idealized_Adapter"
  ],
  "missing_capabilities": [
    "PR214_MNE_Streaming (iter_mne_signal_chunks not found in eeg_mne_adapter)",
    "PR220_Native_Signal (eeg_native_adapter module not present in checkout)"
  ],
  "test_results": {
    "compilation": "PASS",
    "conformance_suite": "PASS",
    "existing_interop_tests": "SKIPPED (Directory not in current checkout)",
    "pr214_adapter_tests": "SKIPPED (PR #214 test file not in current checkout)",
    "pr220_adapter_tests": "SKIPPED (PR #220 test file not in current checkout)",
    "governance_validation": "PASS"
  }
}
```

---

## 4. Architectural Independence

The conformance suite is designed to run in any of the following configurations:
1. **On `main` alone**: Validates the 16 contract properties using deterministic reference models and reports unmerged PR capabilities honestly as missing.
2. **On PR #212**: Validates `shared.interop.contracts` schemas against the conformance invariants.
3. **On PR #214**: Validates the streaming MNE EEG adapter against streaming chunk and lazy import requirements.
4. **On PR #220**: Validates native signal adapters (NumPy, CSV, etc.) against shape and metadata preservation.
5. **Combined / Post-Merge**: Validates the unified cross-adapter matrix end-to-end.
