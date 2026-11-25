# Provenance-Aware Recording-Quality Gate

## Overview

The `shared.provenance.recording_quality` module provides a memory-bounded, provenance-aware recording-quality evaluator for local EEG and MEG data containers in NeuroTopology-Sim.

The evaluator guarantees that raw signal files are verified for syntactic correctness, header completeness, signal finiteness, channel uniqueness, and provenance authenticity before any downstream analysis or pipeline execution can consume them.

## Scientific Guardrails

1. **Header validation is not independent empirical validation.**
   Confirming that a file exists, possesses valid metadata, and contains finite values in initial sample windows confirms container integrity and syntactic readability; it does not validate empirical scientific hypotheses or falsify theories.
2. **Synthetic data is never empirical evidence.**
   Recordings flagged or detected as synthetic, phantom, simulation, or demonstration data are strictly classified as `VALIDATED_SYNTHETIC_ONLY` and can never enter formal empirical evidence pathways.
3. **No label inference.**
   The evaluator strictly forbids inferring clinical, behavioral, or cognitive states (such as `awake`, `sedated`, `meditation`, or `task`) from filenames, directory structures, or arbitrary strings. All labels must be supplied explicitly by an authenticated operator configuration or manifest.
4. **No clinical claims.**
   The evaluator performs technical signal and metadata quality gating only. It makes no diagnostic, therapeutic, or clinical claims.

---

## Quality States Taxonomy

The evaluator assigns one of seven mutually exclusive quality states to every target container:

| Quality State | Meaning | Passed Validation | Evidence Suitability |
| :--- | :--- | :---: | :--- |
| `VALIDATED_EMPIRICAL_LOCAL` | Container verified, headers complete, bounded sample chunk finite, empirical provenance authenticated. | **YES** | Eligible for local empirical analysis pipeline. |
| `VALIDATED_SYNTHETIC_ONLY` | Container valid, but detected or flagged as synthetic, mock, phantom, or simulation data. | **YES** | Demonstration / testing only; rejected from empirical evidence paths. |
| `INCOMPLETE_METADATA` | Container missing mandatory metadata fields (e.g. missing `dataset_description.json` in BIDS, zero channels). | **NO** | Inconclusive; requires operator repair. |
| `INVALID_RECORDING` | Container corrupted, non-finite values (NaN/Inf) in inspected chunk, duplicate channels, or missing companion files. | **NO** | Rejected. |
| `MISSING_OPTIONAL_DEPENDENCY` | Required reader library (e.g. `mne`, `mne_bids`) not installed in execution environment. | **NO** | Capability state; no scientific result. |
| `UNSUPPORTED_FORMAT` | File extension or container type not recognized. | **NO** | Rejected. |
| `UNAVAILABLE_FILE` | Specified path does not exist or cannot be accessed. | **NO** | Rejected. |

---

## Supported Formats & Inspection Mechanics

### 1. Neuromag FIF (`.fif`, `.fif.gz`)
- **Inspection:** Uses lazy header parsing via `mne.io.read_raw_fif(path, preload=False)`.
- **Validation:** Sampling rate $> 0$, channel count $> 0$, channel uniqueness, bad-channel lists, 3D montage coordinate availability, and finite bounded samples.
- **Dependency:** Optional dependency `mne`. If absent, emits `MISSING_OPTIONAL_DEPENDENCY`.

### 2. European Data Format (`.edf`) & BioSemi (`.bdf`)
- **Inspection:** Lazy inspection via `mne.io.read_raw_edf(path, preload=False)` or `read_raw_bdf(path, preload=False)`.
- **Validation:** Signal labels, physical/digital min/max compliance, sampling rates, channel uniqueness, and finite bounded chunk.
- **Dependency:** Optional dependency `mne`. If absent, emits `MISSING_OPTIONAL_DEPENDENCY`.

### 3. BrainVision (`.vhdr`, `.vmrk`, `.eeg`)
- **Inspection:** Multipart container inspection. Evaluates the text header `.vhdr` and parses referenced `DataFile` and `MarkerFile`.
- **Companion File Check:** Verifies companion `.eeg` and `.vmrk` files exist on disk. If either companion file is missing, marks container as `INVALID_RECORDING` (`MISSING_COMPANION_FILE`).
- **Signal Inspection:** When `mne` is available, evaluates bounded samples via `mne.io.read_raw_brainvision(path, preload=False)`. If `mne` is absent, text header validation succeeds while signal inspection reports `MISSING_OPTIONAL_DEPENDENCY`.

### 4. BIDS Container Directories
- **Inspection:** Recursively inspects BIDS directory structure.
- **Validation:** Verifies presence and valid JSON structure of `dataset_description.json` (`Name`, `BIDSVersion`). Discovers recordings matching `sub-*/eeg/*` or `sub-*/meg/*` and validates representative recording files under bounded limits.

---

## Strict Memory Boundedness

To support high-density recordings (e.g. 256-channel EEG or 306-channel MEG running for multiple hours), the evaluator enforces strict memory boundedness:

- **No Full Preloading:** `preload=False` is unconditionally enforced. Whole recordings are never loaded into RAM.
- **Bounded Sample Inspection:** Finiteness verification evaluates only the first `bounded_samples` (default: 512 samples, corresponding to $\approx 1-2$ seconds of data).
- **Inspected Chunk Assertion:** Asserts that all values in the bounded matrix $X \in \mathbb{R}^{C \times T}$ satisfy `np.all(np.isfinite(X))`. If any `NaN` or `Infinity` value is encountered, the recording is marked `INVALID_RECORDING`.

---

## JSON Serialization & Deterministic Report Checksums

Reports are serialized to JSON with strict null-safety and cryptographic tamper-detection:

1. **Null for Unavailable Numerics:** Unavailable numeric fields (such as indeterminate duration or missing montage coordinates) serialize as `null` (`None` in Python).
2. **Rejection of NaN and Infinity:** `json.dumps(..., allow_nan=False)` is enforced. Any unhandled NaN or Inf raises an explicit `ValueError`.
3. **Deterministic SHA-256 Report Checksum:**
   The report dictionary is canonicalized with sorted keys and compact separators:
   ```python
   canonical = json.dumps(report_dict_without_hash, sort_keys=True, separators=(',', ':'), allow_nan=False)
   report_checksum_sha256 = hashlib.sha256(canonical.encode('utf-8')).hexdigest()
   ```
   Downstream systems can verify report integrity with `verify_report_checksum(report_dict)`.

---

## CLI Usage

The command-line interface is provided by `scripts/validate_recording_quality.py`:

```bash
# Validate a single FIF recording
python scripts/validate_recording_quality.py data/sample_raw.fif

# Inspect with explicit bounded sample limit and output formatted Markdown
python scripts/validate_recording_quality.py data/synthetic_bv.vhdr --bounded-samples 256 --format markdown

# Enforce strict empirical validation (fails if synthetic fixtures are supplied)
python scripts/validate_recording_quality.py data/patient_recording.edf --strict-empirical

# Validate multiple files and save JSON report to disk
python scripts/validate_recording_quality.py rec1.fif rec2.edf -o outputs/quality_report.json
```

### Options Reference

- `targets`: Positional recording or BIDS container paths.
- `--path`, `-p`: Repeated explicit target paths.
- `--bounded-samples`: Max sample frames inspected for finiteness (default: `512`).
- `--provenance-hint`: `auto` (default), `empirical`, `synthetic`.
- `--format`: `json` (default), `markdown`.
- `--strict-empirical`: Exits with nonzero status unless all targets are `VALIDATED_EMPIRICAL_LOCAL`.
- `--output`, `-o`: Write report to destination file.
- `--quiet`: Suppress terminal stdout.
