# Multivariate Surrogate Null Audit (HOLD / SYNTHETIC_ONLY)

Owner:
- `tools/surrogate_audit/**`
- `tests/surrogate_audit/**`
- `docs/surrogate_audit/mv_null_contract.md`

## HOLD

This surface is **SYNTHETIC_ONLY**. It never emits scientific `VALIDATED`.

## Round 6 status

The Round 6 production candidate was **not present** on verified `origin/main`
(`3f3fe8593303184cb88eef056c1322f3d4e57a16`). This package is a **separate**
verifier/API implementing the stated contract. It must **not** be read as a
test of the missing Round 6 candidate (`round6_candidate_tested=false`).

Existing `validation/surrogate_testing.py` (per-channel FT/IAAFT gates) was left
unmodified.

## Null assumptions (not interchangeable)

| Method | Preserves | Does not guarantee |
| --- | --- | --- |
| **MV-FPR** | Full complex cross-spectral tensor via a **shared** phase multiplier per randomized frequency | Per-channel amplitude quantiles |
| **MV-IAAFT** | Exact per-channel sorted values after rank adjustment; targets auto-spectra each iteration | Strict `1e-3` **post-rank** full cross-spectral error |

## Definitions

### Cross-spectral error

With real-FFT coefficients `F` of shape `(n_channels, n_freq)`:

```
C[f, i, j] = F[i, f] * conj(F[j, f]) / n_time
error = ||C_surr - C_orig||_F / ||C_orig||_F
```

This is the **full** channel×channel complex matrix at every frequency — not
per-channel power spectra alone. The relative cross-spectral error is scale-invariant;
Fourier coefficients are normalized by original peak spectral magnitude before forming
cross-products or auto-spectral squares, completely preventing float underflow or overflow
across extreme dynamic ranges (e.g. `1e-250` to `1e250`). No absolute denominator floor is
applied, preventing false passes at small signal scales.

### Cross- versus auto-spectrum mutations

Independent per-channel phase shifts preserve auto-spectra to machine precision but
destroy cross-channel phase alignments (`relative_cross_spectral_error > 0.5`). The audit
strictly enforces full tensor evaluation so that mutations preserving auto-spectra cannot
falsely pass.

### Tolerance fail-closed validation

Audit tolerances (`fpr_spectral_atol`, `spectral_gate`) and `max_iter` are validated as
finite positive values, rejecting invalid non-positive, NaN, or non-numeric arguments.

### Marginal error

```
max over channels of max_t |sort(surr[c])_t - sort(orig[c])_t|
```

Exact rank restoration yields ~0.

### MV-FPR randomized bins

- Randomized: `rfft` bins `1 .. n_freq-2` when `n_time` even; `1 .. n_freq-1` when odd.
- Fixed real: DC (`0`); Nyquist (`n_freq-1`) when `n_time` even.

## Strict 1e-3 post-rank gate

IAAFT quantile restoration can (and often does) break a `1e-3` full
cross-spectral contract. This audit:

1. Returns the **post-rank** signal by default.
2. Reports **both** pre-rank and post-rank full cross-spectral errors.
3. Labels `spectral_gate_status=UNMET` when post-rank error `> 1e-3`.
4. Does **not** hide the miss by substituting the pre-rank signal or by
   reporting only auto-spectra.

## Run

```bash
PYTHONPATH=. python -m pytest tests/surrogate_audit -q
python -m compileall -q tools/surrogate_audit tests/surrogate_audit
git diff --check
```
