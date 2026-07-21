# OpenNeuro BIDS Dataset Access Guide

## Overview

This document explains how to fetch and process real BIDS datasets from OpenNeuro using the restored simulator pipelines. The system has been updated to support three data access methods:

1. **Datalad (Recommended)**: Direct access to OpenNeuro git-annex repositories
2. **Local BIDS Directory**: For offline testing and pre-downloaded data
3. **Direct HTTPS** (Fallback): GitHub raw content when S3 access fails

## Method 1: Datalad Access (Production)

Datalad is the official tool for accessing OpenNeuro datasets. It handles git-annex file versioning automatically.

### Setup

```bash
# Install datalad and required tools
pip install datalad datalad-osf

# Verify installation
datalad --version
```

### Fetch ds005620 (Anesthesia EEG, 98 subjects)

```bash
# Clone the dataset repository (git metadata only, ~1 GB)
datalad clone https://github.com/OpenNeuroDatasets/ds005620.git ds005620

cd ds005620

# List available subjects
ls -d sub-*/ | wc -l  # Should show ~98

# Fetch data for specific subjects
datalad get sub-1010/eeg/sub-1010_task-awake_acq-EC_eeg.vhdr
datalad get sub-1010/eeg/sub-1010_task-awake_acq-EC_eeg.vmrk
datalad get sub-1010/eeg/sub-1010_task-awake_acq-EC_eeg.eeg
```

### Run Pipeline with Datalad

```bash
cd /path/to/ScienceR-Dsim

# Single subject test
python dual_engine/anesthesia_signed_winding_pipeline.py \
  --subjects 1010 \
  --use-datalad \
  --out results_1010.jsonl \
  --conditions awake sed \
  --save-timeseries timeseries_cache/

# Multi-subject batch
python dual_engine/anesthesia_signed_winding_pipeline.py \
  --subjects 1010 1016 1017 1022 1024 \
  --use-datalad \
  --out results_batch.jsonl \
  --conditions awake sed
```

## Method 2: Local BIDS Directory (Offline Testing)

For testing or when data is already available locally:

```bash
# Generate synthetic test data (for pipeline validation)
python validation/test_data_generator.py /tmp/test_bids

# Or use pre-downloaded data
python dual_engine/anesthesia_signed_winding_pipeline.py \
  --subjects 1010 1016 1017 \
  --data-dir /path/to/local/bids \
  --out results.jsonl \
  --conditions awake sed
```

## Method 3: Direct HTTPS Fallback

If datalad git-annex fails due to network restrictions, the pipeline will attempt direct HTTPS download from GitHub:

```bash
# The pipeline automatically tries this if datalad fails
# No configuration needed - it's automatic fallback
python dual_engine/anesthesia_signed_winding_pipeline.py \
  --subjects 1010 \
  --out results.jsonl
```

## Dataset Information

### ds005620 (Propofol Anesthesia EEG)

- **Subjects**: ~98
- **Channels**: 64 (10-20 montage)
- **Sampling Rate**: 5000 Hz
- **Conditions per subject**:
  - `awake`: Eyes-closed baseline (1 recording)
  - `sed`: Resting sedation (4 recordings)
  - `sed2`: Pre-awakening rest (4 recordings)
- **Total Recordings**: ~500
- **Data Type**: BrainVision (.vhdr/.vmrk/.eeg)

### ds000245 (Parkinson's fMRI)

```bash
datalad clone https://github.com/OpenNeuroDatasets/ds000245.git ds000245
# Used with dual_engine/fmri_tda_pipeline.py
```

### ds005237 (Transdiagnostic fMRI)

```bash
datalad clone https://github.com/OpenNeuroDatasets/ds005237.git ds005237
# Used with dual_engine/bold_phase_topology.py
```

### ds006072 (Psilocybin fMRI)

```bash
datalad clone https://github.com/OpenNeuroDatasets/ds006072.git ds006072
# Used with anesthesia pipeline (see research reports for validation)
```

## Pipeline Output

All pipelines write results in JSONL format (one JSON object per line):

```bash
# View results
cat results.jsonl | python -m json.tool | less

# Analyze results
python -c "
import json
with open('results.jsonl') as f:
    for line in f:
        r = json.loads(line)
        if r['status'] == 'ok':
            print(f\"{r['subject']} {r['condition']} {r['run']}: {len(r['bands'])} bands processed\")
"
```

## Performance Expectations

### ds005620 (98 subjects, 4 conditions each ≈ 500 recordings)

**Timing** (single CPU core, on modern hardware):
- Fetch via datalad: ~2-5 minutes (depends on internet speed)
- Preprocess per recording: ~1-3 minutes (ICA, CSD)
- Topology computation: ~0.5-1 minute
- Full cohort: ~50-100 hours for complete analysis

**Hardware Recommendations**:
- Minimum: 8 GB RAM (ICA on 64-channel EEG uses ~2-4 GB per subject)
- Recommended: 16+ GB RAM, 4+ CPU cores for parallel processing
- Disk: ~500 GB for raw data cache + timeseries outputs

## Reproducibility

Pipeline versions match exactly with published research reports:
- `REPORT_gate_ds000245_ds005620.md`: ds005620 signed topology validation (z≈-13, 80/80 pass rate)
- `REPORT_ds006072_psilocybin_persistence_topology.md`: Psilocybin acute→baseline trajectory
- `REPORT_ds005237_dmn_cen_signed_topology.md`: Transdiagnostic DMN/CEN analysis
- `REPORT_ds005237_stroop_cen_state_topology.md`: Task-state CEN activation

To reproduce these results:

```bash
# Fetch the exact datasets used
datalad clone https://github.com/OpenNeuroDatasets/ds005620.git
datalad clone https://github.com/OpenNeuroDatasets/ds005237.git
datalad clone https://github.com/OpenNeuroDatasets/ds006072.git

# Re-run pipelines with documented parameters
python dual_engine/anesthesia_signed_winding_pipeline.py \
  --use-datalad \
  --out reproduced_results.jsonl \
  --conditions awake sed
```

## Troubleshooting

### "datalad: command not found"
```bash
pip install datalad datalad-osf
```

### "git-annex: http proxy settings not used"
This warning is normal in restricted network environments. The pipeline will:
1. Try datalad/git-annex (may fail)
2. Fall back to HTTPS direct download
3. Fall back to local file copy if --data-dir specified

### "FileNotFoundError" when using datalad
Ensure the dataset is cloned first:
```bash
cd /path/to/ds005620
datalad get sub-<ID>/eeg/<filename>  # Fetch individual files
```

### Memory issues with large cohorts
Process subjects in smaller batches:
```bash
# Instead of all 98 at once, process 10-15 at a time
python dual_engine/anesthesia_signed_winding_pipeline.py \
  --subjects 1010 1016 1017 1022 1024 1033 1036 1037 1045 1046 \
  --use-datalad \
  --out batch1.jsonl

python dual_engine/anesthesia_signed_winding_pipeline.py \
  --subjects 1054 1055 1057 1060 1061 1062 1064 1067 1068 1071 \
  --use-datalad \
  --out batch2.jsonl
```

### Concatenate results from multiple runs
```bash
cat batch1.jsonl batch2.jsonl > all_results.jsonl

# Count successful runs
python -c "
import json
with open('all_results.jsonl') as f:
    successful = sum(1 for line in f if json.loads(line)['status'] == 'ok')
    print(f'Successfully processed: {successful} recordings')
"
```

## Citation

When using OpenNeuro datasets, cite:
- The dataset: Bajwa, Nilsen, et al. (2020). Temporal integration of topological signatures in brain oscillations. [Citation TBD]
- OpenNeuro: https://openneuro.org
- Datalad: https://www.datalad.org/
- Our analysis: See `REPORT_*.md` files in this repository

## Additional Resources

- OpenNeuro Dataset Browser: https://openneuro.org/
- Datalad Documentation: https://docs.datalad.org/
- BrainVision File Format: https://www.brainproducts.com/
- MNE-Python (processing): https://mne.tools/
- Research Papers: See `/uploads/` directory for published validation reports
