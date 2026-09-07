# Paired-Cohort Statistics and Effect-Size Validation

## 1. Overview

Within-subject experimental paradigms (such as crossover trials, pre-post interventions, or paired drug-vs-placebo conditions) generate repeated measures from the same biological or computational units. Analyzing repeated-measures designs using independent two-sample formulas (such as two-sample Student's $t$-tests or two-sample pooled Cohen's $d$) conflates inter-subject baseline variance with true intra-subject treatment shifts, biasing standard errors and distorting effect-size estimations.

The `analysis.cohort_statistics` package provides a typed, deterministic, and verifiable within-subject paired statistics and effect-size validation framework for `NeuroTopology-Sim`.

### Key Capabilities

- **Exact Pairing Guarantees**: Deterministic subject identifier sorting and bijective condition matching ($A_i$ and $B_i$ for each subject $i$).
- **Non-Silent Exclusions**: Explicit recording of every exclusion with machine-readable reasons (`missing_condition`, `non_finite_value`, `subject_error`, `duplicate_subject_id`). Insufficient or missing data are never silently dropped.
- **Scientifically Grounded Effect Sizes**: Implements paired Cohen's $d_z$ ($d_z = \bar{d} / s_d$) and rank-biserial correlation $r = (W^+ - W^-) / (W^+ + W^-)$ for non-parametric rank tests.
- **Multiple Testing Corrections**: Holm-Bonferroni step-down, Bonferroni, and Benjamini-Hochberg False Discovery Rate (FDR-BH), correctly excluding non-testable metrics from the hypothesis count $m$ while preserving exact positional alignment.
- **Strict RFC-8259 JSON Compliance**: Guaranteed omission of non-finite literals (`NaN`, `Infinity`, `-Infinity`); unavailable numerical estimates are strictly serialized as JSON `null`.
- **Tamper-Evident Integrity Checksums**: SHA-256 checksum computed over canonical metric payloads to detect mutation or data drift.
- **Strict Scientific Guardrails**: Explicit provenance tagging (`empirical`, `synthetic_demo`, `incomplete_provenance`) and disclaimers prohibiting clinical or ontology claims.

---

## 2. Mathematical Foundations

### 2.1 Paired Differences
For subjects $i \in \{1, \dots, n\}$ with measurements under Condition $A$ ($x_{A,i}$) and Condition $B$ ($x_{B,i}$):

$$d_i = x_{A,i} - x_{B,i}$$

Mean paired difference:
$$\bar{d} = \frac{1}{n} \sum_{i=1}^{n} d_i$$

Sample standard deviation of differences ($ddof = 1$):
$$s_d = \sqrt{\frac{1}{n - 1} \sum_{i=1}^{n} (d_i - \bar{d})^2}$$

Standard error of the mean difference:
$$SE_d = \frac{s_d}{\sqrt{n}}$$

### 2.2 Paired Effect Size (Cohen's $d_z$)
For repeated-measures designs, the appropriate standardized mean difference is Cohen's $d_z$:

$$d_z = \frac{\bar{d}}{s_d}$$

> [!IMPORTANT]
> The independent-samples pooled standard deviation formula $s_{\text{pooled}} = \sqrt{\frac{(n_A - 1)s_A^2 + (n_B - 1)s_B^2}{n_A + n_B - 2}}$ does NOT account for within-subject covariance $\text{Cov}(A, B)$ and is mathematically invalid for paired contrasts.

### 2.3 Non-Parametric Rank-Biserial Correlation ($r$)
For non-parametric comparisons via the Wilcoxon signed-rank test, the rank-biserial correlation expresses the standardized direction and strength of difference ranks:

$$r = \frac{W^+ - W^-}{W^+ + W^-}$$

Where:
- $W^+$ is the sum of ranks for positive differences ($d_i > 0$).
- $W^-$ is the sum of ranks for negative differences ($d_i < 0$).
- When all paired differences are zero, $r$ is explicitly set to $0.0$.
- Rank-biserial correlation is bounded in $[-1.0, 1.0]$.

### 2.4 Wilcoxon Signed-Rank Test & Zero-Difference Handling
The inferential test uses the Wilcoxon signed-rank test. By default, zero differences ($d_i = 0$) are processed using the Pratt method (`zero_method="pratt"`), which includes zero differences in the ranking procedure before discarding their rank sum, avoiding artificial rejection inflation. When all paired differences in a cohort are zero:
- `status = "available"`
- `statistic = 0.0`
- `p_value = 1.0`
- `zero_count = n`

If SciPy is absent from the execution environment, the inferential test exits gracefully:
- `status = "unavailable"`
- `statistic = null`
- `p_value = null`
- `notes = "SciPy unavailable in execution environment; inferential test deferred."`

---

## 3. Multiple Testing Adjustments

When assessing multiple topological metrics (e.g. graph $\beta_1$, persistence, modularity, efficiency), raw $p$-values are adjusted using:

1. **Holm-Bonferroni (`holm`)** [Default]: Step-down method controlling Family-Wise Error Rate (FWER) without requiring subset independence.
   $$p_{(k)}^{\text{adj}} = \min\left(1.0, \max_{j \le k} \left( (m - j + 1) \cdot p_{(j)} \right)\right)$$
2. **Bonferroni (`bonferroni`)**: Single-step FWER control:
   $$p_i^{\text{adj}} = \min(1.0, m \cdot p_i)$$
3. **Benjamini-Hochberg (`fdr_bh`)**: Step-up False Discovery Rate control:
   $$p_{(k)}^{\text{adj}} = \min\left(1.0, \min_{j \ge k} \left( \frac{m}{j} \cdot p_{(j)} \right)\right)$$

Metrics with unavailable tests (`p_value = null`) are preserved as `null` at their exact indices and are excluded from the test count $m$.

---

## 4. Software Architecture and API

The package is organized under `analysis/cohort_statistics/`:

```
analysis/cohort_statistics/
├── __init__.py           # Public API facade
├── models.py             # Typed dataclasses, enums, finite serializer
├── multiplicity.py       # P-value adjustment algorithms
├── calculator.py         # Descriptive, difference, and inferential math
└── serialization.py      # I/O, RFC-8259 JSON validation, SHA-256 integrity
```

### Python API Usage

```python
from analysis.cohort_statistics import (
    calculate_paired_cohort_report,
    save_cohort_report,
    MultiplicityMethod,
    HypothesisAlternative,
)

cohort_data = {
    "sub-001": {
        "drug": {"betti1": 14.5, "efficiency": 0.42},
        "placebo": {"betti1": 9.2, "efficiency": 0.38},
    },
    "sub-002": {
        "drug": {"betti1": 13.8, "efficiency": 0.45},
        "placebo": {"betti1": 8.9, "efficiency": 0.37},
    },
    "sub-003": {
        "drug": {"betti1": 15.1, "efficiency": 0.41},
        "placebo": {"betti1": 10.0, "efficiency": 0.39},
    },
}

report = calculate_paired_cohort_report(
    cohort_data=cohort_data,
    condition_a_name="drug",
    condition_b_name="placebo",
    multiplicity_method=MultiplicityMethod.HOLM,
    alternative=HypothesisAlternative.TWO_SIDED,
    min_pairs=3,
)

# Persist report with SHA-256 checksum and RFC-8259 compliance
save_cohort_report(report, "outputs/cohort_statistics_report.json")
```

---

## 5. Command-Line Interface

The command-line interface is located at `scripts/summarize_cohort_statistics.py`:

```bash
python scripts/summarize_cohort_statistics.py \
    --input outputs/cohort_input.json \
    --output outputs/cohort_statistics_report.json \
    --condition-a drug \
    --condition-b placebo \
    --correction holm \
    --min-pairs 3
```

To verify the SHA-256 cryptographic checksum of an existing report:

```bash
python scripts/summarize_cohort_statistics.py \
    --input outputs/cohort_statistics_report.json \
    --verify-checksum
```

---

## 6. Scientific Guardrails & Separation

All statistical outputs adhere strictly to the repository governance boundaries:

1. **No Biological Proof Claims**: Paired statistical significance rejection ($p < 0.05$ or $p_{\text{adj}} < 0.05$) indicates only rejection of the null hypothesis under the model assumptions; it does NOT constitute biological proof or clinical validation.
2. **No Clinical Claims**: The software must not be used to formulate medical or diagnostic assertions.
3. **Metric Separation**: Graph 1-Betti numbers ($\beta_1$), spatial winding, topological charge, and scalar chirality are computed and reported as independent physical/topological dimensions. They are never conflated or merged into composite "master" scalars.
4. **Bayesian Gate Independence**: This module does not compute Bayes factors and does not modify the falsification gate ($K > 100$).
5. **Deterministic Auditability**: Every report includes a verifiable SHA-256 checksum and exact records for all excluded subject pairs.
