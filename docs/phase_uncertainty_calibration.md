# Narrowband Phase-Uncertainty Estimator Calibration & Audit Report

**Status**: HOLD / SYNTHETIC_ONLY
**Lane**: Batch 2 / Antigravity Agent A
**Target Repository**: `https://github.com/ChristianV997/NeuroTopology-Sim`
**Base Commit**: `bc91af19a22783d2721fc881842573f7e08a8925` (synced from stale `3f3fe859…`)
**Module path**: `tools/phase_uncertainty/` (not `phase_dispersion.py`; see planner mismatch note)
**Candidate Status**: Reconstructed from the Round 6 specification contract; candidate was not previously executed in the repository.
**Planner note (#424)**: `phase_dispersion_module` is `contract_declared_unobserved` / unpinned;
`tools/phase_uncertainty/` is explicitly `substitute_module_rejected` and must not be
treated as that missing module.

---

## 1. Executive Summary

This audit evaluates the calibration, empirical coverage, and mathematical failure modes of the proposed **Round 6 narrowband phase-uncertainty estimator**.

The core question investigated is: **Does the reported `phase_std` represent a calibrated, statistically valid measure of phase uncertainty, or is it an uncalibrated heuristic?**

Reported phase-error bias is computed as a circular mean. When the error resultant length is very small, the mean direction is weakly determined and is noted as such.

### Key Findings
1. **Severe Overconfidence under Colored Noise**:
   Under autoregressive noise ($AR(1)$ with $\rho = 0.85$), the empirical RMS phase error is **1.60× larger than the predicted `phase_std`**. Empirical $1\sigma$ coverage drops from the nominal Gaussian $68.27\%$ to **$42.30\%$**, and $2\sigma$ coverage drops from $95.00\%$ to **$77.40\%$**.
2. **Breakdown of the Second-Difference MAD Noise Model**:
   The estimator assumes that residual phase noise $\eta[n]$ is independent and identically distributed (i.i.d.) Gaussian, where the second difference $\Delta^2 \eta[n] = \eta[n] - 2\eta[n-1] + \eta[n-2]$ has variance $6\sigma_\eta^2$. When noise is positively autocorrelated, $\mathrm{Var}(\Delta^2 \eta) < 6\sigma_\eta^2$. Consequently, the scaling factor $\frac{1.4826}{\sqrt{6}} \mathrm{MAD}(\Delta^2 \theta)$ severely underestimates the actual noise standard deviation.
3. **Severe Overconfidence at Near-Zero Amplitude**:
   At exactly zero amplitude, phase is undefined; at low but nonzero amplitude, additive noise can dominate the measured phase. In intermediate synthetic bins, empirical error exceeds predicted uncertainty by **$1.68\times$**.
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

The implementation requires a one-dimensional NumPy numeric-dtype signal of at least four finite samples and a finite positive sampling rate. Boolean, string, date/time, and object dtypes are rejected instead of coerced. It fails closed if the analytic transform or any derived diagnostic becomes non-finite; it does not return a report containing NaN or Infinity.

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
- At exactly zero amplitude, phase is mathematically undefined. At low but nonzero amplitude, noise can dominate and make measured phase unstable; this is not a claim about a biological singularity.
- Second differences clip against the boundary $(-\pi, \pi]$, violating Gaussian linearity.
- In the transition region, the estimator reports $\sigma \approx 0.9 - 1.3$ rad, while the true error distribution has RMS $> 1.79$ rad.

---

## 5. Proposed Fail-Closed Operational Categories

Because `phase_std` cannot be corrected to a universal confidence interval by linear rescaling, downstream consumers must apply **fail-closed reliability categorization**:

```mermaid
flowchart TD
    A["Complex Frame Z[n]"] --> B{"Diagnostics finite and aligned?"}
    B -- No --> C["FAIL_CLOSED_INVALID_DATA<br>(Reject malformed diagnostics)"]
    B -- Yes --> D{"Amplitude and phase_std non-negative?"}
    D -- No --> C
    D -- Yes --> E{"A[n] < 0.15 * median(A), or median(A) <= 0?"}
    E -- Yes --> F["FAIL_CLOSED_NEAR_ZERO_AMPLITUDE<br>(Quarantine: Undefined or Unstable Phase)"]
    E -- No --> G{"phase_std >= 0.95 * (pi/sqrt(3))?"}
    G -- Yes --> H["FAIL_CLOSED_MAX_UNCERTAINTY<br>(Quarantine: Near-Ceiling Threshold)"]
    G -- No --> I{"|f_inst - f_median| > 0.5 * |f_median|?"}
    I -- Yes --> J["FAIL_CLOSED_FREQUENCY_DRIFT<br>(Quarantine: Nonstationary Carrier)"]
    I -- No --> K{"phase_std > 0.6 * (pi/sqrt(3))?"}
    K -- Yes --> L["MARGINAL<br>(Use only with wide tolerance)"]
    K -- No --> M["RELIABLE<br>(Rule-based category only)"]
```

### Categorization Criteria
1. **`FAIL_CLOSED_INVALID_DATA`**:
   Direct tier classification assigns this tier to non-finite diagnostic values and negative amplitude or `phase_std`. Instantaneous frequency is signed, so negative frequency is permitted. Calibration report generation rejects non-finite, non-vector, or misaligned arrays with `ValueError`.
2. **`FAIL_CLOSED_NEAR_ZERO_AMPLITUDE`**:
   Triggered when $A[n] < 0.15 \times \mathrm{median}(A)$.
   If median amplitude is zero, all otherwise valid frames are quarantined. At zero amplitude, phase is undefined; this does not identify a physical vortex or biological state.
3. **`FAIL_CLOSED_MAX_UNCERTAINTY`**:
   Triggered when $\mathrm{phase\_std}[n] \ge 0.95 \times \frac{\pi}{\sqrt{3}} \approx 1.72$ rad.
   This is a threshold on the heuristic output; it does not prove phase is statistically uniform.
4. **`FAIL_CLOSED_FREQUENCY_DRIFT`**:
   Triggered when $|f_{\mathrm{inst}}[n] - f_{\mathrm{median}}| > 0.5 \times |f_{\mathrm{median}}|$. At zero median frequency, any nonzero deviation fails closed.
   Median frequency demodulation fails during rapid frequency sweeps.
5. **`MARGINAL`**:
   Triggered when $\mathrm{phase\_std} \in [0.60, 0.95) \times \frac{\pi}{\sqrt{3}}$.
6. **`RELIABLE`**:
   A deterministic rule-based category for high amplitude, small frequency deviation, and $\mathrm{phase\_std} < 0.60 \times \frac{\pi}{\sqrt{3}}$. It is not a calibrated probability, confidence interval, physical-correctness check, or empirical/biological validation.

### Circular coverage limitation

Errors are wrapped to $(-\pi, \pi]$. Whenever $1.96 \times \mathrm{phase\_std} \ge \pi$, every possible wrapped error is within the nominal 2-sigma bound and the reported coverage is geometrically saturated at 100%. The calibration report adds an explicit note for this condition; such coverage is not evidence that uncertainty is calibrated.

---

## 6. Scientific Limitations & Guardrails

- **Synthetic Only**: All evaluations performed purely on synthetic signals with known ground truth.
- **No SciPy Dependency**: Calibration harness implemented in pure NumPy without third-party dependencies.
- **No Evidence Promotion**: This calibration does not constitute validation of any consciousness or neural theory.
- **Status**: `HOLD / SYNTHETIC_ONLY`.
