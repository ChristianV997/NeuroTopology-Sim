# Embodied-Control Alignment Layer

## Overview

The `EmbodiedControlAligner` provides a principled, memory-bounded synchronization and feature extraction layer linking windowed electroencephalography (EEG) data with continuous peripheral autonomic physiology—specifically respiration, electrocardiography (ECG), heart-rate variability (HRV), and electrodermal activity (EDA).

```
+------------------------------------+       +------------------------------------+
|         Neural Windows             |       |    Multimodal Physiology Stream    |
|   (EEGSignalWindow / SignalChunk)  |       |   (Respiration, ECG, EDA, Temp)    |
+------------------------------------+       +------------------------------------+
                   \                                   /
                    \                                 /
                     v                               v
       +-----------------------------------------------------------+
       |                 EmbodiedControlAligner                    |
       |  - Common clock resampling (Causal linear interpolation)  |
       |  - Clock drift & timestamp discontinuity diagnostics      |
       |  - Window overlap duration & overlap ratio calculation    |
       |  - Cross-modal lag candidate search (-3s to +3s)          |
       |  - Variable role assignment (predictor/moderator/covariate)|
       +-----------------------------------------------------------+
                                     |
                                     v
       +-----------------------------------------------------------+
       |               Multimodal Feature Extraction               |
       |  - Respiration: Rate (BPM), Phase [-pi, pi), I:E ratio    |
       |  - Cardiac: Heart Rate (BPM), RMSSD (ms), SDNN, pNN50     |
       |  - Autonomic Proxy: Tonic EDA (uS), Vagal proxy, Balance  |
       |  - Neural: Theta, Alpha, Beta, Gamma bandpowers, Centroid |
       +-----------------------------------------------------------+
                                     |
                                     v
       +-----------------------------------------------------------+
       |                 Empirical Confound Controls               |
       |  - Circular shift control                                 |
       |  - Block shift control                                    |
       |  - Matched-variance Fourier phase-randomized surrogates   |
       |  - Condition-preserving permutations                      |
       +-----------------------------------------------------------+
                                     |
                                     v
       +-----------------------------------------------------------+
       |             EmbodiedControlAlignmentReport                |
       |  - Schema version v1.0.0                                  |
       |  - Null-safe JSON serialization (no NaN / Infinity)       |
       |  - SHA-256 cryptographic report digest                    |
       |  - Explicit evidence class & quality classification       |
       +-----------------------------------------------------------+
```

---

## Scientific Guardrails & Epistemological Boundaries

All modules, scripts, and downstream analysis pipelines consuming this layer must adhere strictly to the following boundaries:

> [!IMPORTANT]
> 1. **Candidate Explanatory Features Only:** Embodied physiological variables (respiratory mechanics, vagal tone, autonomic balance) are **candidate explanatory features, moderators, covariates, or potential intervention targets**. They are **not proven causal mechanisms**.
> 2. **No Claim of Causal Mediation:** Observational correlation or phase alignment between peripheral signals and neural oscillations does not establish directed causal mediation.
> 3. **Prohibition of Metaphysical & Subjective Labels:**
>    - Parasympathetic activation or elevated vagal tone is **never** labeled as "calmness".
>    - Slow or paced breathing is **never** labeled as "equanimity".
>    - Attenuated autonomic arousal or reward reactivity is **never** labeled as "detachment".
>    - Autonomic changes are **never** labeled as "liberation".
> 4. **No Label Inference:** File paths, filenames, participant IDs, or annotations containing strings like `awake`, `sedated`, `meditation`, `jhana`, or `arousal` must never be used to infer cognitive or mental states. Operator-provided labels must be preserved verbatim.
> 5. **Synthetic Status Separation:** Synthetic signals are strictly flagged with `is_synthetic=True` and `evidence_class="SYNTHETIC_CONTROL"`. Synthetic data is never empirical evidence.

---

## Alignment Metadata & Diagnostics

For every time window, the layer constructs explicit alignment provenance:

| Field | Type | Description |
| :--- | :--- | :--- |
| `common_clock_hz` | `float` | Target uniform sampling frequency (e.g. 100.0 Hz). |
| `start_time_s`, `end_time_s` | `float` | Window interval boundaries on the shared timeline. |
| `window_overlap_s` | `float` | Duration of intersection between neural window and valid physiological data. |
| `overlap_ratio` | `float` | $T_{\text{overlap}} / (t_{\text{end}} - t_{\text{start}})$, bounded in $[0.0, 1.0]$. |
| `resampling` | `list[ResamplingRecord]` | Per-channel source and target sampling rates, resampling ratio, and interpolation method. |
| `interpolation_method` | `str` | Strictly `causal_linear` (evaluating samples exclusively using past/current observations) or `nearest`. |
| `clock_drift` | `ClockDriftDiagnostics` | Estimated drift in parts-per-million (ppm) and detected timestamp discontinuities. |
| `lag_candidates` | `list[LagCandidate]` | Cross-correlation evaluated across physiological candidate lags $\tau \in [-3.0, +3.0]$ s. |
| `missingness_ratio` | `float` | Fraction of expected physiological channels (RESP, ECG, EDA) absent from the recording. |
| `signal_quality_state` | `str` | `PASS` ($\ge 90\%$ overlap, no drift), `DEGRADED` ($\ge 50\%$ overlap), `INCONCLUSIVE`, or `FAIL`. |

---

## Variable Roles & Feature Units

Physiological variables are categorized into formal methodological roles:

| Variable | Methodological Role | Units | Description |
| :--- | :--- | :---: | :--- |
| `respiratory_rate` | `candidate_predictor` | `BPM` | Breaths per minute derived from zero-crossing cycle detection ($\ge 2$ breath cycles required). |
| `respiratory_phase` | `candidate_predictor` | `rad` | Instantaneous respiratory phase $\theta \in [-\pi, \pi)$ at the end of the window. |
| `ie_ratio` | `candidate_predictor` | `ratio` | Inspiratory duration divided by expiratory duration. |
| `heart_rate` | `covariate` | `BPM` | Mean heart rate from detected R-peaks (refractory period 300 ms, max 200 BPM). |
| `hrv_rmssd` | `moderator` | `ms` | Root mean square of successive RR differences, quantifying short-term variability. |
| `hrv_sdnn` | `moderator` | `ms` | Standard deviation of RR intervals. |
| `pnn50` | `moderator` | `%` | Percentage of successive RR differences exceeding 50 ms. |
| `eda_tonic` | `moderator` | `uS` | Mean tonic skin conductance level. |
| `slow_breathing` | `possible_intervention_variable` | `arbitrary` | Operator flag for paced or controlled breathing interventions. |
| `theta_power_rel` | Neural feature | `ratio` | Relative power in theta band (4–8 Hz). |
| `alpha_power_rel` | Neural feature | `ratio` | Relative power in alpha band (8–12 Hz). |
| `beta_power_rel` | Neural feature | `ratio` | Relative power in beta band (13–30 Hz). |
| `gamma_power_rel` | Neural feature | `ratio` | Relative power in gamma band (30–45 Hz). |
| `spectral_centroid`| Neural feature | `Hz` | Frequency center of gravity across power spectrum. |
| `rms_amplitude` | Neural feature | `uV` | Root mean square amplitude across channels. |

---

## Empirical Confound Controls

To establish that cross-modal neural-autonomic relationships are not artifacts of linear autocorrelation, shared non-stationarities, or condition-level mean shifts, four orthogonal surrogate controls are applied:

1. **Circular Shift (`circular_shift`):**
   Cyclically shifts the physiological series by a fixed offset $\tau$ (e.g. 5.0 seconds).
   *Preserves:* Exact marginal distribution, power spectrum, and periodicity.
   *Destroys:* Instantaneous temporal and phase alignment with neural windows.

2. **Block Shift (`block_shift`):**
   Partitions the physiological stream into contiguous multi-second blocks and shifts them cyclically.
   *Preserves:* Intra-block autocorrelation and non-stationary structure.
   *Destroys:* Continuous cross-modal coherence across block boundaries.

3. **Matched-Variance Fourier Surrogate (`matched_variance`):**
   Phase-randomizes intermediate Fourier coefficients ($\phi \sim U[-\pi, \pi]$) while preserving Fourier amplitudes and empirical signal variance.
   *Preserves:* Broadband power spectrum, variance, and linear autocorrelation.
   *Destroys:* Specific physiological waveform dynamics, R-peaks, and breath morphology.

4. **Condition-Preserving Permutation (`condition_preserving_permutation`):**
   Permutes feature vectors across windows strictly within subsets sharing the same task or resting condition.
   *Preserves:* Condition-level means and variances.
   *Destroys:* Chronological sequence and window-specific neural-physiological coupling.

---

## Programmatic API Usage

```python
from tools.embodied_controls.aligner import EmbodiedControlAligner
from tools.embodied_controls.types import InterpolationMethod

aligner = EmbodiedControlAligner(
    common_clock_hz=100.0,
    interpolation_method=InterpolationMethod.CAUSAL_LINEAR,
    lag_candidates_s=[-3.0, -2.0, -1.0, 0.0, 1.0, 2.0, 3.0],
    is_synthetic=False,
)

# Align neural windows with continuous physiology
report = aligner.align(
    neural_windows=eeg_window_records,
    physiology_stream=physiology_dict,
    conditions=["rest", "rest", "task", "task"],
)

# Export deterministic, null-safe JSON
json_data = report.to_json(indent=2)
```

---

## Command-Line Tool

```bash
# Synthetic benchmark alignment with Markdown output
python scripts/align_embodied_controls.py --synthetic --format markdown

# Alignment of user-supplied EEG windows and physiology stream
python scripts/align_embodied_controls.py \
  --eeg-windows data/eeg_windows.json \
  --physio-stream data/physiology_stream.json \
  --common-clock-hz 100.0 \
  --interpolation causal_linear \
  --format json \
  --output outputs/embodied_alignment.json
```
