"""Stdlib spectral primitives for the surrogate-null contract.

Synthetic arrays only. No NumPy, SciPy, subprocess, network, or dataset access.

Conventions (all explicit, all checkable):

- ``rfft`` is the unnormalised forward DFT of a real sequence of length ``n``,
  ``X[k] = sum_t x[t] * exp(-2*pi*i*k*t/n)``, for ``k = 0 .. n//2``. It is an
  O(n^2) reference implementation, intended for small synthetic inputs.
- ``irfft`` inverts it with the Hermitian extension implied by real data:
  ``x[t] = (1/n) * (Re X0 + [Re Xnyq*(-1)^t if n even] + 2*sum Re(X_k e^{2 pi i k t/n}))``.
  Taking real parts is what enforces Hermitian symmetry. The imaginary parts of
  the DC bin and, for even ``n``, the Nyquist bin are discarded and reported,
  because a real signal cannot carry them.
- Periodogram cross-spectrum: ``C[k][i][j] = X_i[k] * conj(X_j[k]) / n``.
  Its expectation under a stationary process is the cross-spectral density up
  to the normalisation; that is the only sense in which it estimates the CSD.
"""
from __future__ import annotations

import cmath
import math
import numbers
import random

EPS = 1e-12
_PSD_PIVOT_REL = 1e-12  # unregularised pivots below this (relative) count as singular


class SurrogateInputError(ValueError):
    """Input is not a finite, real, rectangular array of the expected shape."""


class NonPositiveDefiniteError(ValueError):
    """A covariance/CSD matrix is not positive definite and was not regularised."""


def check_seed(seed):
    if isinstance(seed, bool) or not isinstance(seed, numbers.Integral):
        raise SurrogateInputError(f"seed must be an integer, got {type(seed).__name__}")
    return int(seed)


def rng_for(seed, label):
    """Deterministic, independent stream per (seed, label).

    ``random.Random`` seeds strings with a version-2 algorithm that does not use
    hash randomisation, so the same seed and label give the same stream in every
    process. Labels separate channels, frequency bins, and null families.
    """
    return random.Random(f"{check_seed(seed)}|{label}")


def validate_signal(x):
    """Return ``(n_channels, n_time)`` for a rectangular array of finite reals.

    Rejects: empty input, non-sequence channels, ragged channels, bool and
    complex values, and non-finite values. Never coerces silently.
    """
    if isinstance(x, (str, bytes)) or not hasattr(x, "__len__") or len(x) == 0:
        raise SurrogateInputError("x must be a non-empty sequence of channels")
    lengths = set()
    for c, channel in enumerate(x):
        if isinstance(channel, (str, bytes)) or not hasattr(channel, "__len__"):
            raise SurrogateInputError(f"channel {c} must be a sequence of samples")
        lengths.add(len(channel))
        for t, value in enumerate(channel):
            if isinstance(value, bool) or not isinstance(value, numbers.Real):
                raise SurrogateInputError(
                    f"channel {c} sample {t} must be a real number, got {type(value).__name__}"
                )
            if not math.isfinite(value):
                raise SurrogateInputError(f"channel {c} sample {t} is not finite")
    if len(lengths) != 1:
        raise SurrogateInputError(f"channels have mismatched lengths {sorted(lengths)}")
    n_time = lengths.pop()
    if n_time == 0:
        raise SurrogateInputError("channels must contain at least one sample")
    return len(x), n_time


def as_float_matrix(x):
    """Validate, then return channels as lists of Python floats."""
    validate_signal(x)
    return [[float(value) for value in channel] for channel in x]


def n_freq(n_time):
    return n_time // 2 + 1


def randomized_bins(n_time):
    """Bins whose phase may be randomised: positive frequencies, excluding DC and Nyquist."""
    if n_time % 2 == 0:
        return list(range(1, n_time // 2))
    return list(range(1, (n_time - 1) // 2 + 1))


def fixed_bins(n_time):
    """Bins that must stay real: DC always, and Nyquist for even lengths."""
    bins = [0]
    if n_time % 2 == 0 and n_time >= 2:
        bins.append(n_time // 2)
    return bins


_TABLE_CACHE: dict[int, tuple[list[complex], list[complex]]] = {}


def _tables(n):
    if n not in _TABLE_CACHE:
        forward = [cmath.exp(-2j * math.pi * m / n) for m in range(n)]
        inverse = [cmath.exp(2j * math.pi * m / n) for m in range(n)]
        _TABLE_CACHE[n] = (forward, inverse)
    return _TABLE_CACHE[n]


def rfft(x):
    """Unnormalised forward DFT of a real sequence, bins ``0 .. n//2``."""
    n = len(x)
    forward, _ = _tables(n)
    out = []
    for k in range(n_freq(n)):
        acc = 0j
        for t in range(n):
            acc += x[t] * forward[(k * t) % n]
        out.append(acc)
    return out


def irfft(spectrum, n):
    """Inverse of ``rfft`` with Hermitian extension; returns ``(signal, discarded)``.

    ``discarded`` reports the magnitude of the imaginary parts of the DC bin and,
    for even ``n``, the Nyquist bin. Those parts cannot be represented by a real
    signal, so they are dropped and the drop is reported, not hidden.
    """
    if len(spectrum) != n_freq(n):
        raise SurrogateInputError(
            f"spectrum has {len(spectrum)} bins; a real signal of length {n} needs {n_freq(n)}"
        )
    _, inverse = _tables(n)
    nyquist = n // 2 if n % 2 == 0 and n >= 2 else None
    discarded = {
        "dc_imag": abs(spectrum[0].imag),
        "nyquist_imag": abs(spectrum[nyquist].imag) if nyquist is not None else 0.0,
    }
    signal = []
    for t in range(n):
        acc = spectrum[0].real
        for k in range(1, n_freq(n)):
            weight = 1.0 if k == nyquist else 2.0
            acc += weight * (spectrum[k] * inverse[(k * t) % n]).real
        signal.append(acc / n)
    return signal, discarded


def periodogram_csd(spectra, n):
    """Per-bin periodogram matrices ``X_i[k] conj(X_j[k]) / n`` for each bin ``k``."""
    n_channels = len(spectra)
    bins = n_freq(n)
    out = []
    for k in range(bins):
        matrix = [[spectra[i][k] * spectra[j][k].conjugate() / n for j in range(n_channels)]
                  for i in range(n_channels)]
        out.append(matrix)
    return out


def smooth_csd(raw, halfwidth):
    """Average each bin's matrix over neighbouring bins within ``halfwidth``.

    Edges are truncated, not reflected, and the average is normalised by the
    number of bins actually used. Each output is a convex combination of
    positive-semidefinite rank-one matrices, so it stays Hermitian PSD.
    """
    if isinstance(halfwidth, bool) or not isinstance(halfwidth, numbers.Integral) or halfwidth < 0:
        raise SurrogateInputError("smoothing_halfwidth must be a non-negative integer")
    bins = len(raw)
    d = len(raw[0])
    out = []
    for k in range(bins):
        lo, hi = max(0, k - halfwidth), min(bins, k + halfwidth + 1)
        count = hi - lo
        matrix = [[sum(raw[j][i][m] for j in range(lo, hi)) / count for m in range(d)]
                  for i in range(d)]
        out.append(matrix)
    return out


def is_hermitian(matrix, tol=1e-9):
    d = len(matrix)
    scale = max(1.0, max(abs(matrix[i][j]) for i in range(d) for j in range(d)))
    return all(abs(matrix[i][j] - matrix[j][i].conjugate()) <= tol * scale
               for i in range(d) for j in range(d))


def cholesky_hermitian(matrix):
    """Lower-triangular ``L`` with ``L L^H = matrix``.

    Raises ``NonPositiveDefiniteError`` if a pivot is not safely positive. The
    threshold is relative to the largest diagonal entry, so rounding noise on a
    rank-deficient matrix is treated as singular rather than as a valid factor.
    """
    d = len(matrix)
    max_diag = max(matrix[i][i].real for i in range(d))
    if not math.isfinite(max_diag):
        raise NonPositiveDefiniteError("matrix has a non-finite diagonal")
    tiny = max(max_diag, 0.0) * _PSD_PIVOT_REL
    factor = [[0j] * d for _ in range(d)]
    for j in range(d):
        pivot = matrix[j][j].real - sum((abs(factor[j][k]) ** 2 for k in range(j)), 0.0)
        if not math.isfinite(pivot) or pivot <= tiny or pivot <= 0.0:
            raise NonPositiveDefiniteError(
                f"pivot {j} = {pivot!r} is not positive relative to diagonal scale {max_diag!r}"
            )
        factor[j][j] = complex(math.sqrt(pivot), 0.0)
        for i in range(j + 1, d):
            acc = matrix[i][j] - sum((factor[i][k] * factor[j][k].conjugate() for k in range(j)), 0j)
            factor[i][j] = acc / factor[j][j]
    return factor


def mat_vec(factor, vector):
    d = len(factor)
    return [sum((factor[i][j] * vector[j] for j in range(d)), 0j) for i in range(d)]


def complex_standard_normal(rng, d):
    """``g`` with ``E[g g^H] = I``: real and imaginary parts each have variance 1/2."""
    scale = 1.0 / math.sqrt(2.0)
    return [complex(rng.gauss(0.0, 1.0) * scale, rng.gauss(0.0, 1.0) * scale) for _ in range(d)]


def real_standard_normal(rng, d):
    """``g`` with ``E[g g^T] = I`` for the real DC and Nyquist bins."""
    return [complex(rng.gauss(0.0, 1.0), 0.0) for _ in range(d)]


def complex_relative_error(actual, target):
    """Frobenius-style relative error ``||actual - target|| / (||target|| + EPS)``."""
    num = 0.0
    den = 0.0
    for a_row, t_row in zip(actual, target):
        for a, t in zip(a_row, t_row):
            num += abs(a - t) ** 2
            den += abs(t) ** 2
    return math.sqrt(num) / (math.sqrt(den) + EPS)


def power_relative_error(spectrum_a, spectrum_b):
    """Relative error of the power spectra ``|A|^2`` against ``|B|^2``."""
    num = 0.0
    den = 0.0
    for a, b in zip(spectrum_a, spectrum_b):
        pa, pb = abs(a) ** 2, abs(b) ** 2
        num += (pa - pb) ** 2
        den += pb ** 2
    return math.sqrt(num) / (math.sqrt(den) + EPS)
