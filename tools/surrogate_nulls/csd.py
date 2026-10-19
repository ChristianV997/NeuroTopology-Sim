"""Spectral-matrix estimators, PSD diagnostics, and ensemble checks for the surrogate nulls.

Synthetic arrays only. Stdlib only. No subprocess, network, or dataset access.

Conventions match ``spectral.py``: the periodogram cross-spectrum is
``C[k] = X(k) X(k)^H / n`` with the unnormalised rFFT.

Estimators (each one is named in every report that uses it):

- ``single_periodogram``: one unsmoothed periodogram per bin. For ``d >= 2`` channels
  this is rank one at every bin, so it cannot describe cross-channel structure. It is
  supported so that the rank problem is visible, not hidden.
- ``periodogram_boxcar``: the periodogram averaged over neighbouring bins within a
  halfwidth. Edges are truncated and the average is normalised by the count used.
- ``multitaper``: a sine multitaper (Riedel and Sidorenko, 1995). The K tapers are
  orthonormal, ``h_j(t) = sqrt(2/(n+1)) sin(pi (j+1)(t+1)/(n+1))``, and the estimate is the
  average over tapers of the tapered periodogram matrices. With ``K >= d + 1`` the estimate
  has full rank at each bin, which is the reason for the default ``K``.
- ``supplied``: a caller-provided spectral matrix per bin. It is validated, never estimated.

Shrinkage (optional, applied after estimation): ``C <- (1 - lam) C + lam (tr C / d) I``
with ``lam`` in ``[0, 1]``. It is explicit and reported. It is not applied by default.

PSD policy: a Hermitian matrix whose smallest eigenvalue is below ``-psd_tol * trace`` is
materially indefinite and raises ``NonPositiveDefiniteError``. Smaller negative eigenvalues
are rounding noise. They are regularised by the null, and the bin is reported.
"""
from __future__ import annotations

import cmath
import math
import numbers

from . import spectral as sp

ESTIMATORS = ("single_periodogram", "periodogram_boxcar", "multitaper", "supplied")
DEFAULT_RANK_TOL = 1e-10
DEFAULT_PSD_TOL = 1e-10


def default_n_tapers(n_time, n_channels):
    """Default multitaper count: at least ``d + 2`` so the estimate keeps rank headroom."""
    return min(n_time, max(4, n_channels + 2))


def sine_tapers(n_time, n_tapers):
    """Orthonormal sine tapers of length ``n_time``: a list of ``n_tapers`` lists."""
    if isinstance(n_time, bool) or not isinstance(n_time, numbers.Integral) or n_time < 1:
        raise sp.SurrogateInputError("n_time must be a positive integer")
    if isinstance(n_tapers, bool) or not isinstance(n_tapers, numbers.Integral) or not (1 <= n_tapers <= n_time):
        raise sp.SurrogateInputError(f"n_tapers must be an integer in [1, {n_time}], got {n_tapers!r}")
    scale = math.sqrt(2.0 / (n_time + 1))
    return [
        [scale * math.sin(math.pi * (j + 1) * (t + 1) / (n_time + 1)) for t in range(n_time)]
        for j in range(n_tapers)
    ]


def multitaper_csd(data, n_tapers):
    """Sine-multitaper cross-spectral estimate, one ``d x d`` matrix per rFFT bin."""
    n_channels = len(data)
    n_time = len(data[0])
    tapers = sine_tapers(n_time, n_tapers)
    bins = sp.n_freq(n_time)
    acc = [[[0j] * n_channels for _ in range(n_channels)] for _ in range(bins)]
    for taper in tapers:
        spectra = [sp.rfft([channel[t] * taper[t] for t in range(n_time)]) for channel in data]
        for k in range(bins):
            for i in range(n_channels):
                for j in range(n_channels):
                    acc[k][i][j] += spectra[i][k] * spectra[j][k].conjugate() / n_tapers
    return acc


def periodogram_boxcar_csd(data, halfwidth):
    """Boxcar-smoothed periodogram cross-spectrum; ``halfwidth = 0`` is the single periodogram."""
    spectra = [sp.rfft(channel) for channel in data]
    raw = sp.periodogram_csd(spectra, len(data[0]))
    return sp.smooth_csd(raw, halfwidth)


def shrink_csd(csd_by_bin, lam):
    """``(1 - lam) C + lam (tr C / d) I`` at every bin. ``lam`` must lie in ``[0, 1]``."""
    if isinstance(lam, bool) or not isinstance(lam, numbers.Real) or not math.isfinite(lam) or not (0.0 <= lam <= 1.0):
        raise sp.SurrogateInputError(f"shrinkage must be a finite number in [0, 1], got {lam!r}")
    out = []
    for mat in csd_by_bin:
        d = len(mat)
        mean_power = sum(mat[i][i].real for i in range(d)) / d
        out.append([
            [(1.0 - lam) * mat[i][j] + (lam * mean_power if i == j else 0.0) for j in range(d)]
            for i in range(d)
        ])
    return out


def _jacobi_symmetric_eigvals(a, max_sweeps=80):
    """Eigenvalues of a real symmetric matrix by cyclic Jacobi rotations, sorted descending.

    The matrix is first scaled by an exact power of two, so its largest entry lies in
    ``[0.5, 1)``, and the eigenvalues are scaled back exactly. Every stop test is then relative
    to the matrix's own norm. A stop test with an absolute floor would end the iteration before
    any rotation at tiny scales, and the diagonal would be reported as the eigenvalues.
    """
    n = len(a)
    peak = max(abs(float(v)) for row in a for v in row)
    if peak == 0.0:
        return [0.0] * n
    exponent = math.frexp(peak)[1]
    m = [[math.ldexp(float(v), -exponent) for v in row] for row in a]
    for _ in range(max_sweeps):
        off = 0.0
        diag = 0.0
        for i in range(n):
            diag += m[i][i] * m[i][i]
            for j in range(i + 1, n):
                off += m[i][j] * m[i][j]
        if off == 0.0 or off <= 1e-30 * (diag + 2.0 * off):
            break
        for p in range(n - 1):
            for q in range(p + 1, n):
                apq = m[p][q]
                if apq == 0.0:
                    continue
                theta = (m[q][q] - m[p][p]) / (2.0 * apq)
                t = (1.0 if theta >= 0.0 else -1.0) / (abs(theta) + math.sqrt(theta * theta + 1.0))
                c = 1.0 / math.sqrt(t * t + 1.0)
                s = t * c
                for k in range(n):
                    mkp = m[k][p]
                    mkq = m[k][q]
                    m[k][p] = c * mkp - s * mkq
                    m[k][q] = s * mkp + c * mkq
                for k in range(n):
                    mpk = m[p][k]
                    mqk = m[q][k]
                    m[p][k] = c * mpk - s * mqk
                    m[q][k] = s * mpk + c * mqk
    return sorted((math.ldexp(m[i][i], exponent) for i in range(n)), reverse=True)


def hermitian_eigenvalues(matrix):
    """Eigenvalues of a Hermitian matrix, sorted descending.

    Uses the real embedding ``[[A, -B], [B, A]]`` for ``H = A + iB``. Each eigenvalue of
    ``H`` appears twice in the embedding, so every second value of the sorted list is kept.
    """
    d = len(matrix)
    emb = [[0.0] * (2 * d) for _ in range(2 * d)]
    for i in range(d):
        for j in range(d):
            re = matrix[i][j].real
            im = matrix[i][j].imag
            emb[i][j] = re
            emb[i][j + d] = -im
            emb[i + d][j] = im
            emb[i + d][j + d] = re
    return _jacobi_symmetric_eigvals(emb)[0::2]


def participation_ratio(eigs):
    """``(sum lam)^2 / sum lam^2`` over the non-negative eigenvalues.

    It is a continuous measure of how many directions the covariance actually uses. A value
    near 1 means one direction dominates, even when the numerical rank is larger.
    """
    positive = [max(v, 0.0) for v in eigs]
    total = sum(positive)
    squares = sum(v * v for v in positive)
    return (total * total / squares) if squares > 0.0 else 0.0


def _validate_hermitian_matrix(matrix):
    """Square, finite, Hermitian. Raises ``SurrogateInputError`` otherwise."""
    d = len(matrix)
    if d < 1 or any(len(row) != d for row in matrix):
        raise sp.SurrogateInputError("matrix must be a non-empty square array")
    for row in matrix:
        for value in row:
            if isinstance(value, bool) or not isinstance(value, numbers.Number):
                raise sp.SurrogateInputError(f"matrix entries must be numbers, got {type(value).__name__}")
            z = complex(value)
            if not (math.isfinite(z.real) and math.isfinite(z.imag)):
                raise sp.SurrogateInputError("matrix contains non-finite entries")
    if not sp.is_hermitian(matrix):
        raise sp.SurrogateInputError("matrix is not Hermitian (relative to its largest entry)")


def matrix_diagnostics(matrix, rank_tol=DEFAULT_RANK_TOL, psd_tol=DEFAULT_PSD_TOL):
    """Numerical rank, smallest eigenvalue relative to trace, condition number, and participation.

    Returns ``(effective_rank, min_eig_rel, condition, participation)``. ``effective_rank``
    counts eigenvalues above ``rank_tol`` times the largest; ``participation`` is the
    continuous ratio from ``participation_ratio``.

    Malformed input raises ``SurrogateInputError``: an empty or non-square array, a non-numeric or
    boolean entry, a non-finite entry, or a matrix that is not Hermitian relative to its largest
    entry (``spectral.is_hermitian``). The draw path applies the same validation. Its reference scale is
    ``max(trace, largest entry)``: the trace for a positive-semidefinite matrix, and the largest
    entry otherwise. An all-zero matrix is positive semidefinite with rank 0. A matrix whose
    trace is not positive while its entries are nonzero is not positive semidefinite, and it
    raises ``NonPositiveDefiniteError``. So does a matrix whose smallest eigenvalue is below
    ``-psd_tol * scale``. Rounding-level negative eigenvalues are returned, not raised; the null
    decides how to regularise them.
    """
    _validate_hermitian_matrix(matrix)
    return _diagnose_validated(matrix, rank_tol=rank_tol, psd_tol=psd_tol)


def _diagnose_validated(matrix, rank_tol=DEFAULT_RANK_TOL, psd_tol=DEFAULT_PSD_TOL):
    """``matrix_diagnostics`` for a matrix the caller has already validated.

    The caller must have run ``_validate_hermitian_matrix`` on the matrix. The draw path does this
    once per bin, so the diagnostics do not repeat it.
    """
    d = len(matrix)
    largest_entry = max(abs(matrix[i][j]) for i in range(d) for j in range(d))
    if largest_entry == 0.0:
        return 0, 0.0, 1.0, 0.0
    trace = sum(matrix[i][i].real for i in range(d))
    if trace <= 0.0:
        raise sp.NonPositiveDefiniteError(
            f"trace {trace!r} is not positive while entries are nonzero (largest entry "
            f"{largest_entry!r}); the matrix is not positive semidefinite"
        )
    scale = max(trace, largest_entry)
    eigs = hermitian_eigenvalues(matrix)
    smallest = eigs[-1]
    if smallest < -psd_tol * scale:
        raise sp.NonPositiveDefiniteError(
            f"materially indefinite: smallest eigenvalue {smallest!r} is below "
            f"-psd_tol*scale = {-psd_tol * scale!r}"
        )
    largest = eigs[0]
    effective_rank = sum(1 for v in eigs if v > rank_tol * largest)
    min_eig_rel = smallest / trace
    if smallest > rank_tol * largest:
        condition = largest / smallest
    else:
        condition = math.inf
    return effective_rank, min_eig_rel, condition, participation_ratio(eigs)


def diagnose_csd(csd_by_bin, rank_tol=DEFAULT_RANK_TOL, psd_tol=DEFAULT_PSD_TOL):
    """Per-bin numerical rank, relative minimum eigenvalue, condition number, and participation ratio."""
    ranks = []
    min_rel = []
    conds = []
    parts = []
    for mat in csd_by_bin:
        rank, rel, cond, part = matrix_diagnostics(mat, rank_tol=rank_tol, psd_tol=psd_tol)
        ranks.append(rank)
        min_rel.append(rel)
        conds.append(cond)
        parts.append(part)
    return {"effective_rank": tuple(ranks), "min_eig_rel": tuple(min_rel),
            "condition": tuple(conds), "participation_ratio": tuple(parts)}


def estimate_csd(data, estimator, *, n_tapers=None, smoothing_halfwidth=1, shrinkage=0.0):
    """Estimate the per-bin spectral matrix for ``data`` (validated, real, finite channels).

    Returns ``(csd_by_bin, info)``. ``info`` names the estimator and its parameters so that
    every downstream report can state them. ``supplied`` is not accepted here; supplied
    matrices go straight to the null.
    """
    if estimator not in ESTIMATORS or estimator == "supplied":
        raise sp.SurrogateInputError(
            f"estimator must be one of {tuple(e for e in ESTIMATORS if e != 'supplied')}, got {estimator!r}"
        )
    data = sp.as_float_matrix(data)
    n_channels = len(data)
    n_time = len(data[0])
    info = {"estimator": estimator, "n_tapers": None, "smoothing_halfwidth": None,
            "shrinkage": float(shrinkage), "source": "estimated_from_input"}
    bins = sp.n_freq(n_time)
    if estimator == "multitaper":
        k = default_n_tapers(n_time, n_channels) if n_tapers is None else n_tapers
        csd = multitaper_csd(data, k)
        info["n_tapers"] = k
        # Nominal complex-Gaussian degrees of freedom: 2 per taper. Approximate, because
        # sine tapers are only approximately independent for coloured signals.
        info["dof_per_bin"] = tuple(2 * k for _ in range(bins))
    elif estimator == "periodogram_boxcar":
        csd = periodogram_boxcar_csd(data, smoothing_halfwidth)
        info["smoothing_halfwidth"] = smoothing_halfwidth
        info["dof_per_bin"] = tuple(
            2 * (min(bins, k + smoothing_halfwidth + 1) - max(0, k - smoothing_halfwidth)) for k in range(bins)
        )
    else:
        csd = periodogram_boxcar_csd(data, 0)
        info["smoothing_halfwidth"] = 0
        info["dof_per_bin"] = tuple(2 for _ in range(bins))
    if shrinkage:
        csd = shrink_csd(csd, shrinkage)
    return csd, info


def validate_supplied_csd(csd_by_bin, n_channels, n_time):
    """Shape and Hermitian checks for a caller-supplied spectral estimate."""
    for name, value in (("n_channels", n_channels), ("n_time", n_time)):
        if isinstance(value, bool) or not isinstance(value, numbers.Integral) or value < 1:
            raise sp.SurrogateInputError(f"{name} must be a positive integer, got {value!r}")
    expected_bins = sp.n_freq(n_time)
    if len(csd_by_bin) != expected_bins:
        raise sp.SurrogateInputError(
            f"supplied spectral estimate has {len(csd_by_bin)} bins; n_time={n_time} needs {expected_bins}"
        )
    for k, mat in enumerate(csd_by_bin):
        if len(mat) != n_channels or any(len(row) != n_channels for row in mat):
            raise sp.SurrogateInputError(
                f"supplied spectral estimate bin {k} must be {n_channels}x{n_channels}"
            )
        try:
            _validate_hermitian_matrix(mat)
        except sp.SurrogateInputError as exc:
            raise sp.SurrogateInputError(f"supplied spectral estimate bin {k}: {exc}") from exc
    return [[[complex(v) for v in row] for row in mat] for mat in csd_by_bin]


PI_STEP_TOL = 1e-9  # an adjacent relative phase within this of +/-pi is treated as exactly pi


def phase_loop_winding(spectra, k):
    """Integer winding of the phase loop 0 -> 1 -> ... -> d-1 -> 0 at bin ``k``.

    A test statistic for designed signals. It is not a project metric.

    - One or two channels: the winding is 0. A loop with fewer than three edges cannot wind,
      because the two edges of a two-channel loop cancel.
    - An adjacent relative phase at exactly +/-pi (within ``PI_STEP_TOL``) is ambiguous under the
      minimal-wrap convention, so the winding is undefined. This raises ``SurrogateInputError``
      rather than returning an arbitrary integer. The real-coefficient zero-lag null produces such
      steps, so its winding is undefined.
    """
    d = len(spectra)
    if d < 3:
        return 0
    phases = [cmath.phase(spectra[c][k]) for c in range(d)]
    steps = [_wrap(phases[c] - phases[(c + 1) % d]) for c in range(d)]
    if any(abs(abs(step) - math.pi) <= PI_STEP_TOL for step in steps):
        raise sp.SurrogateInputError(
            f"winding at bin {k} is undefined: an adjacent relative phase is at +/-pi"
        )
    return round(sum(steps) / (2.0 * math.pi))


def winding_variation(x, generator, seeds, bin_k, *, statistic=phase_loop_winding):
    """Whether a surrogate procedure varies the phase statistic across an ensemble.

    ``generator(x, seed)`` must return ``(signals, report)``. The statistic is computed on
    the rFFT of each surrogate at ``bin_k``. ``varies_from_original`` is True only if some
    surrogate differs from the statistic on the original data. A procedure that leaves the
    statistic unchanged reports False and must not be used to test that statistic. If the
    statistic is undefined for a surrogate (see ``phase_loop_winding``), the call raises
    ``SurrogateInputError``.
    """
    if isinstance(bin_k, bool) or not isinstance(bin_k, numbers.Integral):
        raise sp.SurrogateInputError("bin_k must be an integer")
    seeds = list(seeds)
    if not seeds:
        raise sp.SurrogateInputError("seeds must be non-empty")
    x = sp.as_float_matrix(x)
    original_spectra = [sp.rfft(channel) for channel in x]
    original = statistic(original_spectra, bin_k)
    values = []
    for seed in seeds:
        signals, _ = generator(x, seed)
        spectra = [sp.rfft(s) for s in signals]
        values.append(statistic(spectra, bin_k))
    distinct = sorted(set(values))
    return {
        "statistic": getattr(statistic, "__name__", "statistic"),
        "bin": bin_k,
        "n_seeds": len(seeds),
        "original_value": original,
        "distinct_values": tuple(distinct),
        "varies_across_ensemble": len(distinct) > 1,
        "varies_from_original": any(v != original for v in values),
    }


VARIATION_TOL = 1e-9  # a circular spread below this is numerical zero, not variation


def _wrap(angle):
    return (angle + math.pi) % (2.0 * math.pi) - math.pi


def pairwise_relative_phases(spectra, k):
    """Relative phases ``arg(X_i[k] conj(X_j[k]))`` for every channel pair ``i < j`` at bin ``k``."""
    d = len(spectra)
    return {(i, j): cmath.phase(spectra[i][k] * spectra[j][k].conjugate())
            for i in range(d) for j in range(i + 1, d)}


def relative_phase_spread(x, generator, seeds, bin_k):
    """Does a procedure vary each channel pair's relative phase at ``bin_k`` across an ensemble?

    For each pair, the circular spread is ``1 - R``, where ``R`` is the mean resultant length of
    the surrogate relative phases. ``varies`` is True if any pair's spread exceeds
    ``VARIATION_TOL``. ``max_deviation_from_original`` is the largest wrapped deviation of any
    surrogate's relative phase from the original data's. A procedure that keeps every relative
    phase cannot test a statistic built from relative phases.
    """
    if isinstance(bin_k, bool) or not isinstance(bin_k, numbers.Integral):
        raise sp.SurrogateInputError("bin_k must be an integer")
    seeds = list(seeds)
    if not seeds:
        raise sp.SurrogateInputError("seeds must be non-empty")
    x = sp.as_float_matrix(x)
    original = pairwise_relative_phases([sp.rfft(c) for c in x], bin_k)
    angles = {pair: [] for pair in original}
    for seed in seeds:
        signals, _ = generator(x, seed)
        rel = pairwise_relative_phases([sp.rfft(s) for s in signals], bin_k)
        for pair in angles:
            angles[pair].append(rel[pair])
    pairs = {}
    for pair, values in angles.items():
        mean_cos = sum(math.cos(v) for v in values) / len(values)
        mean_sin = sum(math.sin(v) for v in values) / len(values)
        spread = 1.0 - math.hypot(mean_cos, mean_sin)
        deviation = max(abs(_wrap(v - original[pair])) for v in values)
        pairs[pair] = {"spread": spread, "max_deviation_from_original": deviation}
    max_spread = max((p["spread"] for p in pairs.values()), default=0.0)
    return {
        "bin": bin_k,
        "n_seeds": len(seeds),
        "pairs": pairs,
        "max_spread": max_spread,
        "varies": max_spread > VARIATION_TOL,
    }


def zero_or_pi_distance(signals, bins=None, rel_amplitude_floor=1e-10):
    """Largest distance, in radians, of any inter-channel relative phase from ``{0, pi}``.

    Zero means every checked relative phase is 0 or pi up to rounding. Bins where a channel's
    amplitude is below ``rel_amplitude_floor`` times the largest amplitude are skipped, because
    their phase is undefined. Returns ``0.0`` when no bin is checked.
    """
    signals = sp.as_float_matrix(signals)
    spectra = [sp.rfft(s) for s in signals]
    n = len(signals[0])
    if bins is None:
        bins = range(sp.n_freq(n))
    peak = max((abs(v) for row in spectra for v in row), default=0.0)
    floor = rel_amplitude_floor * peak
    worst = 0.0
    for k in bins:
        if any(abs(row[k]) <= floor for row in spectra):
            continue
        for theta in pairwise_relative_phases(spectra, k).values():
            worst = max(worst, min(abs(_wrap(theta)), abs(_wrap(theta - math.pi))))
    return worst
