# Narrowband Phase-Uncertainty Estimator Calibration & Audit Report

**Status**: HOLD / SYNTHETIC_ONLY  
**Lane**: Batch 2 / Antigravity Agent A  
**Target Repository**: `https://github.com/ChristianV997/NeuroTopology-Sim`  
**Base Commit**: `3f3fe8593303184cb88eef056c1322f3d4e57a16`  
**Candidate Status**: Reconstructed from the Round 6 specification contract; candidate was not previously executed in the repository.

---

## 1. Executive Summary

This audit evaluates the calibration, empirical coverage, and mathematical failure modes of the proposed **Round 6 narrowband phase-uncertainty estimator**. 

The core question investigated is: **Does the reported `phase_std` represent a calibrated, statistically valid measure of phase uncertainty, or is it an uncalibrated heuristic?**

### Key Findings
1. **Severe Overconfidence under Colored Noise**:
   Under autoregressive noise ($AR(1)$ with $\rho = 0.85$), the empirical RMS phase error is **1.60× larger than the predicted `phase_std`**. Empirical $1\sigma$ coverage drops from the nominal Gaussian $68.27\%$ to **$42.30\%$**, and $2\sigma$ coverage drops from $95.00\%$ to **$77.40\%$**.
2. **Breakdown of the Second-Difference MAD Noise Model**:
   The estimator assumes that residual phase noise $\eta[n]$ is independent and identically distributed (i.i.d.) Gaussian, where the second difference $\Delta^2 \eta[n] = \eta[n] - 2\eta[n-1] + \eta[n-2]$ has variance $6\sigma_\eta^2$. When noise is positively autocorrelated, $\mathrm{Var}(\Delta^2 \eta) < 6\sigma_\eta^2$. Consequently, the scaling factor $\frac{1.4826}{\sqrt{6}} \mathrm{MAD}(\Delta^2 \theta)$ severely underestimates the actual noise standard deviation.
3. **Severe Overconfidence at Near-Zero Amplitude Singularities**:
   In low-amplitude regimes ($A \to 0$), phase is dominated by noise and wraps uniformly on $(-\pi, \pi]$. In intermediate bins, empirical error exceeds predicted uncertainty by **$1.68\times$**.
4. **Conservatism under High-SNR AWGN**:
   Under high-SNR stationary white noise, the estimator is conservative ($\mathrm{RMS} / \overline{\sigma}_{\mathrm{pred}} \approx 0.65$) because it quadratically sums an SNR-derived term and a local circular jitter term ($\sqrt{\sigma_{\mathrm{SNR}}^2 + \sigma_{\mathrm{jitter}}^2}$), effectively double-counting noise fluctuations.
5. **Verdict**:
   **`phase_std` is NOT a statistically valid confidence interval.** It is an uncalibrated heuristic indicator. It must never be labeled or consumed as a formal confidence interval without fail-closed gating.

---

## 2. Mathematical Contract of the Candidate Estimator

The Round 6 candidate estimator operates on complex narrowband signals $Z[n] = A[n] e^{i \theta[n]}$:
1. **Instantaneous Phase Increments**:
   $$\theta[n] = \mathrm{wrap}(\mathrm{angle}(Z[n])) \in (-\pi, \pi], \quad \Delta \theta[n] = \mathrm{wrap}(\theta[n] - \theta[n-1])$$
2. **Median Frequency Demodulation**:
   $$\Delta \omega_0 = \mathrm{median}(\Delta \theta), \quad \delta[n] = \mathrm{wrap}(\Delta \theta[n] - \Delta \omega_0)$$
3. **Second-Difference Residual Noise via MAD**:
   $$\Delta^2 \theta[n] = \mathrm{wrap}(\delta[n] - \delta[n-1])$$
   $$\hat{\sigma}_{\mathrm{MAD}} = \frac{1.4826 \cdot \mathrm{MAD}(\Delta^2 \theta)}{\sqrt{6}}$$
4. **SNR Term and Local Circular Jitter**:
   $$\sigma_{\mathrm{SNR}}[n] = \frac{\hat{\sigma}_{\mathrm{MAD}}}{\sqrt{2} \cdot (A[n] / \mathrm{median}(A))}$$
   $$R[n] = \left| \frac{1}{W} \sum_{k \in W_n} e^{i \delta[k]} \right|, \quad \sigma_{\mathrm{jitter}}[n] = \sqrt{2 (1 - R[n])}$$
5. **Combined Uncertainty with Uniform Ceiling**:
   $$\sigma_{\mathrm{raw}}[n] = \sqrt{\sigma_{\mathrm{SNR}}[n]^2 + \sigma_{\mathrm{jitter}}[n]^2}$$
   $$\mathrm{phase\_std}[n] = \min\left(\sigma_{\mathrm{raw}}[n], \frac{\pi}{\sqrt{3}}\right)$$
   *(where $\pi / \sqrt{3} \approx 1.8138$ is the standard deviation of a continuous uniform distribution on $[-\pi, \pi]$)*.

---

## 3. Empirical Calibration Results across Synthetic Battery

All tests evaluated $N=1000$ samples (burst $N=64$) at $f_s = 1000$ Hz with known ground truth $\theta_{\mathrm{true}}[n]$:

| Synthetic Fixture | Nominal Condition | Mean $\overline{\sigma}_{\mathrm{pred}}$ | Empirical $\mathrm{RMS}(e_\theta)$ | $1\sigma$ Cov (68.3%) | $2\sigma$ Cov (95.0%) | Ratio ($\frac{\mathrm{RMS}}{\overline{\sigma}}$) | Calibration Verdict |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `stationary_awgn_20db` | AWGN 20 dB | 0.1215 rad | 0.0768 rad | 82.2% | 100.0% | 0.63 | **Conservative** |
| `stationary_awgn_6db` | AWGN 6 dB | 0.4431 rad | 0.3533 rad | 77.8% | 98.4% | 0.80 | **Conservative** |
| `stationary_awgn_-3db` | AWGN -3 dB | 1.1352 rad | 0.9419 rad | 72.5% | 96.1% | 0.83 | **Conservative** |
| `amplitude_modulated` | Depth 0.8, 10 dB | 0.3703 rad | 0.2905 rad | 79.4% | 97.9% | 0.78 | **Conservative** |
| `frequency_drift` | 8 $\to$ 15 Hz chirp | 0.2458 rad | 0.2198 rad | 70.1% | 96.3% | 0.89 | **Well-Calibrated** |
| `near_zero_amplitude` | Notch $A=10^{-4}$ | 0.6171 rad | 1.0374 rad | 47.9% | 85.1% | **1.68** | **OVERCONFIDENT** |
| `colored_noise_ar0.85` | AR(1) $\rho=0.85$ | 0.1656 rad | 0.2647 rad | 42.3% | 77.4% | **1.60** | **OVERCONFIDENT** |
| `short_window_burst` | $N=64$, 12 dB | 0.2978 rad | 0.1927 rad | 79.7% | 100.0% | 0.65 | **Conservative** |

---

## 4. Failure Mode Analysis

### 4.1 Colored Noise and Spectral Non-Whiteness
In real electrophysiological and neural physical recordings, residual noise exhibits $1/f$ pink noise or autoregressive temporal correlation.
- For noise with lag-1 correlation $\rho = 0.85$, adjacent samples cancel out during second differencing.
- The theoretical variance ratio is:
  $$\mathrm{Var}(\Delta^2 \eta) = (6 - 8\rho + 2\rho^2) \sigma_\eta^2$$
  For $\rho = 0.85$, $6 - 8(0.85) + 2(0.85)^2 = 6 - 6.8 + 1.445 = 0.645$.
- The estimator assumes the factor is $6.0$. Thus the estimated noise variance is underestimated by $\frac{0.645}{6.0} \approx 0.1075$ (an underestimate of $\sigma$ by $\sqrt{0.1075} \approx 0.33$).
- This mathematical defect causes the estimator to underestimate phase noise by up to $3\times$ under colored noise.

### 4.2 Near-Zero Amplitude Crossings
Near amplitude nulls ($A[n] \to 0$):
- Instantaneous phase wraps chaotically due to division by zero in $\mathrm{atan2}$.
- Second differences clip against the boundary $(-\pi, \pi]$, violating Gaussian linearity.
- In the transition region, the estimator reports $\sigma \approx 0.9 - 1.3$ rad, while the true error distribution has RMS $> 1.79$ rad.

---

## 5. Proposed Fail-Closed Operational Categories

Because `phase_std` cannot be corrected to a universal confidence interval by linear rescaling, downstream consumers must apply **fail-closed reliability categorization**:

```mermaid
flowchart TD
    A["Complex Frame Z[n]"] --> B{"|Z[n]| < 0.15 * median(A)?"}
    B -- Yes --> C["FAIL_CLOSED_NEAR_ZERO_AMPLITUDE<br>(Quarantine: Phase Singular)"]
    B -- No --> D{"phase_std >= 0.95 * (pi/sqrt(3))?"}
    D -- Yes --> E["FAIL_CLOSED_MAX_UNCERTAINTY<br>(Quarantine: Uniform Floor)"]
    D -- No --> F{"|f_inst - f_median| > 0.5 * f_median?"}
    F -- Yes --> G["FAIL_CLOSED_FREQUENCY_DRIFT<br>(Quarantine: Nonstationary Carrier)"]
    F -- No --> H{"phase_std > 0.6 * (pi/sqrt(3))?"}
    H -- Yes --> I["MARGINAL<br>(Use only with wide tolerance)"]
    H -- No --> J["RELIABLE<br>(Bounded Operational Use)"]
```

### Categorization Criteria
1. **`FAIL_CLOSED_NEAR_ZERO_AMPLITUDE`**:
   Triggered when $A[n] < 0.15 \times \mathrm{median}(A)$.
   Phase is physically undefined (vortex core / singularity); discard from synchronization metrics.
2. **`FAIL_CLOSED_MAX_UNCERTAINTY`**:
   Triggered when $\mathrm{phase\_std}[n] \ge 0.95 \times \frac{\pi}{\sqrt{3}} \approx 1.72$ rad.
   Phase is statistically uniform on the unit circle.
3. **`FAIL_CLOSED_FREQUENCY_DRIFT`**:
   Triggered when $|\Delta \theta[n] - \Delta \omega_0| > 0.5 \times |\Delta \omega_0|$.
   Median frequency demodulation fails during rapid frequency sweeps.
4. **`MARGINAL`**:
   Triggered when $\mathrm{phase\_std} \in [0.60, 0.95) \times \frac{\pi}{\sqrt{3}}$.
5. **`RELIABLE`**:
   High amplitude, stable frequency, $\mathrm{phase\_std} < 0.60 \times \frac{\pi}{\sqrt{3}}$.

---

## 6. Scientific Limitations & Guardrails

- **Synthetic Only**: All evaluations performed purely on synthetic signals with known ground truth.
- **No SciPy Dependency**: Calibration harness implemented in pure NumPy without third-party dependencies.
- **No Evidence Promotion**: This calibration does not constitute validation of any consciousness or neural theory.
- **Status**: `HOLD / SYNTHETIC_ONLY`.
