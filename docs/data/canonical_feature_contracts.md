# Canonical Feature Contracts Specification

## 1. Overview and Purpose

The **Canonical Feature Contracts** layer provides a standardized, schema-governed, provenance-rich specification for features extracted across electrophysiology, higher-order spectral analysis, multivariate functional connectivity, peripheral physiology, and topological invariants in `NeuroTopology-Sim`.

### Core Objectives
- **Standardized Representation**: Unify distinct feature representations under versioned schemas with explicit physical units, dimensional axes, and coordinate tracking.
- **Decoupled Architecture**: Allow feature extractors, topology runners, statistical engines, and monitoring dashboards to interoperate without hard import dependencies.
- **Scientific Guardrails**: Prevent invalid conflations (e.g., confusing graph persistence with spatial phase charge, or conflating statistical dependence with causality).
- **Epistemic Integrity**: Maintain strict boundary separation between empirical physiological recordings and synthetic scaffolding or computational model outputs.
- **Auditability & Traceability**: Guarantee end-to-end reproducibility through deterministic SHA-256 checksums and immutable provenance records.

---

## 2. Schema Specification

The specification defines two canonical objects:
1. `FeatureRecord` (alias `CanonicalFeatureRecord`): An individual feature or feature tensor (`FeatureRecord.v1`).
2. `FeatureBundle` (alias `CanonicalFeatureBundle`): A session- or run-level collection of feature records (`FeatureBundle.v1`).

### 2.1. FeatureRecord Schema (`FeatureRecord.v1`)

| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `schema_version` | `string` | Yes | Defaults to `FeatureRecord.v1`. Canonical versions: `FeatureRecord.v1`, `CanonicalFeatureRecord.v1`, `NeuroTopologySim.CanonicalFeatureRecord.v1`. |
| `feature_family` | `string` | Yes | One of the registered families in `FeatureFamily`. |
| `feature_name` | `string` | Yes | Non-empty unique identifier for the feature (e.g. `alpha_psd`, `wpli_matrix`). |
| `mathematical_definition` | `string` | Yes | Unambiguous formulation or algorithmic reference. |
| `units` | `string` | Yes | Physical or mathematical unit string from the approved whitelist. |
| `frequency_axis` / `frequency_band` | `object` \| `null` | No | Object containing `low_hz` (float), `high_hz` (float), and optional `band_name`. |
| `time_axis` / `time_window` | `object` \| `null` | No | Object containing `start_s` (float) and `duration_s` (float > 0). |
| `sampling_rate_hz` | `float` \| `null` | No | Positive sampling frequency. Must be `null` if missing (never `0` or `0.0`). |
| `channel_node_identity` | `list[string]` | Yes | Ordered array of unique channel names or graph node labels. |
| `coordinate_status` | `string` | Yes | One of: `3d_montage`, `2d_planar`, `topological_abstract`, `missing`. |
| `montage_coordinates` | `list[list[float]]` \| `null` | No | 3D `[x, y, z]` coordinates matching channels 1:1. |
| `subject` | `string` \| `null` | No | BIDS subject identifier (e.g., `sub-01`). |
| `session` | `string` \| `null` | No | BIDS session identifier (e.g., `ses-01`). |
| `run` | `string` \| `null` | No | BIDS run identifier (e.g., `run-01`). |
| `condition_label` | `string` \| `null` | No | Experimental condition (e.g., `baseline_eyes_closed`, `sevoflurane_sedation`). Non-empty when provided. |
| `source_checksum` / `provenance_checksum` | `string` | Yes | SHA-256 hash representing upstream input data and transformation history. |
| `preprocessing` | `list[string]` | Yes | Ordered pipeline steps applied (e.g., `["bandpass_0.5_45hz", "rereference_average"]`). |
| `missingness` | `float` \| `null` | No | Fraction of missing or interpolated samples in `[0.0, 1.0]`. |
| `uncertainty` | `object` \| `null` | No | Uncertainty metadata (e.g., `{"method": "bootstrap_sem", "ci": 0.95}`). |
| `is_synthetic` / `synthetic_empirical_origin` | `bool` / `string` | Yes | Synthetic origin flag (`is_synthetic: bool` or `synthetic_empirical_origin: 'empirical' | 'synthetic'`). |
| `evidence_class` | `string` | Yes | One of: `empirical_feature`, `computational_model`, `synthetic_scaffolding`, `descriptive_topology_only`. |
| `axes` | `list[string]` | Yes | Dimension labels (e.g. `["channel", "frequency"]`). Length must match tensor dimensions. |
| `shape` | `list[int]` | Yes | Dimensions matching `values`. Empty `[]` if `values` is `null`. |
| `values` | `any` \| `null` | No | Multi-dimensional array of finite numerical values, or `null`. |
| `checksum` | `string` | Yes | Deterministic SHA-256 digest of the canonicalized record JSON. |

### 2.2. FeatureBundle Schema (`FeatureBundle.v1`)

| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| `schema_version` | `string` | Yes | Defaults to `FeatureBundle.v1`. Canonical versions: `FeatureBundle.v1`, `CanonicalFeatureBundle.v1`. |
| `bundle_id` | `string` | Yes | Unique bundle identifier. |
| `subject` | `string` \| `null` | No | Subject identifier across records in bundle. |
| `session` | `string` \| `null` | No | Session identifier across records in bundle. |
| `run` | `string` \| `null` | No | Run identifier. |
| `condition_label` | `string` \| `null` | No | Condition label for the bundle. |
| `is_synthetic` | `bool` | Yes | Synthetic status matching contained records. |
| `source_checksum` | `string` | Yes | SHA-256 digest of upstream raw bundle inputs. |
| `records` | `list[FeatureRecord]` | Yes | Canonically ordered list of validated feature records. |
| `bundle_checksum` | `string` | Yes | Deterministic SHA-256 digest over the sorted bundle. |

---

## 3. Registered Feature Families

The contract registers core feature families spanning electrophysiology, higher-order structures, physiology, and topology:

1. **`psd`** (Power Spectral Density)
   - *Approved Units*: `uV^2/Hz`, `V^2/Hz`, `dB`, `log_uV2_Hz`.
   - *Typical Axes*: `["channel", "frequency"]` or `["frequency"]`.
2. **`cross_spectrum`** (Cross-Spectral Density)
   - *Approved Units*: `uV^2/Hz`, `V^2/Hz`.
   - *Typical Axes*: `["channel_i", "channel_j", "frequency"]`.
3. **`pairwise_fc`** (Pairwise Functional Connectivity)
   - *Approved Units*: `dimensionless`.
   - *Typical Axes*: `["channel_i", "channel_j"]`.
4. **`triadic_fc`** (Triadic Higher-Order Interactions)
   - *Approved Units*: `dimensionless`, `ratio`, `z-score`, `bits`, `nats`.
   - *Typical Axes*: `["channel_i", "channel_j", "channel_k"]`.
5. **`bispectrum`** / **`higher_order_spectra`** (Higher-Order Spectra / Bispectra)
   - *Approved Units*: `dimensionless`, `arbitrary_units`, `a.u.`.
   - *Typical Axes*: `["channel", "freq1", "freq2"]`.
6. **`trispectrum_modulogram`** / **`trispectrum`** / **`modulogram`** (Trispectrum / Modulation Indices)
   - *Approved Units*: `dimensionless`, `arbitrary_units`, `a.u.`.
   - *Typical Axes*: `["channel", "freq_phase", "freq_amp"]`.
7. **`respiration`** (Respiratory Physiology)
   - *Approved Units*: `bpm`, `Hz`, `1/s`, `arbitrary_units`.
   - *Typical Axes*: `["time_window"]`.
8. **`ecg_hrv`** (Electrocardiography / Heart Rate Variability)
   - *Approved Units*: `ms`, `bpm`, `ratio`, `dimensionless`.
   - *Typical Axes*: `["time_window"]`.
9. **`spatial_phase_charge`** (Spatial Phase Singularity & Topological Charge)
   - *Approved Units*: `rad`, `dimensionless`, `integer`.
   - *Typical Axes*: `["charge_component"]` or `["defect_index"]`.
   - *Prerequisite*: Mandatory 2D or 3D montage coordinates (`coordinate_status != 'missing'`).
10. **`graph_beta_1`** (Persistent Homology 1-Cycles on Abstract Graphs)
    - *Approved Units*: `counts`, `integer`, `index`, `dimensionless`.
    - *Typical Axes*: `["filtration_step"]` or `["cycle_index"]`.
11. **`directed_hypergraph`** (Higher-Order Directed Hypergraph Transitions)
    - *Approved Units*: `index`, `ratio`, `dimensionless`.
    - *Typical Axes*: `["hyperedge_order"]` or `["transition_step"]`.
12. **`behavioral_transition_labels`** (Behavioral State & Task Indicators)
    - *Approved Units*: `dimensionless`, `index`, `integer`.
    - *Typical Axes*: `["time_window"]`.

---

## 4. Scientific Guardrails and Boundary Rules

To prevent statistical confusion, mathematical conflation, and ungrounded neuroscientific claims, validators enforce the following non-negotiable rules:

1. **Graph $\beta_1$ is NOT Spatial Phase Charge**:
   - One-dimensional Betti numbers computed over abstract correlation complexes (e.g., Vietoris-Rips or clique complexes) reflect combinatorial graph topology, **not** continuous phase vortices or topological charge on the cortical manifold. Records in `graph_beta_1` cannot contain `spatial_charge`, `vortex_charge`, or `spatial_winding`.
2. **Spatial Phase Charge Requires Physical Coordinates and is NOT Graph Persistence**:
   - `spatial_phase_charge` requires genuine electrode coordinates (`3d_montage` or `2d_planar`). It cannot be calculated without spatial geometry, and cannot claim persistent homology cycle metrics (`betti_1`, `graph_persistence`, `clique_complex`).
3. **Triadic FC Reflects Statistical Dependence, NOT Causality**:
   - Higher-order metrics such as O-information or total correlation quantify information redundancy or synergy, **not** causal mechanics. Records in `triadic_fc` cannot claim `granger_causality`, `causal_driver`, or `directed_causality`.
4. **Trispectral Modulation is NOT Topology**:
   - Bispectra, trispectra, and modulograms reflect non-linear harmonic phase-amplitude interactions. They do not constitute topological invariants or homology groups. Records in `higher_order_spectra`, `bispectrum`, `trispectrum_modulogram`, `trispectrum`, or `modulogram` cannot claim `homology_group`, `betti_number`, or `topological_invariant`.
5. **Respiration is NOT Automatically Arousal or Consciousness**:
   - Peripheral respiratory dynamics reflect autonomic modulation. They cannot be framed as direct readouts of conscious level or anesthetic depth. Records in `respiration` cannot claim `consciousness_level` or `depth_of_anesthesia`.
6. **Behavioral Constructs and Mental Discernment Cannot Be Inferred from EEG Alone**:
   - Electrophysiological features must not be branded with subjective, philosophical, or spiritual labels (e.g., `discernment_score`, `enlightenment_index`, `behavioral_construct`).
7. **Missing Metadata Null Rule**:
   - Missing numerical values or metadata (such as `sampling_rate_hz`) must be explicitly serialized as `null`. They must **never** be coerced to `0` or `0.0`.
8. **Synthetic-Empirical Boundary Separation**:
   - Synthetic scaffolding and simulated data cannot enter formal empirical evidence. A record with `is_synthetic=True` can **never** have `evidence_class="empirical_feature"`.
9. **Condition-Label Validation**:
   - `condition_label` when provided cannot be empty or purely whitespace.

---

## 5. Decoupled Migration Pattern

Extractors developed in separate branches or external modules can emit canonical feature records **without importing `shared.feature_contracts` directly**. Any module can simply emit a Python dictionary conforming to the schema.

### 5.1. Zero-Dependency Emission Template

```python
def extract_alpha_psd(raw_signal, fs: float, ch_names: list[str]) -> dict:
    """Emits a canonical feature record dictionary without requiring library imports."""
    psd_values = compute_welch(raw_signal, fs)  # e.g., shape [len(ch_names), n_freqs]

    return {
        "schema_version": "FeatureRecord.v1",
        "feature_family": "psd",
        "feature_name": "welch_alpha_psd",
        "mathematical_definition": "Welch average periodogram in alpha band (8-13 Hz)",
        "units": "uV^2/Hz",
        "frequency_axis": {"low_hz": 8.0, "high_hz": 13.0, "band_name": "alpha"},
        "time_axis": {"start_s": 0.0, "duration_s": 60.0},
        "sampling_rate_hz": float(fs),
        "channel_node_identity": ch_names,
        "coordinate_status": "missing",
        "montage_coordinates": None,
        "subject": "sub-01",
        "session": "ses-01",
        "run": "run-01",
        "condition_label": "resting_state",
        "source_checksum": "0" * 64,
        "preprocessing": ["bandpass_0.5_45hz", "notch_60hz"],
        "missingness": 0.0,
        "uncertainty": None,
        "is_synthetic": False,
        "evidence_class": "empirical_feature",
        "axes": ["channel", "frequency"],
        "shape": list(psd_values.shape),
        "values": psd_values.tolist(),
        "checksum": "",
    }
```

When ingested by downstream consumers, calling `record_from_dict(data, validate=True)` will validate all guardrails and populate deterministic checksums automatically.

---

## 6. CLI Reference

The validation CLI allows auditing single files or full directory trees of records and bundles:

```bash
# Validate a single feature record or bundle
python scripts/validate_feature_contract.py --input path/to/record.json

# Validate an entire directory of feature artifacts and save summary report
python scripts/validate_feature_contract.py --input outputs/features/ --output outputs/reports/feature_audit.json
```

### Exit Codes
- `0`: All inspected files conform strictly to the schema, unit whitelist, and scientific guardrails.
- `1`: Invalid input argument, file not found, or JSON parsing error.
- `2`: Schema validation error or guardrail violation detected in one or more files.
