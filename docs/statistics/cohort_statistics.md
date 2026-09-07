# Paired-Cohort Descriptive and Non-Parametric Statistics Layer

## 1. Overview and Scientific Motivation

In topological data analysis (TDA) and empirical electrophysiology cohorts (e.g. comparing `awake` vs. `sed2` or pre- vs. post-intervention states), downstream falsification pipelines require a standardized, typed statistical layer to quantify within-subject condition shifts across key topological and physical metrics:
- **$\beta_1$ Graph Persistence**: Betti-1 homology counting 1-dimensional topological cycles in functional or phase synchronization graphs.
- **Persistence Landscape Area**: Integrated norm of the persistence landscape measuring topological signal magnitude.
- **Winding Number / Phase Curvature**: Topological phase trajectory winding across multi-channel cycles.
- **Spatial Topological Charge ($Q_{\text{spatial}}$)**: Defect charge computed using 3D sensor montage geometry.

This module provides descriptive moments, paired difference distributions, effect size estimations, confidence intervals, non-parametric hypothesis testing (Wilcoxon signed-rank test), and family-wise multiplicity adjustments.

---

## 2. Mathematical Framework

### Descriptive Moments
For a sample of $N$ valid paired observations $(A_i, B_i)$ ($i = 1, \dots, N$):
- **Mean**: $\bar{x} = \frac{1}{N} \sum_{i=1}^N x_i$
- **Median**: $\text{med}(x) = \text{quantile}(x, 0.5)$
- **Sample Variance**: $s^2 = \frac{1}{N - 1} \sum_{i=1}^N (x_i - \bar{x})^2$ ($N \ge 2$, with $ddof=1$)
- **Standard Error of the Mean**: $\text{SE} = \frac{s}{\sqrt{N}}$

### Paired Differences and Effect Size
The within-subject paired difference is defined as:
$$d_i = B_i - A_i$$

- **Mean Difference**: $\bar{d} = \frac{1}{N} \sum_{i=1}^N d_i = \bar{B} - \bar{A}$
- **Median Difference**: $\text{med}(d) = \text{quantile}(d, 0.5)$
- **Sample Standard Deviation of Differences**: $s_d = \sqrt{\frac{1}{N - 1} \sum_{i=1}^N (d_i - \bar{d})^2}$
- **Standard Error of Differences**: $\text{SE}_d = \frac{s_d}{\sqrt{N}}$
- **Paired Cohen's $d_z$**:
  $$d_z = \frac{\bar{d}}{s_d} \quad (s_d > 0)$$
- **95% Confidence Interval for Mean Difference**:
  $$\text{CI}_{95\%} = \left[ \bar{d} - t_{0.975, N-1} \cdot \text{SE}_d, \; \bar{d} + t_{0.975, N-1} \cdot \text{SE}_d \right]$$

### Non-Parametric Hypothesis Testing: Wilcoxon Signed-Rank Test
When $N \ge \text{min\_pairs}$ (default: 2) and differences are not all zero, the non-parametric Wilcoxon signed-rank test is evaluated:
- **Null Hypothesis ($H_0$)**: The distribution of within-subject differences $d_i = B_i - A_i$ is symmetric around zero.
- **Alternative Hypotheses ($H_1$)**:
  - `two-sided`: The distribution of differences is not symmetric around zero.
  - `greater`: Condition B systematically exceeds Condition A ($d_i > 0$).
  - `less`: Condition B is systematically less than Condition A ($d_i < 0$).
- **Zero-Difference Handling**: Explicitly governed by `zero_method="wilcox"`. If all differences are identically zero ($d_i = 0$ for all $i$), the status is reported as `all_paired_differences_zero` with $W = 0.0$ and $p = 1.0$.

### Multiplicity Corrections
When evaluating multiple topological metrics simultaneously, p-values are adjusted across the family of $m$ tests:
1. **Holm-Bonferroni (`holm`, default)**: Step-down procedure controlling the family-wise error rate (FWER) without requiring independent tests. For sorted $p_{(1)} \le \dots \le p_{(m)}$:
   $$p^{\text{adj}}_{(i)} = \min\left(1.0, \; \max_{j \le i} \left( (m - j + 1) \cdot p_{(j)} \right)\right)$$
2. **Bonferroni (`bonferroni`)**: Single-step FWER control:
   $$p^{\text{adj}}_i = \min\left(1.0, \; m \cdot p_i\right)$$
3. **Benjamini-Hochberg (`fdr_bh`)**: Controls the false discovery rate (FDR) under positive dependence:
   $$p^{\text{adj}}_{(i)} = \min\left(1.0, \; \min_{j \ge i} \left( \frac{m}{j} \cdot p_{(j)} \right)\right)$$
4. **None (`none`)**: Reports unadjusted raw p-values.

---

## 3. Scientific Rules & Guardrails

1. **Significance Separation**: Descriptive moments describe the sample distribution; inferential tests require statistical power ($N \ge \text{min\_pairs}$) and SciPy. Significance is **never inferred** from a missing or underpowered test.
2. **No Subject Fabrication**: Insufficient paired cohorts are reported explicitly; synthetic pairs are **never substituted** for empirical subjects.
3. **No Silent Drops**: Any subject with missing or non-finite metric values is logged in `exclusion_records` with exact subject identifier and rejection reason.
4. **Finite Input Enforcement**: Non-finite numbers (`NaN`, `Inf`, `-Inf`) are rejected and excluded with `non_finite_metric_value` provenance.
5. **Topological Metric Demarcation**: $\beta_1$ represents 1D persistent graph homology; it must **never be equated** with physical spatial topological charge ($Q_{\text{spatial}}$), which requires physical 3D montage electrode coordinates.
6. **No Formal Bayes Factor Claim**: This module computes descriptive and frequentist non-parametric statistics; it does not produce formal Bayes factors or bypass the repository's Bayesian falsification engine.
7. **Strict JSON Null Compliance**: Unavailable values serialize strictly to JSON `null` (never `"NaN"`, `"Infinity"`, or fabricated sentinel values).

---

## 4. CLI Reference

### Command Syntax
```bash
python scripts/summarize_cohort_statistics.py \
  --input cohort_metrics.json \
  --output cohort_statistics.json \
  --correction holm \
  --alternative two-sided \
  --min-pairs 2
```

### CLI Arguments

| Flag | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `--input`, `-i` | Path | Required | Path to input metrics JSON or CSV. |
| `--output`, `-o` | Path | Required | Path to output statistics JSON. |
| `--correction`, `-c` | str | `holm` | Multiplicity method (`holm`, `bonferroni`, `fdr_bh`, `none`). |
| `--alternative`, `-a` | str | `two-sided` | Hypothesis direction (`two-sided`, `greater`, `less`). |
| `--min-pairs` | int | `2` | Minimum valid pairs threshold for inferential tests. |
| `--metrics` | str | `None` | Optional comma-separated list of metrics to restrict evaluation to. |
| `--csv-output` | Path | `None` | Optional path for tabular summary CSV. |
| `--is-synthetic` | flag | `False` | Declares that input data originates from synthetic fixtures. |
| `--provenance-status` | str | `empirical` | Origin label (`empirical`, `synthetic_fixture`, `incomplete_provenance`). |
| `--strict` | flag | `False` | Exits non-zero (code 2) if execution errors occur or no valid pairs exist. |

---

## 5. Output Artifact Schema

### JSON Schema (`cohort_statistics.json`)
```json
{
  "schema": "NeuroTopologySim.CohortStatisticsReport.v1",
  "dataset_id": "ds005620",
  "condition_a_label": "awake",
  "condition_b_label": "sed2",
  "total_subjects_evaluated": 16,
  "is_synthetic": false,
  "provenance_status": "empirical",
  "multiplicity_method": "holm",
  "min_pairs": 2,
  "checksum": "d5a8...",
  "metrics": {
    "beta_1": {
      "metric_name": "beta_1",
      "valid_pairs_count": 16,
      "excluded_pairs_count": 0,
      "exclusion_records": [],
      "condition_a_stats": {
        "n": 16,
        "mean": 14.25,
        "median": 14.0,
        "variance": 3.13,
        "standard_error": 0.44
      },
      "condition_b_stats": {
        "n": 16,
        "mean": 18.50,
        "median": 18.0,
        "variance": 4.26,
        "standard_error": 0.51
      },
      "difference_stats": {
        "values": [4.0, 4.5, 3.8, ...],
        "mean": 4.25,
        "median": 4.1,
        "variance": 1.20,
        "standard_error": 0.27,
        "median_difference": 4.1,
        "cohens_d_z": 3.88,
        "ci_95": [3.67, 4.83]
      },
      "inferential_stats": {
        "test_name": "Wilcoxon signed-rank test",
        "status": "computed",
        "statistic": 0.0,
        "p_value": 0.00048,
        "p_adjusted": 0.00192,
        "alternative": "two-sided",
        "zero_method": "wilcox",
        "notes": "Computed non-parametric test (two-sided, zero_method=wilcox)."
      }
    }
  },
  "scientific_notes": [...]
}
```

### CSV Summary (`cohort_statistics.csv`)
Columns:
`metric,valid_pairs,excluded_pairs,mean_a,median_a,var_a,se_a,mean_b,median_b,var_b,se_b,mean_diff,median_diff,cohens_d_z,ci95_lower,ci95_upper,wilcoxon_stat,p_value,p_adjusted,test_status`
