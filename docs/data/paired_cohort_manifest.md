# Empirical Cohort Discovery and Paired-Condition Manifest Builder

## 1. Overview and Scientific Motivation

Previous empirical cohort evaluations in `NeuroTopology-Sim` produced `insufficient_paired_subjects` warnings or halted execution prematurely. Investigation revealed that the pipeline relied on brittle, format-restricted local globbing patterns (e.g., hardcoded scans for `*task-awake*.vhdr` and `*task-sed2*.vhdr`):

1. **Format Blindness**: Ignored standard electrophysiology formats such as European Data Format (`.edf`, `.bdf`), Neuromag FIF (`.fif`, `.fif.gz`), and preprocessed arrays.
2. **Companion Desynchronization**: BrainVision files (`.vhdr`) were indexed without verifying whether the underlying data files (`.eeg`) or marker files (`.vmrk`) actually existed on disk, leading to downstream read crashes.
3. **Session and Run Conflation**: Multi-session (`ses-01`, `ses-02`) and multi-run (`run-01`, `run-02`) structures resulted in collision or duplicate matches.
4. **Condition Label Fabrication Risk**: Hardcoded mappings risked conflating distinct experimental states (e.g., guessing that `meditation` or `rest_eyes_closed` equals `awake`).
5. **Lack of Readiness Distinctions**: Downstream falsification systems could not distinguish between a completely empty directory (`NO_DATA`), corrupted files (`MALFORMED_COHORT`), or valid data that simply lacked statistical sample size (`INSUFFICIENT_PAIRS`).

The `cohort_manifest` subsystem provides a local-only, offline, provenance-tracked manifest builder and readiness gate that resolves these issues **without downloading external data or manufacturing synthetic subjects**.

---

## 2. Core Architecture

```
Local BIDS or Data Root
          │
          ▼
 [Local File Discovery]  <-- 100% Offline, recursive filesystem scan
          │
          ├── BrainVision (.vhdr) + verifies companion .eeg / .vmrk
          ├── EDF / BDF (.edf, .bdf) via pure-Python standard library parser
          ├── Neuromag FIF (.fif, .fif.gz) via MNE or fallback tag inspector
          └── Fixtures (.npy, .csv) explicitly flagged as synthetic
          │
          ▼
 [Provenance & Metadata Extractor]
          │
          ├── BIDS entity parser (subject, session, task, condition, run, datatype)
          ├── Provenance dictionary tracking source for every attribute
          ├── Exact condition label preservation (no unconfigured inference)
          ├── Deterministic SHA-256 block hash
          └── BIDS sidecar augmentation (_eeg.json, _channels.tsv, _electrodes.tsv)
          │
          ▼
 [Pairing Engine]
          │
          ├── Configurable pairing keys (e.g. ["subject"], ["subject", "session"])
          ├── Exact condition match against condition_a and condition_b
          ├── Conflict detection: duplicates, ambiguous labels, missing companions
          └── Synthetic segregation: fixtures never count toward empirical gate
          │
          ▼
 [Readiness Gate]
          │
          ├── NO_DATA: 0 recordings found
          ├── MALFORMED_COHORT: unparseable files, missing data files, corrupt headers
          ├── INSUFFICIENT_PAIRS: empirical pairs < min_pairs
          └── VALID_PAIRED_COHORT: empirical pairs >= min_pairs
          │
          ▼
 [Deterministic Artifacts]
          ├── paired_cohort_manifest.json
          ├── paired_cohort_manifest.csv
          └── paired_cohort_summary.json
```

---

## 3. Supported Data Formats

| Format | Extension | Primary Header / Reader | Metadata Extracted |
| :--- | :--- | :--- | :--- |
| **BrainVision** | `.vhdr` | INI text parser (pure Python standard library) | `sample_rate` (from `SamplingInterval`), `channel_count`, companion files (`.eeg`, `.vmrk`), coordinates |
| **EDF / BDF** | `.edf`, `.bdf` | Binary header parser (pure Python `struct`) | `sample_rate` (from record duration & channel samples), `channel_count` (`ns`), duration |
| **Neuromag FIF** | `.fif`, `.fif.gz` | MNE raw reader (when installed) / tag fallback | `sample_rate`, `channel_count`, digitization montage state |
| **NPY Array** | `.npy` | Binary header shape unpacker | `channel_count`, flagged as `is_synthetic = True` |
| **CSV Fixture** | `.csv` | Column parser | `channel_count`, flagged as `is_synthetic = True` |

---

## 4. Extraction & Provenance Tracking

Every recording record preserves explicit provenance for all metadata fields via `ProvenanceRecord`:

- `subject_source`: `"bids_filename"`, `"directory_hierarchy"`, or `"null"`
- `session_source`: `"bids_filename"`, `"directory_hierarchy"`, or `"null"`
- `task_source`: `"bids_filename"`, `"sidecar_json"`, or `"null"`
- `condition_source`: `"bids_task"`, `"bids_filename"`, `"sidecar_task"`, `"explicit_mapping"`, or `"null"`
- `run_source`: `"bids_filename"`, or `"null"`
- `datatype_source`: `"bids_suffix"`, `"directory_hierarchy"`, or `"null"`
- `sample_rate_source`: `"file_header"`, `"sidecar_json"`, or `"null"`
- `channel_count_source`: `"file_header"`, `"sidecar_json"`, `"channels_tsv"`, or `"null"`
- `montage_state_source`: `"file_header"`, `"electrodes_tsv"`, or `"null"`

Missing metadata is strictly represented as `null` in JSON and empty string in CSV (never stringified `"None"`, `NaN`, or fabricated placeholders).

---

## 5. Condition Preservation and Configurable Pairing

### Exact Condition Rule
In compliance with repository guardrails:
- Condition labels are preserved **verbatim** from BIDS entities or sidecar metadata.
- The pipeline **never** infers that `rest` or `baseline` implies `awake`, or that `sed2` or `propofol` implies `sedated`, unless an explicit condition alias is passed by the operator (e.g. `--condition-alias sedation=sed2,awake_ec=awake`).

### Configurable Pairing Keys
By default, recordings are paired by subject identity (`pairing_keys=["subject"]`).
When datasets have multiple sessions or runs, operators can configure finer-grained pairing:
- Session-matched pairing: `--pairing-keys subject,session`
- Run-matched pairing: `--pairing-keys subject,run`

### Conflict Reporting
The manifest exhaustively inventories:
- `paired_records`: exact 1-to-1 pairings for condition A and condition B matching the key.
- `unpaired_records`: subjects missing either condition A or condition B.
- `duplicate_candidates`: subjects with multiple runs for condition A or condition B (preventing arbitrary pairing bias).
- `ambiguous_matches`: recordings with conflicting or unresolvable condition assignments.
- `missing_files`: recordings whose referenced binary or marker files are missing on disk.
- `invalid_files`: unparseable, truncated, or corrupt files.

---

## 6. Downstream Falsification Readiness Gate

Downstream statistical pipelines (such as Wilcoxon signed-rank tests or persistent homology estimators) check the `status` field:

1. **`no_data` (`NO_DATA`)**: The scan directory contains zero recognizable recordings. Downstream code aborts immediately with an explicit descriptive message.
2. **`malformed_cohort` (`MALFORMED_COHORT`)**: Files are corrupt, truncated, missing companions, or lack valid pairing keys, preventing cohort formation.
3. **`insufficient_pairs` (`INSUFFICIENT_PAIRS`)**: Valid empirical pairs were found, but the count is strictly below the configured `min_pairs` gate. Downstream comparative statistical tests remain descriptive and do not execute underpowered inferential tests.
4. **`valid_paired_cohort` (`VALID_PAIRED_COHORT`)**: The number of valid empirical pairs meets or exceeds `min_pairs`. Full comparative inference is enabled.

### Synthetic Segregation
Synthetic fixtures are strictly segregated:
- Files residing in `synthetic/`, `fixture/`, `mock/`, or formatted as `.npy`/`.csv` are flagged with `is_synthetic = True`.
- Synthetic pairs are counted under `synthetic_paired_count` and are **excluded** from `empirical_paired_count`.
- Synthetic fixtures cannot satisfy the empirical minimum-paired-subject gate unless `--allow-synthetic` is explicitly declared.

---

## 7. CLI Reference

### Basic Usage
```bash
python scripts/build_paired_cohort_manifest.py \
  --input-dir data/ds005620 \
  --condition-a awake \
  --condition-b sed2 \
  --output-dir artifacts/cohort_manifest/ds005620 \
  --min-pairs 2
```

### Advanced Arguments

| Argument | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `--input-dir`, `-i` | Path | Required | Directory to scan recursively. |
| `--condition-a`, `-a` | str | Required | Exact condition label for condition A. |
| `--condition-b`, `-b` | str | Required | Exact condition label for condition B. |
| `--output-dir`, `-o` | Path | Required | Directory where manifest artifacts are written. |
| `--min-pairs` | int | `2` | Minimum paired subjects gate. |
| `--pairing-keys` | str | `"subject"` | Comma-separated pairing keys (e.g. `"subject,session"`). |
| `--condition-alias` | str | `None` | Explicit mappings (e.g. `"awake_ec=awake,sedation=sed2"`). |
| `--allow-synthetic` | flag | `False` | Allow synthetic fixtures in cohort pairing. |
| `--formats` | str | `None` | Comma-separated format filter (e.g. `"vhdr,edf,bdf,fif"`). |
| `--strict` | flag | `False` | Exit with status code 2 if cohort is not `valid_paired_cohort`. |
| `--json-out` | Path | `None` | Custom path for full manifest JSON. |
| `--csv-out` | Path | `None` | Custom path for tabular manifest CSV. |
| `--summary-out` | Path | `None` | Custom path for gate summary JSON. |

### Generated Outputs
1. **`paired_cohort_manifest.json`**: Complete structured JSON representation of the manifest, including all recordings, provenance, pairs, unpairs, duplicates, missing files, and readiness status.
2. **`paired_cohort_manifest.csv`**: Tabular CSV of all discovered recordings with metadata and provenance.
3. **`paired_cohort_summary.json`**: Lightweight summary for consumption by CI or orchestration gates.

---

## 8. Guardrails and Compliance

In accordance with `AGENTS.md` and repository scientific governance:
- **No clinical claims**: The manifest builder indexes physical signals and does not diagnose, assess pathology, or claim clinical efficacy.
- **No ontology promotion**: Structural categories strictly reflect file-system and BIDS schema labels.
- **No proof claims**: Output statuses reflect empirical dataset completeness and statistical sample size requirements, not physical proofs.
- **No real-data fabrication**: The manifest builder discovers existing local files; it never manufactures mock subjects to artificially pass sample size gates.
- **No network access**: All operations are 100% offline and execute locally.
