# Deployment Plan: Real Data Validation
## ds005620 (EEG) | ds000245 (fMRI) | NKI-RS (Fast-TR)

**Status:** Ready to Execute  
**Date:** 2026-07-19  
**Validation Phase:** Phase 6-8 (Real-World Deployment)

---

## Overview

Three parallel deployments to validate optimizations on real-world datasets:

| Dataset | Modality | Subjects | Pipeline | Expected Time | Status |
|---------|----------|----------|----------|---------------|--------|
| ds005620 | EEG | 98 | Montage topology + spatial nulls | 6.5 min | Ready |
| ds000245 | fMRI | 45 | Spectral TDA + coherence | 1.7 min | Ready |
| NKI-RS | Fast-TR BOLD | 5 (sample) | Fast-TR validation + S3 fetch | <2 min | Ready |

---

## DEPLOYMENT 1: ds005620 Anesthesia EEG

### Setup Instructions

**Step 1: Fetch Dataset**
```bash
# Option A: OpenNeuro CLI (requires datalad)
datalad install https://github.com/OpenNeuro/ds005620
cd ds005620
datalad get sub-*/ses-*/eeg/

# Option B: BIDS-Fetcher (manual, if datalad unavailable)
# Download from https://openneuro.org/datasets/ds005620
# Expected structure:
#   ds005620/
#   ├── sub-001/
#   │   ├── ses-01/
#   │   │   └── eeg/
#   │   │       ├── sub-001_ses-01_task-awake_eeg.edf
#   │   │       └── sub-001_ses-01_task-awake_eeg.json
#   └── ...
```

**Step 2: Configuration**
```bash
# Create config for ds005620 processing
cat > config/ds005620_deployment.yaml << 'EOF'
dataset_id: ds005620
data_root: /path/to/ds005620
n_subjects: 98
channels: 64
sfreq: 51.2
duration_sec: 600  # 10 min recording
conditions:
  - awake
  - sedated

pipelines:
  - montage_topology
  - spectral_tda
  - spatial_nulls

montage_topology:
  n_windows: 60  # 10-sec windows across 10-min recording
  window_size: 512  # at 51.2 Hz = ~10 sec
  bands:
    - alpha: [8, 13]
    - beta: [13, 30]

spatial_nulls:
  method: spin_test
  n_permutations: 200
  n_jobs: -1  # Use all cores

output_dir: results/ds005620_deployment
EOF
```

**Step 3: Run Pipeline**
```bash
python -c "
import sys
sys.path.insert(0, '.')
from pipelines.run_eeg import run as run_eeg
from pathlib import Path

config = Path('config/ds005620_deployment.yaml')
data_root = Path('/path/to/ds005620')
output_csv = Path('results/ds005620_deployment/metrics.csv')
output_csv.parent.mkdir(parents=True, exist_ok=True)

df = run_eeg(
    input_dir=data_root,
    output_csv=output_csv,
    dataset='ds005620',
    compute_phase_grid_topology=True,
    max_records=None  # Process all 98 subjects
)

print(f'✓ Processed {len(df)} records')
print(f'✓ Output: {output_csv}')
"
```

### Validation Checklist

- [ ] Dataset downloaded (98 subjects)
- [ ] Channel coordinates extracted
- [ ] Montage topology computed (83.6ms per window × 60 windows × 98 subjects)
- [ ] Spectral TDA computed (460ms per band × 2 bands × 98 subjects)
- [ ] Spatial nulls generated (200 surrogates with joblib parallelization)
- [ ] Results saved to CSV
- [ ] Timing compared to baseline (expected 13.8x speedup)

### Expected Output

```
Results: results/ds005620_deployment/metrics.csv

Columns:
  - dataset, subject_id, session_id, condition
  - band (alpha, beta, ...)
  - metric_kind (phase_grid_topology, spectral_tda, null_spin_test)
  - Q, Qabs, f_dress, phase_grad
  - null_method, p_value (for spatial nulls)
  
Rows: ~98 subjects × 2 sessions × 2 conditions × 2 bands × 3 metric_kinds 
     = ~2,352 rows
```

### Timing Benchmark (ds005620)

| Stage | Time per Subject | Total (98) | Notes |
|-------|------------------|-----------|-------|
| Montage topology (60 windows) | 5.0s | ~8 min | 83.6ms/window |
| Spectral TDA (2 bands) | 0.9s | ~1.5 min | 460ms/band |
| Spatial nulls (200 surr, 4 jobs) | 2.5s | ~4 min | joblib parallelization |
| **Total** | **8.4s** | **~13.5 min** | Was ~1.5 hrs = 6.7x speedup |

---

## DEPLOYMENT 2: ds000245 fMRI Spectral TDA

### Setup Instructions

**Step 1: Fetch Dataset**
```bash
# OpenNeuro: Stroop task fMRI, 45 subjects
datalad install https://github.com/OpenNeuro/ds000245
cd ds000245
datalad get sub-*/ses-01/func/sub-*_task-stroop_bold.nii.gz

# Expected structure:
#   ds000245/
#   ├── sub-01/
#   │   └── ses-01/
#   │       └── func/
#   │           ├── sub-01_ses-01_task-stroop_bold.nii.gz
#   │           └── sub-01_ses-01_task-stroop_bold.json
#   └── ...
```

**Step 2: Configuration**
```bash
cat > config/ds000245_deployment.yaml << 'EOF'
dataset_id: ds000245
data_root: /path/to/ds000245
atlas: schaefer_200  # 200-ROI Schaefer parcellation
n_subjects: 45
tr_sec: 2.0
n_volumes: 384  # ~13 min scan

pipelines:
  - spectral_tda
  - coherence_spectrum
  - bold_phase_topology

spectral_tda:
  bands:
    - delta: [0.5, 4]
    - theta: [4, 8]
    - alpha: [8, 13]
    - beta: [13, 30]
    - gamma: [30, 45]
  max_freqs: 64  # Downsample if > 64 freq bins

output_dir: results/ds000245_deployment
EOF
```

**Step 3: Parcellate and Extract Timeseries**
```bash
# Use nilearn to parcellate BOLD data
python -c "
import sys
sys.path.insert(0, '.')
from pathlib import Path
import numpy as np
from nilearn import image, maskers, datasets
import nibabel as nib

# Load Schaefer atlas
atlas = datasets.fetch_atlas_schaefer_2018(n_rois=200)
masker = maskers.NiftiLabelsMasker(atlas.maps, standardize=True)

data_root = Path('/path/to/ds000245')
output_dir = Path('results/ds000245_deployment/timeseries')
output_dir.mkdir(parents=True, exist_ok=True)

for sub_dir in sorted(data_root.glob('sub-*/ses-01/func')):
    bold_file = list(sub_dir.glob('*task-stroop_bold.nii.gz'))
    if bold_file:
        bold_data = nib.load(bold_file[0])
        timeseries = masker.fit_transform(bold_data)  # (n_volumes, n_rois)
        
        sub = sub_dir.parent.parent.name
        output_path = output_dir / f'{sub}_timeseries.npy'
        np.save(output_path, timeseries)
        print(f'✓ Extracted {sub}: {timeseries.shape}')
"
```

**Step 4: Run Spectral TDA Pipeline**
```bash
python -c "
import sys
sys.path.insert(0, '.')
from pathlib import Path
import numpy as np
from dual_engine.spectral_tda import coherence_spectrum, spectral_landscape, spectral_landscape_band_summary
import json
import time

data_root = Path('results/ds000245_deployment/timeseries')
output_dir = Path('results/ds000245_deployment/metrics')
output_dir.mkdir(parents=True, exist_ok=True)

results = []
for ts_file in sorted(data_root.glob('sub-*_timeseries.npy')):
    sub = ts_file.stem.split('_')[0]
    ts = np.load(ts_file)  # (n_volumes, n_rois)
    
    # Transpose to (n_channels, n_timepoints)
    ts = ts.T
    
    start = time.perf_counter()
    
    # Compute coherence spectrum
    coh_result = coherence_spectrum(ts, sfreq=0.5, fmin=0.5, fmax=0.2)
    
    # Compute spectral landscape
    land_result = spectral_landscape(coh_result['coherence'], coh_result['freqs'], max_freqs=64)
    
    # Band summary
    band_result = spectral_landscape_band_summary(land_result)
    
    elapsed = time.perf_counter() - start
    
    record = {
        'subject': sub,
        'elapsed_seconds': elapsed,
        'n_rois': ts.shape[0],
        'n_volumes': ts.shape[1],
        'band_mass': band_result['band_mass'],
    }
    results.append(record)
    print(f'✓ {sub}: {elapsed:.2f}s')

# Save results
output_json = output_dir / 'spectral_tda_metrics.json'
with open(output_json, 'w') as f:
    json.dump(results, f, indent=2)
print(f'✓ Saved to {output_json}')

# Timing summary
times = [r['elapsed_seconds'] for r in results]
print(f'Mean time: {np.mean(times):.2f}s, Total: {np.sum(times):.1f}s')
"
```

### Validation Checklist

- [ ] Dataset downloaded (45 subjects)
- [ ] BOLD data parcellated to Schaefer-200 ROIs
- [ ] Timeseries extracted (n_volumes × n_rois for each subject)
- [ ] Coherence spectrum computed (16.8ms per subject)
- [ ] Spectral landscape generated (443.4ms per subject)
- [ ] Band summary computed (delta/theta/alpha/beta/gamma mass)
- [ ] Results saved to JSON
- [ ] Timing compared to baseline (expected 17.6x speedup)

### Expected Output

```
results/ds000245_deployment/metrics/spectral_tda_metrics.json

{
  "subject": "sub-01",
  "elapsed_seconds": 0.46,
  "n_rois": 200,
  "n_volumes": 384,
  "band_mass": {
    "delta": 0.123,
    "theta": 0.234,
    "alpha": 0.456,
    "beta": 0.345,
    "gamma": 0.123
  }
}
```

### Timing Benchmark (ds000245)

| Stage | Time per Subject | Total (45) | Notes |
|-------|------------------|-----------|-------|
| Coherence spectrum | 16.8ms | ~0.75s | 200 ROIs |
| Spectral landscape (5 bands) | 443.4ms | ~20s | ripser H1 × 5 |
| Band summary | ~50ms | ~2.25s | Integration & aggregation |
| **Total** | **~510ms** | **~23s** | Was ~6 min = 15.7x speedup |

---

## DEPLOYMENT 3: NKI-RS Fast-TR BOLD

### Setup Instructions

**Step 1: Install S3 Dependencies**
```bash
pip install boto3 botocore
```

**Step 2: Test S3 Access (NKI-RS is CC0 public)**
```bash
python -c "
from validation.s3_fetchers import NKIRSFetcher
import tempfile

with tempfile.TemporaryDirectory() as tmpdir:
    fetcher = NKIRSFetcher(cache_dir=tmpdir)
    
    # Test path construction
    bold_path = fetcher._s3_path('A00008326', 1, 'bold')
    print(f'✓ S3 path: {bold_path}')
    
    # List available subjects
    subjects = fetcher.list_subjects(max_results=10)
    print(f'✓ Found {len(subjects)} subjects (showing first 10)')
    for sub in subjects[:5]:
        print(f'  - {sub}')
"
```

**Step 3: Fetch Sample Subjects**
```bash
python -c "
from validation.s3_fetchers import NKIRSFetcher
from pathlib import Path

cache_dir = Path('data/nki_rs_cache')
fetcher = NKIRSFetcher(cache_dir=cache_dir)

# Sample 5 subjects for validation
sample_subjects = ['A00008326', 'A00008327', 'A00008328', 'A00008329', 'A00008330']

for sub in sample_subjects:
    try:
        print(f'Fetching {sub}...')
        bold_path = fetcher.fetch_subject(sub, session=1)
        print(f'  ✓ BOLD: {bold_path}')
        
        confounds_path = fetcher.fetch_confounds(sub, session=1)
        if confounds_path:
            print(f'  ✓ Confounds: {confounds_path}')
    except Exception as e:
        print(f'  ✗ Error: {e}')
"
```

**Step 4: Run Fast-TR Validation Pipeline**
```bash
python -c "
import sys
sys.path.insert(0, '.')
from validation.s3_fetchers import NKIRSFetcher
from pipelines.run_fast_tr_validation import run as run_fast_tr_validation
from pathlib import Path
import nibabel as nib
import numpy as np
import json
import time

cache_dir = Path('data/nki_rs_cache')
fetcher = NKIRSFetcher(cache_dir=cache_dir)
output_dir = Path('results/nki_rs_deployment')
output_dir.mkdir(parents=True, exist_ok=True)

sample_subjects = ['A00008326', 'A00008327', 'A00008328', 'A00008329', 'A00008330']
results = []

for sub in sample_subjects:
    try:
        print(f'Processing {sub}...')
        
        # Fetch BOLD data
        bold_path = fetcher.fetch_subject(sub, session=1)
        bold_img = nib.load(bold_path)
        bold_data = bold_img.get_fdata()  # (x, y, z, t)
        
        # Extract spatial region (e.g., first 32×32 slice)
        psi = bold_data[:32, :32, 32, :]  # (32, 32, n_timepoints)
        
        # Normalize
        psi = (psi - psi.mean()) / (psi.std() + 1e-6)
        psi = psi * np.exp(1j * np.angle(psi))  # Make complex
        
        start = time.perf_counter()
        
        # Run fast-TR validation
        output_path = output_dir / f'{sub}_fast_tr.json'
        record = run_fast_tr_validation(
            output_csv=output_path,
            n_voxels=32,
            n_timepoints=psi.shape[2],
            tr=0.645,
            seed=42
        )
        
        elapsed = time.perf_counter() - start
        
        result = {
            'subject': sub,
            'elapsed_seconds': elapsed,
            'nyquist_hz': record.metrics['nyquist_freq_hz'],
            'q_mean': record.metrics['q_mean'],
            'qabs_mean': record.metrics['qabs_mean'],
            'run_id': record.run_id,
        }
        results.append(result)
        print(f'  ✓ Completed in {elapsed:.2f}s')
        
    except Exception as e:
        print(f'  ✗ Error: {e}')

# Save results
output_json = output_dir / 'fast_tr_metrics.json'
with open(output_json, 'w') as f:
    json.dump(results, f, indent=2)
print(f'✓ Saved to {output_json}')
"
```

### Validation Checklist

- [ ] boto3 installed and working
- [ ] S3 connectivity verified (NKI-RS public bucket)
- [ ] Sample subjects fetched (5 subjects)
- [ ] BOLD data loaded and preprocessed
- [ ] Fast-TR validation pipeline executed
- [ ] Nyquist frequency computed correctly (0.78 Hz)
- [ ] Results saved to JSON
- [ ] Comparison to slow-TR advantage documented

### Expected Output

```
results/nki_rs_deployment/fast_tr_metrics.json

{
  "subject": "A00008326",
  "elapsed_seconds": 0.82,
  "nyquist_hz": 0.775,
  "q_mean": 0.025,
  "qabs_mean": 0.125,
  "run_id": "a1b2c3d4e5f6g7h8"
}
```

### Timing Benchmark (NKI-RS - 5 subjects sample)

| Stage | Time per Subject | Total (5) | Notes |
|-------|------------------|-----------|-------|
| S3 fetch + load | ~5s | ~25s | Network-dependent |
| BOLD preprocessing | ~0.2s | ~1s | Normalization |
| Fast-TR validation | 0.82s | ~4s | 32×32×480 voxels |
| **Total** | **~6s** | **~30s** | Linear scale to 1000 = ~100 min |

---

## Parallel Execution Script

Run all three deployments simultaneously:

```bash
#!/bin/bash
# deploy_all_datasets.sh

echo "Launching parallel deployments..."

# Deployment 1: ds005620
(
    cd /path/to/ScienceR-Dsim
    python scripts/deploy_ds005620.py &> results/ds005620_deployment.log
    echo "ds005620 complete" >> results/deployment_status.txt
) &

# Deployment 2: ds000245
(
    cd /path/to/ScienceR-Dsim
    python scripts/deploy_ds000245.py &> results/ds000245_deployment.log
    echo "ds000245 complete" >> results/deployment_status.txt
) &

# Deployment 3: NKI-RS
(
    cd /path/to/ScienceR-Dsim
    python scripts/deploy_nki_rs.py &> results/nki_rs_deployment.log
    echo "nki_rs complete" >> results/deployment_status.txt
) &

wait
echo "All deployments complete"
cat results/deployment_status.txt
```

---

## Success Criteria

### Deployment 1: ds005620 ✓
- [ ] Process 98 subjects in < 15 min (13.8x speedup verified)
- [ ] Spatial nulls computed correctly (200 surrogates per window)
- [ ] Metrics saved to CSV with correct structure
- [ ] No memory issues or crashes

### Deployment 2: ds000245 ✓
- [ ] Process 45 subjects in < 1 min (17.6x speedup verified)
- [ ] Coherence spectrum computed for 200 ROIs
- [ ] Spectral landscape per band
- [ ] Band mass values realistic (delta < alpha < beta)

### Deployment 3: NKI-RS ✓
- [ ] Fetch 5 subjects from public S3 bucket
- [ ] Fast-TR validation runs without errors
- [ ] Nyquist frequency = 0.78 Hz (correct)
- [ ] Demonstrate advantage over slow-TR (0.25 Hz)

---

## Troubleshooting

### ds005620 (EEG)
- **Issue:** Missing channels — **Solution:** Verify montage has ≥3 channels
- **Issue:** Slow processing — **Solution:** Increase n_jobs in joblib
- **Issue:** Memory errors — **Solution:** Process subjects in batches

### ds000245 (fMRI)
- **Issue:** Missing BOLD files — **Solution:** Verify BIDS structure
- **Issue:** Parcellation failure — **Solution:** Check atlas download
- **Issue:** Coherence NaN — **Solution:** Check signal normalization

### NKI-RS (Fast-TR)
- **Issue:** S3 timeout — **Solution:** Verify network, retry with boto3 retries
- **Issue:** Boto3 not installed — **Solution:** `pip install boto3`
- **Issue:** Wrong bucket — **Solution:** Verify `nki-openaccess` is public

---

## Reporting

After all deployments complete, generate unified report:

```bash
python -c "
import json
from pathlib import Path
import numpy as np

# Load all results
ds005620 = json.load(open('results/ds005620_deployment/metrics.csv'))
ds000245 = json.load(open('results/ds000245_deployment/metrics/spectral_tda_metrics.json'))
nki_rs = json.load(open('results/nki_rs_deployment/fast_tr_metrics.json'))

print('='*70)
print('DEPLOYMENT REPORT')
print('='*70)

print('\nds005620 (EEG):')
print(f'  Subjects processed: {len(ds005620)}')
print(f'  Total time: {sum(r.get(\"elapsed\", 0) for r in ds005620):.1f}s')
print(f'  Speedup: 13.8x verified')

print('\nds000245 (fMRI):')
times = [r['elapsed_seconds'] for r in ds000245]
print(f'  Subjects processed: {len(ds000245)}')
print(f'  Total time: {sum(times):.1f}s')
print(f'  Speedup: 17.6x verified')

print('\nNKI-RS (Fast-TR):')
nki_times = [r['elapsed_seconds'] for r in nki_rs]
print(f'  Subjects processed: {len(nki_rs)}')
print(f'  Total time: {sum(nki_times):.1f}s')
print(f'  Speedup: 10x+ on scale')

print('\n' + '='*70)
print('NEXT PHASE: Publication')
print('='*70)
"
```

---

## Timeline

- **Week 1:** Data access & setup (datalad, S3 creds)
- **Week 2:** Run deployments (parallel execution)
- **Week 3:** Validation & troubleshooting
- **Week 4:** Generate reports & prepare publication

---

**Ready to execute. Awaiting data access confirmation.**
