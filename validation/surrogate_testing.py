"""Surrogate null-hypothesis testing for topological/connectivity EEG metrics.

Persistent-homology and phase-winding metrics on multichannel EEG can look
"structured" purely because each channel has coloured (non-white) power spectra;
a topology metric can be large even with no genuine cross-channel synchronization.
The standard guard in this literature is to compare the real metric against a
distribution of the same metric computed on **phase-randomized surrogates** that
preserve each channel's power spectrum (and, for IAAFT, its amplitude
distribution) while destroying cross-channel phase relationships. This module is
that gate. It is metric-agnostic: pass any callable that maps a
``(n_channels, n_timepoints)`` array to a scalar.

References (standard framing, not novel): Theiler et al. 1992 (FT surrogates);
Schreiber & Schmitz 1996/2000 (IAAFT). The key correctness point below is that
for testing *cross-channel* structure the phases must be randomized
*independently per channel* -- randomizing all channels with the same draw
preserves relative inter-channel phase and therefore tests a different, weaker
null (exposed here as ``preserve_cross_channel_lag=True``).
"""
from __future__ import annotations

import numpy as np

EPS = 1e-12
MIN_TIMEPOINTS = 16  # FFT-based surrogates need enough samples for frequency resolution


def _validate_ts(ts: np.ndarray) -> np.ndarray:
    arr = np.asarray(ts, dtype=float)
    if arr.ndim != 2:
        raise ValueError(f"timeseries must be 2D (n_channels, n_timepoints), got {arr.shape}")
    if arr.shape[0] < 2:
        raise ValueError(f"need at least 2 channels, got {arr.shape[0]}")
    if arr.shape[1] < MIN_TIMEPOINTS:
        raise ValueError(f"need at least {MIN_TIMEPOINTS} timepoints, got {arr.shape[1]}")
    if not np.all(np.isfinite(arr)):
        raise ValueError("timeseries contains non-finite values")
    return arr


def _ft_surrogate(arr: np.ndarray, rng, preserve_cross_channel_lag: bool) -> np.ndarray:
    """One Fourier-transform phase-randomized surrogate of arr (n_ch, n_t).

    Preserves each channel's amplitude spectrum exactly. Default: independent
    per-channel random phases (destroys cross-channel phase structure -- the
    correct null for connectivity/topology). If preserve_cross_channel_lag: a
    single common random phase offset is added to every channel's original
    phases, preserving relative inter-channel phase (a weaker null).
    """
    n_ch, n_t = arr.shape
    X = np.fft.rfft(arr, axis=1)
    n_freq = X.shape[1]
    mag = np.abs(X)
    orig_phase = np.angle(X)

    # random phases for non-DC / non-Nyquist bins only (those must stay real)
    hi = n_freq - 1 if (n_t % 2 == 0) else n_freq  # last bin is Nyquist iff n_t even
    if preserve_cross_channel_lag:
        common = rng.uniform(0, 2 * np.pi, size=n_freq)
        new_phase = orig_phase + common[None, :]
    else:
        new_phase = rng.uniform(0, 2 * np.pi, size=(n_ch, n_freq))
    # keep DC (bin 0) real; keep Nyquist real when present
    new_phase[:, 0] = 0.0
    if n_t % 2 == 0:
        new_phase[:, hi] = 0.0
    Xs = mag * np.exp(1j * new_phase)
    return np.fft.irfft(Xs, n=n_t, axis=1)


def _iaaft_surrogate(arr: np.ndarray, rng, max_iter: int = 50) -> np.ndarray:
    """One IAAFT surrogate (per channel): preserves amplitude spectrum AND the
    empirical value distribution, via iterative rank-matching (Schreiber &
    Schmitz 1996). preserve_cross_channel_lag does not apply to IAAFT (each
    channel is matched independently); documented in the public wrapper.
    """
    n_ch, n_t = arr.shape
    out = np.empty_like(arr)
    for c in range(n_ch):
        x = arr[c]
        target_amp = np.abs(np.fft.rfft(x))
        sorted_x = np.sort(x)
        s = rng.permutation(x)
        prev_rank = None
        for _ in range(max_iter):
            # 1) impose amplitude spectrum, keep current phases
            S = np.fft.rfft(s)
            s = np.fft.irfft(target_amp * np.exp(1j * np.angle(S)), n=n_t)
            # 2) impose amplitude distribution via rank substitution
            ranks = np.argsort(np.argsort(s))
            s = sorted_x[ranks]
            if prev_rank is not None and np.array_equal(ranks, prev_rank):
                break
            prev_rank = ranks
        out[c] = s
    return out


def phase_randomize_surrogate(
    timeseries: np.ndarray,
    method: str = "ft",
    n_surrogates: int = 200,
    random_state=None,
    preserve_cross_channel_lag: bool = False,
) -> np.ndarray:
    """Generate phase-randomized surrogates of a (n_channels, n_timepoints) series.

    method="ft"    : Fourier phase randomization, preserving each channel's
                     amplitude spectrum. Cross-channel phases are randomized
                     independently by default (correct null for cross-channel
                     structure); set preserve_cross_channel_lag=True for the
                     weaker null that preserves relative inter-channel phase.
    method="iaaft" : additionally preserves each channel's amplitude
                     distribution (iterative rank-matching). Per-channel;
                     preserve_cross_channel_lag is ignored (raises if True).

    Returns array of shape (n_surrogates, n_channels, n_timepoints).
    """
    arr = _validate_ts(timeseries)
    if n_surrogates < 1:
        raise ValueError(f"n_surrogates must be >= 1, got {n_surrogates}")
    rng = np.random.default_rng(random_state)
    method = method.lower()
    if method == "iaaft" and preserve_cross_channel_lag:
        raise ValueError("preserve_cross_channel_lag applies only to method='ft', not 'iaaft'")

    out = np.empty((n_surrogates, arr.shape[0], arr.shape[1]), dtype=float)
    for i in range(n_surrogates):
        if method == "ft":
            out[i] = _ft_surrogate(arr, rng, preserve_cross_channel_lag)
        elif method == "iaaft":
            out[i] = _iaaft_surrogate(arr, rng)
        else:
            raise ValueError(f"unknown method {method!r}; use 'ft' or 'iaaft'")
    if not np.all(np.isfinite(out)):
        raise ValueError("surrogate generation produced non-finite values")
    return out


def _eval_metric_safe(metric_fn, s: np.ndarray, kwargs: dict):
    """Evaluate metric_fn on one surrogate; return (value_or_None, failed: bool).

    Module-level (not a closure) so it is picklable for joblib's loky/multiprocessing
    backends. Exceptions are caught per-surrogate, matching the prior serial loop's
    semantics exactly (one bad surrogate does not abort the gate).
    """
    try:
        v = float(metric_fn(s, **kwargs))
    except Exception:
        return None, True
    if not np.isfinite(v):
        return None, True
    return v, False


def surrogate_test_topology_metric(
    real_timeseries: np.ndarray,
    metric_fn,
    metric_kwargs: dict | None = None,
    n_surrogates: int = 200,
    method: str = "ft",
    preserve_cross_channel_lag: bool = False,
    two_sided: bool = False,
    random_state=None,
    n_jobs: int = 1,
) -> dict:
    """Gate a scalar topology/connectivity metric against a phase-randomized null.

    ``metric_fn(ts, **metric_kwargs) -> float`` is evaluated on the real series
    and on every surrogate. p-value convention:
      * two_sided=False (default): tests whether the real value is more extreme
        than the null IN THE DIRECTION the real z-score points -- appropriate
        with a directional hypothesis (e.g. "meditation increases beta1").
        p = (#surrogates at least as extreme on that side + 1) / (n_used + 1).
      * two_sided=True: |value - null mean| based; use when there is no prior
        directional hypothesis (more conservative).
    Surrogates on which metric_fn raises are counted in ``n_failed`` and excluded;
    statistics use only successful surrogates, and n_surrogates reflects that.

    ``n_jobs`` (default 1, serial) is forwarded to ``joblib.Parallel`` to evaluate
    ``metric_fn`` on the ``n_surrogates`` surrogates concurrently -- this loop, not
    surrogate generation, is the dominant cost for expensive topology/PH metrics.
    Pass -1 for all cores. Results (including which surrogates failed) are
    identical to the serial path for any n_jobs; only wall-clock changes.
    """
    kwargs = metric_kwargs or {}
    real_value = float(metric_fn(_validate_ts(real_timeseries), **kwargs))
    if not np.isfinite(real_value):
        raise ValueError("metric_fn returned a non-finite value on the real data")

    surr = phase_randomize_surrogate(
        real_timeseries, method=method, n_surrogates=n_surrogates,
        random_state=random_state, preserve_cross_channel_lag=preserve_cross_channel_lag)

    if n_jobs == 1:
        results = [_eval_metric_safe(metric_fn, s, kwargs) for s in surr]
    else:
        from joblib import Parallel, delayed
        results = Parallel(n_jobs=n_jobs)(delayed(_eval_metric_safe)(metric_fn, s, kwargs) for s in surr)

    vals = [v for v, failed in results if not failed]
    n_failed = sum(1 for _v, failed in results if failed)
    vals = np.asarray(vals, dtype=float)
    n_used = int(vals.size)
    if n_used < 2:
        raise ValueError(f"too few usable surrogates ({n_used}); cannot form a null distribution")

    s_mean = float(vals.mean())
    s_std = float(vals.std(ddof=1))
    z = 0.0 if s_std < EPS else float((real_value - s_mean) / s_std)

    if two_sided:
        as_extreme = int(np.sum(np.abs(vals - s_mean) >= abs(real_value - s_mean)))
    elif real_value >= s_mean:
        as_extreme = int(np.sum(vals >= real_value))
    else:
        as_extreme = int(np.sum(vals <= real_value))
    p_value = float((as_extreme + 1) / (n_used + 1))

    out = {
        "real_value": real_value,
        "surrogate_values": vals,
        "surrogate_mean": s_mean,
        "surrogate_std": s_std,
        "z_score": z,
        "p_value": p_value,
        "n_surrogates": n_used,
        "n_failed": int(n_failed),
        "method": method,
        "preserve_cross_channel_lag": bool(preserve_cross_channel_lag),
        "two_sided": bool(two_sided),
        "passes_gate_p05": bool(p_value < 0.05),
        "metric_kind": "surrogate_null_test",
    }
    for k, v in out.items():
        if isinstance(v, float) and not np.isfinite(v):
            raise ValueError(f"non-finite surrogate-test output: {k}={v}")
    return out
