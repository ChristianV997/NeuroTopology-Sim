# Binomial Operating-Characteristic Planning & Uncertainty Verification

This document specifies the statistical foundations, mathematical formulas, sample size planning rules, and methodological guardrails for estimating binomial operating characteristics—such as False Positive Rate (FPR), True Positive Rate (TPR / Sensitivity), and Specificity—in `NeuroTopology-Sim`.

---

## 1. Scope, Purpose & Architectural Isolation

> [!IMPORTANT]
> This module (`analysis/binomial_planning`) is strictly a **planning and uncertainty verification helper** for binomial proportions.
> - It does **not** evaluate detectors or classifiers.
> - It does **not** compute ROC curves, AUROC, Precision-Recall curves, or threshold sweeps.
> - It has zero dependency on detector implementations or empirical data.

All functions operate strictly on binomial trial counts ($k \in \mathbb{N}_0, n \in \mathbb{N}_0$ with $0 \le k \le n$) and precision targets under standard normal critical values ($z$).

---

## 2. Wilson Score Interval Formulation

### 2.1 Theoretical Inversion of the Score Test
Let $k$ be the observed number of events in $n$ independent, identically distributed Bernoulli trials with true underlying rate $p \in [0, 1]$. The empirical sample proportion is $\hat{p} = k / n$ (for $n > 0$).

The standard Wald interval ($\hat{p} \pm z \sqrt{\hat{p}(1 - \hat{p})/n}$) catastrophically degenerates at boundaries ($k = 0$ or $k = n$), producing an illusory zero-width confidence interval $[0, 0]$ or $[1, 1]$ regardless of $n$.

The **Wilson score interval** (Wilson, 1927) resolves this by inverting the score test statistic:
$$\frac{|\hat{p} - p_0|}{\sqrt{\frac{p_0 (1 - p_0)}{n}}} \le z$$
Squaring both sides yields the quadratic inequality in $p_0$:
$$(\hat{p} - p_0)^2 \le \frac{z^2}{n} p_0 (1 - p_0)$$
$$\left(1 + \frac{z^2}{n}\right) p_0^2 - 2 \left(\hat{p} + \frac{z^2}{2n}\right) p_0 + \hat{p}^2 \le 0$$

Solving for the roots produces the canonical Wilson interval:
$$\tilde{p} = \frac{k + \frac{z^2}{2}}{n + z^2}$$
$$\text{margin} = \frac{z}{n + z^2} \sqrt{\frac{k (n - k)}{n} + \frac{z^2}{4}}$$
$$p_{\text{lower}} = \max\left(0.0, \tilde{p} - \text{margin}\right)$$
$$p_{\text{upper}} = \min\left(1.0, \tilde{p} + \text{margin}\right)$$

### 2.2 Boundary Behavior
1. **Zero Observed Events ($k = 0$)**:
   $$\tilde{p} = \frac{z^2 / 2}{n + z^2}, \quad \text{margin} = \frac{z}{n + z^2} \sqrt{\frac{z^2}{4}} = \frac{z^2 / 2}{n + z^2}$$
   $$p_{\text{lower}} = \tilde{p} - \text{margin} = 0.0$$
   $$p_{\text{upper}}(0, n) = \tilde{p} + \text{margin} = \frac{z^2}{n + z^2}$$
2. **All Observed Events ($k = n$)**:
   $$p_{\text{lower}}(n, n) = 1.0 - \frac{z^2}{n + z^2}$$
   $$p_{\text{upper}}(n, n) = 1.0$$
3. **Zero Trials Evaluated ($n = 0$)**:
   > [!CAUTION]
   > When $n = 0$, evaluating $\hat{p} = 0 / 0$ is mathematically undefined. No empirical trials have occurred.
   > The utility strictly returns `status="unavailable_zero_trials"` with `lower=None`, `upper=None`, and `is_available=False`.
   > A zero-trial interval is **never** imputed as $[0, 0]$ or $[0, 1]$.

---

## 3. Analysis of Small Sample Sizes: The $n = 16$ Problem

Round 6 synthetic evaluations reported Wilson 95% confidence intervals from $n = 16$ evaluation trials.
Evaluating the exact zero-event upper bound at $n = 16$ with $z = 1.95996398454$ (two-sided 95% confidence, $z^2 \approx 3.84146$):
$$p_{\text{upper}}(0, 16) = \frac{3.84146}{16 + 3.84146} = \frac{3.84146}{19.84146} \approx 0.193608 \quad (\sim 19.36\%)$$

```
Observed events: 0 false positives out of 16 trials (k = 0, n = 16)
Point estimate:  FPR = 0.0%
95% Wilson CI:   [0.0%, 19.36%]
```

### Methodological Consequence
Even when **zero** false positives occur across 16 trials, the upper bound on the false positive rate is nearly **20%**.
- A detector with a true underlying FPR of 15% will produce 0 false positives in 16 trials $(1 - 0.15)^{16} \approx 7.4\%$ of the time by pure chance.
- A sample size of $n = 16$ is statistically incapable of substantiating a strong claim of a low false positive rate (such as $\text{FPR} < 5\%$ or $\text{FPR} < 1\%$).

---

## 4. Sample Size Planning & Trial Count Inversion

### 4.1 Required Trials for Zero-Event Upper Bounds
To guarantee that observing zero events ($k = 0$) achieves a 95% confidence upper bound $p_{\text{upper}} \le \alpha_{\text{target}}$:
$$\frac{z^2}{n + z^2} \le \alpha_{\text{target}} \iff n \ge z^2 \left(\frac{1}{\alpha_{\text{target}}} - 1\right)$$
$$n^* = \left\lceil z^2 \left(\frac{1}{\alpha_{\text{target}}} - 1\right) \right\rceil$$

#### Required Trial Counts ($95\%$ Confidence, $z = 1.95996$):
| Target False Positive Upper Bound ($\alpha_{\text{target}}$) | Minimum Required Trials ($n^*$) | Achieved 95% Wilson Upper Bound |
|---|---|---|
| $\le 20\%$ | **16** | 19.36% |
| $\le 10\%$ | **35** | 9.89% |
| $\le 5\%$ | **73** | 4.99% |
| $\le 2\%$ | **189** | 1.99% |
| $\le 1\%$ | **381** | 0.998% |
| $\le 0.5\%$ | **765** | 0.499% |
| $\le 0.1\%$ | **3838** | 0.0999% |

To establish that a pipeline's FPR is bounded below 5% at the 95% confidence level, a minimum of **73 zero-event evaluation trials** is mathematically required.

---

### 4.2 Required Trials for Interval Width (Precision Planning)
Let $W(p, n) = p_{\text{upper}} - p_{\text{lower}}$ be the interval width for an expected proportion $p$:
$$W(p, n) = \frac{2z}{n + z^2} \sqrt{n p (1 - p) + \frac{z^2}{4}}$$

The planner provides two distinct precision guarantee modes:

1. **Pointwise Guarantee at Declared Design Point $p^*$**:
   - Assumes the true operating point is near $p^*$ (e.g. $p^* = 0.05$ for targeted low-FPR, or $p^* = 0.90$ for sensitivity).
   - Because $p^*(1 - p^*) \ll 0.25$, the required $n$ is substantially smaller.
   - **Limitation**: This guarantee holds **only if** the observed rate remains near $p^*$. If the empirical rate deviates toward 0.5, the interval width expands.

2. **Uniform Worst-Case Guarantee Across All $p \in [0, 1]$**:
   - Evaluates at the maximum variance point $p^* = 0.5$, where $p(1 - p) = 0.25$:
     $$W(0.5, n) = \frac{2z}{n + z^2} \sqrt{\frac{n + z^2}{4}} = \frac{z}{\sqrt{n + z^2}}$$
   - Analytical inversion for target full width $W$:
     $$n^* = \left\lceil z^2 \left(\frac{1}{W^2} - 1\right) \right\rceil$$
   - **Guarantee**: Guarantees that the Wilson interval width will not exceed $W$ **regardless** of what empirical proportion is observed.

---

## 5. Epistemic Guardrails & Why Synthetic Results Do Not Generalize

### 5.1 No Cross-Regime Generalization
A confidence interval $[p_{\text{lower}}, p_{\text{upper}}]$ computed from synthetic evaluations quantifies **only the sampling uncertainty within that specific generative model and parameter configuration**.
It assumes independent, exchangeable trials drawn from a static distribution $\text{Bernoulli}(p)$.

It provides **no statistical guarantee** across:
1. **Dipole Depth & Geometry**: Shallow cortical sources produce higher SNR and distinct topological signatures compared to deep thalamic or medial temporal sources.
2. **Noise Regimes & Colors**: White Gaussian noise does not mirror pink ($1/f^\alpha$) background EEG, line noise harmonics, or electrode drift.
3. **Artifact Contamination**: Synthetic runs lacking ocular, cardiac, or myogenic artifacts do not predict detector performance in real recordings.
4. **Inter-Subject / Anatomical Variability**: Head conductivity, skull thickness, and sulcal geometry vary significantly across participants.

### 5.2 Prohibition on Unqualified "Powered" Claims
A sample size cannot be scientifically termed "powered" in isolation. Statistical power ($1 - \beta$) is defined exclusively in the context of:
1. A specific null hypothesis $H_0$ (e.g., $FPR \ge 0.10$).
2. A specific alternative hypothesis $H_1$ (e.g., $FPR = 0.01$).
3. A declared Type I error rate $\alpha$ (significance level).
4. A declared Type II error rate $\beta$.

Precision planning (controlling confidence interval width) is distinct from hypothesis testing power. Declaring an evaluation sample "powered" without declaring $H_0$, $H_1$, $\alpha$, and $\beta$ is prohibited.

---

## 6. CLI Usage & Automated Verification

The package provides a built-in CLI:

```bash
# Evaluate Wilson interval for 0 events in 16 trials
python -m analysis.binomial_planning.cli interval -k 0 -n 16

# Plan sample size for targeting 5% FPR upper bound with zero events
python -m analysis.binomial_planning.cli plan-zero -t 0.05

# Plan sample size for uniform +/- 5% margin of error (half-width 0.05)
python -m analysis.binomial_planning.cli plan-width -w 0.05 --half-width
```
