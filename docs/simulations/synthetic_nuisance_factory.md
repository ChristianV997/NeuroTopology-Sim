# Synthetic Nuisance-Scenario Factory: Operating-Characteristic Infrastructure

**Status**: `HOLD / SYNTHETIC_ONLY`
**Module**: `sim.nuisance_scenarios`
**Test Suite**: `tests/nuisance_scenarios`
**Owner**: Antigravity Agent D (Batch 2)

---

## 1. Executive Summary

This module implements a deterministic, reproducible, synthetic-only nuisance-scenario factory for evaluation studies and operating-characteristic benchmarking in NeuroTopology-Sim. It provides explicit parametric generation of:

1. **Controlled Colored Noise**: Power spectral density scaling as $S(f) \propto 1 / f^\chi$ with explicit DC frequency zeroing ($X(0) = 0$), even-sample Nyquist bin constraints, and pure NumPy log-log regression diagnostics.
2. **Target SNR Mixing**: Amplitude-scaled noise mixing achieving exact user-specified signal-to-noise ratios (in decibels) with respect to multichannel signal power.
3. **Electrode Coordinate Jitter**: 3D Gaussian coordinate perturbations with explicit units (`mm`, `cm`, `m`) supporting both unconstrained Cartesian displacement and sphere-renormalized radial projection.
4. **Independent RNG Streams**: Deterministic sub-generator spawning via `numpy.random.SeedSequence` ensuring bit-for-bit reproducibility and isolation across signal, noise, and coordinate generators.

> [!IMPORTANT]
> **Scientific Guardrails & Epistemic Boundaries**:
> - **Synthetic Only**: This factory is an engineering evaluation fixture. No biological realism or realistic head volume conduction is modeled or claimed.
> - **Not empirical evidence**: Generated arrays must not be treated as participant, clinical, or dataset-derived measurements.
> - **No network / remote data**: The package does not import or call network or remote-data clients; caller-supplied arrays and `signal_generator` callbacks remain caller-controlled. Tests use synthetic fixtures only and make no live API calls.
> - **No Classifier/Detector**: This module does not implement detection algorithms, threshold tuning, or ROC/PR classification scoring.
> - **No Claim States**: Results are tagged strictly with `HOLD / SYNTHETIC_ONLY` and report purely descriptive/engineering realized metrics.
> - **Pure NumPy**: Zero SciPy dependencies; all spectral, linear algebraic, and regression routines use standard `numpy`.
> - **Aliases and numeric bounds**: `from_dict` accepts `chi` / `jitter_std` / `jitter_units` / `sampling_rate_hz` and preserves them; conflicting canonical/alias values fail closed. Low-level `signal`/`clean_signal`, `coordinates`/`coords`, and `sfreq_hz`/`sampling_rate_hz` pairs must agree when both are supplied; `seed`/`rng` are mutually exclusive and require non-negative integer seeds (including arbitrary-precision positive integers), `Generator`, or `SeedSequence`. Coordinate units normalize to lowercase (`mm`/`cm`/`m`). Numeric strings, booleans in numeric fields, fractional integer fields, negative seeds, non-string or whitespace-only `scenario_id`, non-mapping or non-finite `metadata`, unknown string coordinate specifiers, zero-radius origin electrodes under `renormalize_to_sphere=True`, and invalid `f_min`/`f_max` bounds in `estimate_spectral_slope` are rejected fail-closed. Configurations must yield a finite, representable `n_samples >= 8`, matching the factory's spectral-slope estimator.
> - **Caller-array isolation**: `NuisanceScenarioFactory.generate` copies caller-supplied `clean_signal`, `coordinates`, and `signal_generator` outputs into owned float64 buffers before returning a `ScenarioResult`, so mutating result arrays cannot rewrite caller or generator buffers. Supplying both `clean_signal` and `signal_generator` fails closed.
> - **Serialization and identifiers**: Generated scenario IDs retain a readable prefix and append a stable 12-character SHA-256 digest of generation-affecting config fields. Unavailable spectral-fit diagnostics serialize as JSON `null`; `to_json` rejects non-finite JSON values.
> - **No label inference**: Scenario outputs never invent class/condition labels from nuisance parameters; caller `metadata` is preserved verbatim only.

---

## 2. Mathematical Formulations & Conventions

### 2.1 Colored Noise Generation ($1 / f^\chi$)

For a discrete time series of length $N$ sampled at frequency $f_s$, discrete one-sided Fourier frequencies are:
$$f_k = \frac{k f_s}{N}, \quad k \in \left\{0, 1, \dots, \left\lfloor \frac{N}{2} \right\rfloor \right\}$$

The complex spectrum $X(f_k)$ is constructed from independent Gaussian random variables for real and imaginary components:
$$X_{\text{raw}}(f_k) = Z_{r, k} + i Z_{i, k}, \quad Z_{r, k}, Z_{i, k} \sim \mathcal{N}(0, 1)$$

- **DC Handling**: The zero-frequency bin $k=0$ is explicitly forced to zero:
  $$X(0) = 0.0 + 0.0i$$
  This guarantees that the generated noise has zero mean in expectation prior to standardization.
- **Spectral Slope Scaling**: For positive frequency bins $k \ge 1$:
  $$X(f_k) = X_{\text{raw}}(f_k) \cdot f_k^{-\chi / 2}$$
  where:
  - $\chi = 0.0$: White noise (flat power spectrum $S(f) \propto f^0$).
  - $\chi = 1.0$: Pink noise ($S(f) \propto 1/f$).
  - $\chi = 2.0$: Brown/red noise ($S(f) \propto 1/f^2$).
- **Nyquist Bin Constraint**: For even $N$, the Nyquist bin $k = N/2$ is constrained to be strictly real:
  $$\text{Im}(X(f_{N/2})) = 0.0$$
- **Synthesis & Normalization**: The time-domain series is synthesized via inverse real fast Fourier transform (`np.fft.irfft`) and standardized per channel to zero mean and unit variance.

### 2.2 Empirical Spectral Slope Estimation

Empirical slope validation is performed in pure NumPy via log-log linear regression on the periodogram:
$$\text{PSD}(f_k) = \frac{1}{C} \sum_{c=1}^C \frac{|X_c(f_k)|^2}{f_s \cdot N}$$
A linear model is fit using `np.polyfit` over the valid frequency band $[f_{\text{low}}, f_{\text{high}}]$:
$$\ln \text{PSD}(f) = -\hat{\chi} \ln f + \beta$$
Returning the estimated slope $\hat{\chi} = -\text{slope}$ and the coefficient of determination $R^2$:
$$R^2 = 1 - \frac{\sum_k (\ln \text{PSD}_k - \hat{y}_k)^2}{\sum_k (\ln \text{PSD}_k - \overline{\ln \text{PSD}})^2}$$

### 2.3 Exact SNR Mixing (dB)

Given a clean multichannel signal $s \in \mathbb{R}^{C \times N}$ and raw noise $n \in \mathbb{R}^{C \times N}$:
1. **Signal Power**:
   $$P_s = \frac{1}{C \cdot N} \sum_{c=1}^C \sum_{t=1}^N s_{c, t}^2$$
2. **Raw Noise Power**:
   $$P_{n, \text{raw}} = \frac{1}{C \cdot N} \sum_{c=1}^C \sum_{t=1}^N n_{c, t}^2$$
3. **Target Noise Power**:
   $$P_{n, \text{target}} = P_s \cdot 10^{-\text{SNR}_{\text{dB}} / 10}$$
4. **Noise Scale Factor**:
   $$\alpha = \sqrt{\frac{P_{n, \text{target}}}{P_{n, \text{raw}}}}$$
5. **Noisy Signal Assembly & Verification**:
   $$x = s + \alpha n$$
   $$\text{SNR}_{\text{realized}} = 10 \log_{10} \left( \frac{P_s}{P_{n, \text{realized}}} \right)$$

*Edge Case Rule*: If $P_s \le 10^{-15}$ or $P_{n, \text{raw}} \le 10^{-15}$, if inputs are non-finite, or if the requested target noise power is outside the normal float64 range, the mixer fails closed with an explicit `ValueError`. Scaling and realized-SNR diagnostics are computed in log space to avoid intermediate overflow and epsilon-clamping at high SNR.

### 2.4 Electrode Coordinate Jitter

Given initial electrode coordinates $R \in \mathbb{R}^{C \times 3}$:
1. Perturbations $\Delta R \sim \mathcal{N}(0, \sigma^2 I)$ are generated according to `jitter_std` and declared `units` (`mm`, `cm`, `m`).
2. **Mode A — Unconstrained Cartesian Jitter** (`renormalize_to_sphere=False`):
   $$\tilde{R}_c = R_c + \Delta R_c$$
   Electrodes displace freely in 3D Euclidean space.
3. **Mode B — Sphere-Projected Jitter** (`renormalize_to_sphere=True`):
   $$\tilde{R}_c = \frac{R_c + \Delta R_c}{\|R_c + \Delta R_c\|_2} \|R_c\|_2$$
   Electrodes are radially projected back onto the sphere shell, preserving the exact radius $\|R_c\|_2$.
4. **Displacement Diagnostics**:
   $$d_c = \|\tilde{R}_c - R_c\|_2$$
   $$\text{Mean} = \frac{1}{C} \sum_{c=1}^C d_c, \quad \text{Max} = \max_c d_c, \quad \text{RMS} = \sqrt{\frac{1}{C} \sum_{c=1}^C d_c^2}$$

---

## 3. Public API & Usage Examples

```python
import sim.nuisance_scenarios as ns

# 1. Define single scenario configuration
cfg = ns.NuisanceScenarioConfig(
    noise_exponent=1.0,          # chi = 1.0 (pink noise)
    target_snr_db=6.0,           # +6 dB SNR
    coordinate_jitter_std=2.0,   # 2.0 mm displacement standard deviation
    coordinate_units="mm",
    renormalize_to_sphere=True,  # project back onto spherical scalp shell
    sfreq_hz=250.0,
    duration_s=2.0,
    n_channels=8,
    seed=42,
)

# 2. Generate scenario with synthetic spherical coordinates
result = ns.NuisanceScenarioFactory.generate(cfg, coordinates="synthetic_sphere")

# 3. Inspect realized diagnostics
print(f"Scenario ID: {result.scenario_id}")
print(f"Realized SNR: {result.diagnostics.realized_snr_db:.4f} dB")
print(f"Mean Jitter: {result.diagnostics.jitter_mean_disp:.4f} mm")
print(f"Status: {result.diagnostics.status}")

# 4. Serialize to compact JSON metadata
json_meta = result.to_json(include_arrays=False)
```

Automatically generated scenario IDs include all generation-affecting configuration fields, so fine-grained grid values do not collapse to the same rounded display ID. A spectral-slope fit that has too few valid frequency bins is reported as unavailable (`null` in JSON), not as the non-standard JSON token `NaN`.

### Parameter Sweeps with `NuisanceGridConfig`

```python
grid = ns.NuisanceGridConfig(
    chi_values=[0.0, 1.0, 2.0],
    snr_db_values=[-6.0, 0.0, 6.0],
    jitter_std_values=[0.0, 2.0],
    seeds=[42, 100],
    renormalize_options=[False, True],
)

scenario_list = ns.NuisanceScenarioFactory.generate_grid(grid, coordinates="synthetic_sphere")
print(f"Generated {len(scenario_list)} scenarios across grid.")
```

---

## 4. Verification & Testing Summary

The module is verified by a dedicated test suite in `tests/nuisance_scenarios/`:

| Test Module | Coverage & Verification Invariants |
|---|---|
| `test_seed_reproducibility.py` | Bit-for-bit identical outputs on matching seeds; RNG stream isolation across noise and coordinates. |
| `test_colored_noise.py` | Strict zeroing of DC component ($X(0) = 0$); even and odd length support; unit variance standardization; empirical slope recovery for $\chi \in \{0.0, 1.0, 1.5, 2.0\}$. |
| `test_target_snr.py` | Numerical precision of realized SNR ($< 10^{-6}$ dB); high representable and out-of-range SNR behavior; zero-signal and zero-noise fail-closed errors; shape and finiteness validation. |
| `test_coordinate_jitter.py` | Cartesian vs sphere projection verification; radius preservation under projection; displacement scaling; unit checking (`mm`, `cm`, `m`). |
| `test_factory_and_grid.py` | End-to-end factory generation; custom callable integration; grid parameter expansion; JSON serialization fidelity; `HOLD / SYNTHETIC_ONLY` audit tag. |
