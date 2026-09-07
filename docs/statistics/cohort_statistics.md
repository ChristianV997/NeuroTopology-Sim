# Paired-Cohort Statistics and Effect-Size Validation

## 1. Overview

Within-subject experimental paradigms (such as crossover trials, pre-post interventions, or paired condition comparisons) generate repeated measures from the same biological or computational units. Analyzing repeated-measures designs using independent two-sample formulas (such as two-sample Student's $t$-tests or two-sample pooled Cohen's $d$) conflates inter-subject baseline variance with true intra-subject treatment shifts, biasing standard errors and distorting effect-size estimations.

The `analysis.cohort_statistics` package provides a typed, deterministic, and verifiable within-subject paired statistics and effect-size validation framework for `NeuroTopology-Sim`.

### Key Capabilities

- **Versioned Schema (v2)**: Formal schema `NeuroTopologySim.CohortStatisticsReport.v2` with explicit included/excluded subject lists, exclusion reasons, tie counts, zero-difference counts, confidence intervals, and effect estimates.
- **Exact Condition Labels**: Preserves exact condition labels as supplied in manifests or CLI arguments without inferring awake, sedated, meditation, or task identity from filenames.
- **Exact Pairing Guarantees**: Deterministic subject identifier sorting and bijective condition matching ($A_i$ and $B_i$ for each subject $i$).
- **Non-Silent Exclusions**: Explicit recording of every exclusion with machine-readable reasons (`missing_condition`, `non_finite_val`, `unparseable_val`, `condition_error`, `duplicate_subject_id`). Insufficient or missing data are never silently dropped.
- **Scientifically Grounded Effect Sizes**: Implements paired Cohen's $d_z$ ($d_z = \bar{d} / s_d$) and rank-biserial correlation $r = (W^+ - W^-) / (W^+ + W^-)$, labeled explicitly as effect estimates rather than formal biological evidence.
- **Multiple Testing Corrections**: Holm-Bonferroni step-down, Bonferroni, and Benjamini-Hochberg False Discovery Rate (FDR-BH), correctly excluding non-testable metrics from the hypothesis count $m$ while preserving exact positional alignment. If correction is absent or unavailable, returns an explicit `multiplicity_unavailable` state.
- **Strict RFC-8259 JSON Compliance**: Guaranteed omission of non-finite literals (`NaN`, `Infinity`, `-Infinity`); unavailable numerical estimates are strictly serialized as JSON `null`.
- **Tamper-Evident Integrity Checksums**: SHA-256 checksum computed over canonical metric payloads to detect mutation or data drift.
- **Strict Scientific Guardrails**: Explicit non-evidence fields:
  - `formal_bayes_factor = null`
  - `scientific_pass = false`
  - `evidence_class = "descriptive_or_paired_statistics"`

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
> Cohen's $d_z$ is an effect estimate and does NOT constitute formal biological proof.

### 2.3 Non-Parametric Rank-Biserial Correlation ($r$)
For non-parametric comparisons via the Wilcoxon signed-rank test, the rank-biserial correlation expresses the standardized direction and strength of difference ranks:

$$r = \frac{W^+ - W^-}{W^+ + W^-}$$

Where:
- $W^+$ is the sum of ranks for positive differences ($d_i > 0$).
- $W^-$ is the sum of ranks for negative differences ($d_i < 0$).
- Ties among absolute differences are handled by average rank assignment.
- When all paired differences are zero, $r$ is explicitly set to $0.0$.
- Rank-biserial correlation is bounded in $[-1.0, 1.0]$.

### 2.4 Wilcoxon Signed-Rank Test & Zero-Difference Handling
The inferential test uses the Wilcoxon signed-rank test. By default, zero differences ($d_i = 0$) are processed using the Pratt method (`zero_method="pratt"`), which includes zero differences in the ranking procedure before discarding their rank sum. When all paired differences in a cohort are zero:
- `status = "available"`
- `statistic = 0.0`
- `p_value = 1.0`
- `zero_difference_count = n`

If SciPy is absent from the execution environment, the inferential test exits gracefully:
- `status = "unavailable"`
- `wilcoxon_statistic = null`
- `wilcoxon_p_value = null`
- `notes = "SciPy unavailable in execution environment; inferential test deferred."`

---

## 3. Multiple Testing Adjustments

When assessing multiple topological metrics (e.g. `beta-1 persistence`, `integrated persistence-landscape area`, `persistence distance`, `spatial phase charge`), raw $p$-values are adjusted using:

1. **Holm-Bonferroni (`holm`)** [Default]: Step-down method controlling Family-Wise Error Rate (FWER) without requiring subset independence.
2. **Bonferroni (`bonferroni`)**: Single-step FWER control.
3. **Benjamini-Hochberg (`fdr_bh`)**: Step-up False Discovery Rate control.
4. **Unavailable (`multiplicity_unavailable`)**: If the correction method is omitted or unavailable, the output records `multiplicity_status = "multiplicity_unavailable"` and `p_adjusted = null` rather than silently treating the analysis as a single test.

---

## 4. Software Architecture and API

The package is organized under `analysis/cohort_statistics/`:

```
analysis/cohort_statistics/
├── __init__.py           # Public API facade
├── models.py             # Typed dataclasses (v2), enums, finite serializer
├── multiplicity.py       # P-value adjustments and unavailable state
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
        "pre": {"beta-1 persistence": 14.5, "spatial phase charge": 1.1},
        "post": {"beta-1 persistence": 10.0, "spatial phase charge": 0.5},
    },
    "sub-002": {
        "pre": {"beta-1 persistence": 15.0, "spatial phase charge": 1.2},
        "post": {"beta-1 persistence": 10.5, "spatial phase charge": 0.6},
    },
    "sub-003": {
        "pre": {"beta-1 persistence": 13.8, "spatial phase charge": 1.0},
        "post": {"beta-1 persistence": 9.5, "spatial phase charge": 0.4},
    },
}

report = calculate_paired_cohort_report(
    cohort_data=cohort_data,
    condition_a_name="pre",
    condition_b_name="post",
    cohort_identifier="ds005917",
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
    --condition-a pre \
    --condition-b post \
    --cohort-id ds005917 \
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

All statistical outputs adhere strictly to repository governance boundaries:

1. **No Biological Proof Claims**: Paired statistical significance indicates only rejection of the null hypothesis under the model assumptions; it does NOT constitute biological proof of quantum coherence, consciousness, or clinical efficacy.
2. **No Clinical Claims**: The software must not be used to formulate medical or diagnostic assertions.
3. **No Formal Bayes Factors**: Outputs explicitly enforce `formal_bayes_factor = null`, `scientific_pass = false`, and `evidence_class = "descriptive_or_paired_statistics"`.
4. **Metric Separation**: Graph 1-Betti numbers ($\beta_1$), spatial winding, topological charge, and scalar chirality are computed and reported as independent physical/topological dimensions. They are never conflated or merged into composite "master" scalars.
5. **Bayesian Gate Independence**: This module does not compute Bayes factors and does not modify the falsification gate ($K > 100$).
6. **Deterministic Auditability**: Every report includes a verifiable SHA-256 checksum and exact records for all excluded subject pairs.
