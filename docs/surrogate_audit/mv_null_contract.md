# Multivariate Surrogate Null Audit (HOLD / SYNTHETIC_ONLY)

Owner:
- `tools/surrogate_audit/**`
- `tests/surrogate_audit/**`
- `docs/surrogate_audit/mv_null_contract.md`

## HOLD

This surface is **SYNTHETIC_ONLY**. It never emits scientific `VALIDATED`.

## Round 6 status / production separation

Live `origin/main` already ships production nulls at
`tools/surrogate_nulls/nulls.py` (`common_phase_prichard_theiler`,
`mv_iaaft_rank_adjusted`) with a scale-invariant `_csd_rel_error` gate.

This package (`tools/surrogate_audit/**`) remains an **independent** synthetic
audit API: its generators and metrics do **not** import production for expected
values. A separate **production-import bridge** in
`tests/surrogate_audit/test_metrics_scale_invariance.py` hard-imports the real
`nulls.py` leaf and scores production draws with audit metrics. Oracle
independence stays explicit: audit metrics are never computed by calling
production residual helpers as the source of truth for audit gates.

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
per-channel power spectra alone. The relative cross-spectral error is scale-invariant.
Both series are **peak-normalized in the time domain before ``rfft``**, then
Fourier coefficients are peak-normalized again before forming cross-products /
auto-spectral squares. That ordering avoids FFT overflow near the top of finite
float64 (e.g. identical `1e308` series) and avoids absolute-denominator-floor
false passes at tiny scales (e.g. `1e-20`). No absolute denominator floor is
applied to the relative residual.

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
