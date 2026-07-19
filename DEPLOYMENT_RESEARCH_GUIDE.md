# Deployment Research Guide
## Sequential Orchestration Framework for Real-World Validation

**Version:** 1.0  
**Updated:** 2026-07-19  
**Status:** Production Ready

---

## Overview

The Deployment Research Framework provides a sequential, research-focused execution environment for validating performance optimizations across three real neuroscience datasets:

1. **ds005620** — Anesthesia EEG (98 subjects, 51.2 Hz)
2. **ds000245** — fMRI Spectral TDA (45 subjects, 0.5 Hz)
3. **NKI-RS** — Fast-TR BOLD (1000 subjects available, TR=0.645s)

**Key Features:**
- ✅ Sequential orchestration with unified logging
- ✅ Hybrid error recovery (retry with fallback strategy)
- ✅ Research-focused analysis and comparative metrics
- ✅ Comprehensive reproducibility metadata (git, environment, timing)
- ✅ Publication-ready reports (Markdown + JSON)
- ✅ Integration with existing analysis pipelines

---

## Quick Start

### 1. Run Synthetic Validation (No Data Required)

Test the entire framework with synthetic data before running on real datasets:

```bash
# Validate all three pipelines with synthetic data
python scripts/test_deployment_synthetic.py
```

**Output:**
```
✓ ds005620 EEG (montage topology): 1.732s, speedup 4-8x
✓ ds000245 fMRI (spectral TDA): 0.871s, speedup 5-15x
✓ NKI-RS BOLD (fast-TR phase-topology): 0.335s, speedup 10x
```

### 2. Run Full Deployment (When Data Available)

Execute all three deployments sequentially:

```bash
# Run all three datasets (default)
python scripts/run_all_deployments.py --all

# Run specific datasets
python scripts/run_all_deployments.py --ds005620 --ds000245

# Run with custom data paths
python scripts/run_all_deployments.py --all \
  --data-root-ds005620 /path/to/ds005620 \
  --data-root-ds000245 /path/to/ds000245
```

**Output Structure:**
```
runs/<timestamp>/
├── run.log                    # Master execution log
├── metadata.json              # Git, environment, timing
├── deployments.json           # Summary of all deployments
├── ds005620/
│   ├── deployment.log
│   ├── metrics.csv
│   └── deployment_summary.json
├── ds000245/
│   ├── deployment.log
│   ├── spectral_tda_metrics.json
│   └── deployment_summary.json
└── nki_rs/
    ├── deployment.log
    ├── fast_tr_phase_topology_metrics.json
    └── deployment_summary.json
```

### 3. Analyze Results

Generate research report from deployment results:

```bash
# Generate markdown report (to stdout)
python scripts/analyze_deployments.py \
  --results-dir runs/20260719_120000

# Save report to file
python scripts/analyze_deployments.py \
  --results-dir runs/20260719_120000 \
  --output report.md
```

---

## Configuration

### Command-Line Options

```bash
python scripts/run_all_deployments.py [OPTIONS]

Dataset Selection:
  --all                Run all three datasets (default)
  --ds005620          Run ds005620 EEG deployment
  --ds000245          Run ds000245 fMRI deployment
  --nki-rs            Run NKI-RS fast-TR BOLD deployment

Data Paths:
  --data-root-ds005620 PATH     Data root for ds005620 (default: /data/ds005620)
  --data-root-ds000245 PATH     Data root for ds000245 (default: /data/ds000245)
  --cache-dir-nki-rs PATH       Cache directory for NKI-RS (default: ~/nki_rs_data)

Execution:
  --output-base DIR             Base directory for results (default: runs/)
  --max-subjects N              Limit to first N subjects per dataset (for testing)
  --error-recovery MODE         Error strategy: strict|lenient|hybrid (default: hybrid)
```

### Configuration File

Edit `config/deployment_research.yaml` to customize:
- Dataset parameters (sampling rate, subjects, duration)
- Expected speedup benchmarks
- Success criteria
- Research hypotheses
- Reproducibility tracking

---

## Research Workflows

### Workflow 1: Performance Benchmarking

Validate that optimizations deliver expected speedups:

```bash
# 1. Run all deployments
python scripts/run_all_deployments.py --all

# 2. Analyze speedup comparison
python scripts/analyze_deployments.py \
  --results-dir runs/20260719_120000 \
  --output speedup_report.md

# 3. Check report for speedup metrics
cat speedup_report.md | grep "Speedup"
```

**Research Questions Addressed:**
- Did speedups match estimates (13.8x, 17.6x, 10x)?
- Which optimization mechanism was most effective?
- Do results hold across dataset types (EEG vs fMRI)?

### Workflow 2: Hypothesis Testing

Test scientific theories using topology metrics across datasets:

```python
# After orchestrator completes:
from scripts.analyze_deployments import DeploymentAnalyzer

analyzer = DeploymentAnalyzer("runs/20260719_120000")
metrics = analyzer.generate_metrics_summary()

# Example: Test if Q_z distribution varies by dataset
import numpy as np
q_values = {
    dataset: np.random.normal(metrics[dataset].get('q_mean_mean', 0), 
                             metrics[dataset].get('q_mean_std', 1), 100)
    for dataset in metrics.keys()
}

# Statistical test (ANOVA)
from scipy import stats
f_stat, p_value = stats.f_oneway(*q_values.values())
print(f"Q_z distribution differs by dataset: p={p_value:.3f}")
```

**Example Hypotheses (from config/deployment_research.yaml):**
- H1: EEG spatial topology predicts anesthesia state
- H2: Topology metrics stable within modality
- H3: Spectral TDA resolves frequency bands better than time-averaged

### Workflow 3: Cross-Dataset Comparative Analysis

Integrate results from all three datasets for meta-analysis:

```python
from scripts.analyze_deployments import DeploymentAnalyzer

analyzer = DeploymentAnalyzer("runs/20260719_120000")

# Get comparative speedup
speedup_comparison = analyzer.generate_speedup_comparison()
print(f"Mean speedup: {speedup_comparison['summary']['mean_speedup']:.1f}x")

# Get topology metrics summary
metrics_summary = analyzer.generate_metrics_summary()

# Research: Do topology metrics correlate across modalities?
# Example: Does EEG Q_z correlate with fMRI persistence?
# (Requires per-subject level data integration)
```

### Workflow 4: Reproducibility Verification

Verify that results are reproducible and properly documented:

```bash
# 1. Run orchestrator twice with same data
python scripts/run_all_deployments.py --all
RUN1="runs/20260719_120000"

# (Wait a few minutes, run again)
python scripts/run_all_deployments.py --all
RUN2="runs/20260719_120130"

# 2. Compare metadata
diff <(jq .git "$RUN1/metadata.json") <(jq .git "$RUN2/metadata.json")
# Should be identical (same code version, branch, commit)

# 3. Compare metrics
# Speedup should be identical for same data
# Timing may vary by ±10% due to system load
```

---

## Error Recovery Strategies

### Strict Mode

**Behavior:** Stop immediately on first deployment failure

```bash
python scripts/run_all_deployments.py --all --error-recovery strict
```

**Use When:** Testing that all pipelines work correctly (CI/CD)

**Output:** Stops after first failed dataset, reports error

### Lenient Mode

**Behavior:** Skip failed deployments, continue with others

```bash
python scripts/run_all_deployments.py --all --error-recovery lenient
```

**Use When:** One dataset is unavailable, but others should still run

**Output:** Runs ds005620, skips ds000245 if unavailable, runs NKI-RS

### Hybrid Mode (Default)

**Behavior:** Attempt recovery (retry with smaller subset), then skip

```bash
python scripts/run_all_deployments.py --all --error-recovery hybrid
```

**Use When:** Some uncertainty about data availability or system resources

**Output:** 
1. Try deployment on full data
2. If fails, retry with `--max-subjects 10`
3. If still fails, skip with summary

---

## Output Formats

### Markdown Report (for publication)

```
# Deployment Results Research Report

Run ID: 20260719_120000
Environment: Python 3.11.15, NumPy 2.4.6, SciPy 1.13.0

## Speedup Comparison

| Dataset | Speedup | Measured | Baseline | Subjects |
|---------|---------|----------|----------|----------|
| ds005620 | 13.8x | 1.5s | 20.0s | 98 |
| ds000245 | 17.6x | 45.0s | 790.0s | 45 |
| nki_rs | 10.0x | 13.0m | 130.0m | 5 |
```

**Usage:**
- Papers and publications
- GitHub README
- Research presentations

### JSON Report (for analysis)

```json
{
  "run_id": "20260719_120000",
  "datasets": {
    "ds005620": {
      "speedup": 13.8,
      "subjects_processed": 98,
      "elapsed_seconds": 90.0
    }
  },
  "metadata": {
    "git_commit": "abc123...",
    "python_version": "3.11.15"
  }
}
```

**Usage:**
- Statistical analysis (R, Python)
- Data visualization
- Downstream integration

---

## Testing

### Unit Tests

```bash
# Test orchestrator and analyzer
pytest tests/test_deployments_integration.py -v
```

### Integration Tests (Full Workflow)

```bash
# Test with synthetic data
python scripts/test_deployment_synthetic.py

# Test orchestrator with mock data
pytest tests/test_deployments_integration.py::TestDeploymentOrchestrator -v

# Test analysis pipeline
pytest tests/test_deployments_integration.py::TestDeploymentAnalyzer -v
```

### End-to-End Test (Minimal Real Data)

```bash
# Run on subset: first 5 subjects per dataset
python scripts/run_all_deployments.py --all --max-subjects 5

# Should complete in <10 minutes with minimal data
```

---

## Troubleshooting

### Issue: "Data not found: /data/ds005620"

**Solution:** Specify correct data root
```bash
python scripts/run_all_deployments.py --all \
  --data-root-ds005620 /home/datasets/ds005620
```

### Issue: "nibabel not installed"

**Solution:** Install optional dependencies
```bash
pip install nibabel scipy ripser
```

### Issue: "Deployment timed out after 3600s"

**Solution:** Reduce dataset size or increase timeout
```bash
# Test with first 10 subjects
python scripts/run_all_deployments.py --all --max-subjects 10
```

### Issue: "No space left on device"

**Solution:** Check disk space and clean old runs
```bash
df -h
rm -rf runs/20260701_*  # Remove old runs
```

---

## Advanced Usage

### Custom Analysis

```python
from scripts.analyze_deployments import DeploymentAnalyzer
from pathlib import Path

# Load results
analyzer = DeploymentAnalyzer("runs/20260719_120000")

# Access raw deployment data
speedup = analyzer.generate_speedup_comparison()
metrics = analyzer.generate_metrics_summary()

# Custom analysis
for dataset, info in speedup["datasets"].items():
    print(f"{dataset}: {info['speedup']:.1f}x speedup")

# Export for external analysis
import json
with open("export.json", "w") as f:
    json.dump({
        "speedup": speedup,
        "metrics": metrics,
    }, f, indent=2)
```

### Parallel Runs (Multiple Datasets)

```bash
# Run ds005620 in background
nohup python scripts/run_all_deployments.py --ds005620 > ds005620.log 2>&1 &

# Run ds000245 in parallel
nohup python scripts/run_all_deployments.py --ds000245 > ds000245.log 2>&1 &

# Monitor progress
tail -f ds005620.log
tail -f ds000245.log
```

### Comparative Analysis Across Runs

```bash
# Run 1: baseline
python scripts/run_all_deployments.py --all
RUN1=$(ls -td runs/*/ | head -1 | tr -d '/')

# Run 2: after code change
# (modify code...)
python scripts/run_all_deployments.py --all
RUN2=$(ls -td runs/*/ | head -1 | tr -d '/')

# Compare speedups
python -c "
import json
with open('$RUN1/deployments.json') as f:
    r1 = json.load(f)
with open('$RUN2/deployments.json') as f:
    r2 = json.load(f)

for dataset in r1['datasets'].keys():
    s1 = r1['datasets'][dataset]['speedup']
    s2 = r2['datasets'][dataset]['speedup']
    improvement = (s2 - s1) / s1 * 100
    print(f'{dataset}: {s1:.1f}x → {s2:.1f}x ({improvement:+.1f}%)')
"
```

---

## Documentation

- **Performance Report:** `REPORT_performance_optimization_validation.md`
- **Deployment Plan:** `DEPLOYMENT_PLAN_Real_Data_Validation.md`
- **Deployment Execution:** `DEPLOYMENT_EXECUTION_REPORT.md`
- **Configuration:** `config/deployment_research.yaml`

---

## Support & Contributing

For issues or questions:
1. Check `runs/<timestamp>/run.log` for detailed error messages
2. Run synthetic tests to verify environment setup
3. Review configuration in `config/deployment_research.yaml`

For modifications:
- Update research hypotheses in config/deployment_research.yaml
- Add new analysis functions to `scripts/analyze_deployments.py`
- Add new tests to `tests/test_deployments_integration.py`

---

## Citation

If you use this framework in your research, please cite:

```bibtex
@software{deployment_research_2026,
  title={Sequential Deployment Orchestration Framework for Neuroscience Optimization Validation},
  author={[Your Name]},
  year={2026},
  url={https://github.com/ChristianV997/ScienceR-Dsim}
}
```

---

**Version:** 1.0  
**Last Updated:** 2026-07-19  
**Status:** Production Ready ✅
