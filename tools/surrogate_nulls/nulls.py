"""Surrogate nulls for synthetic multichannel real signals (HOLD / SYNTHETIC_ONLY).

Each null is defined by a stable identifier, a generative rule, the quantities it
preserves, the quantities it randomises, and an intended use (``CONTRACTS``).
Every generator returns ``(surrogate, SurrogateReport)``. The report states what
was preserved by construction and what was only measured, so a reader cannot
mistake a measured number for a guarantee.

A null that preserves a chosen statistic is not thereby a valid null for any
scientific question. The assumptions of each null are listed in ``CONTRACTS``
and in ``docs/surrogate_nulls/null_contract.md``.
"""
from __future__ import annotations

import cmath
import math
from dataclasses import asdict, dataclass, field

from . import csd as csdlib
from . import spectral as sp

# Declared tolerances. They are fixed here, not tuned to pass a result.
AUTO_SPECTRUM_TOL = 1e-2          # relative power error per channel (IAAFT auto-spectrum status)
CROSS_SPECTRUM_STRICT_TOL = 1e-3  # strict relative cross-spectral error (same bar as the #398 contract)
MARGINAL_EXACT_TOL = 1e-12        # absolute tolerance for "exact" sorted-value agreement

NULL_IDS = (
    "common_phase_prichard_theiler",
    "independent_phase_univariate_ft",
    "cholesky_gaussian_cross_spectral",
    "mv_iaaft_rank_adjusted",
)

# Exploratory, assumption-dependent nulls. Kept out of NULL_IDS on purpose.
EXPLORATORY_NULL_IDS = ("zero_lag_real_part_gaussian",)

# Reported with every estimated-CSD null. It states what was checked and never claims full rank:
# the factorization returning a factor does not show that the covariance has full numerical rank.
RANK_STATUS = "EFFECTIVE_RANK_REPORTED_PER_BIN_NOT_ASSUMED_FULL"

CONTRACTS = {
    "common_phase_prichard_theiler": {
        "generative_rule": (
            "rFFT each channel; draw ONE uniform phase per randomized positive bin, shared by all "
            "channels; multiply that bin of every channel by exp(i*phase); inverse rFFT."
        ),
        "preserved": "every channel's power spectrum; the complex cross-spectrum at every bin, "
                     "including same-frequency inter-channel phase differences",
        "randomized": "the absolute phase of each randomized bin, identically across channels",
        "role": "CONTROL_DIAGNOSTIC_ONLY: not a winding null and not a Gaussian surrogate",
        "intended_use": "a control that keeps all second-order complex structure, including every "
                        "same-frequency relative phase; use it to check that a statistic is blind to a "
                        "common phase shift. NOT a null for narrowband spatial winding.",
        "invalid_for": "narrowband spatial winding: the winding depends on phase differences, "
                       "which this null preserves exactly, so a winding statistic cannot exceed it",
        "assumptions": "stationary record; second-order structure is the object of the test",
    },
    "independent_phase_univariate_ft": {
        "generative_rule": (
            "rFFT each channel; draw an INDEPENDENT uniform phase per channel and randomized bin; "
            "multiply; inverse rFFT. Univariate FT surrogate applied channel by channel."
        ),
        "preserved": "each channel's power spectrum (exactly, per bin)",
        "randomized": "all cross-channel phase relations, hence the cross-spectrum in expectation",
        "intended_use": "tests against a null that destroys cross-channel coupling; a DIFFERENT "
                        "and potentially TOO-WEAK null",
        "invalid_for": "claims about volume conduction or common-source structure: it destroys "
                       "zero-lag coupling a volume-conduction-preserving null would keep",
        "assumptions": "stationary record; linear structure is the object of the test",
    },
    "cholesky_gaussian_cross_spectral": {
        "generative_rule": (
            "Estimate the CSD as a frequency-smoothed periodogram (bins within a halfwidth, edges "
            "truncated and normalised). Per randomized bin, draw X = sqrt(n) * L g with L the "
            "Cholesky factor of the smoothed CSD and g complex standard normal (E[g g^H] = I). "
            "DC and Nyquist use real factors and real normals. Inverse rFFT."
        ),
        "preserved": "the smoothed CSD IN EXPECTATION over the ensemble (E[X X^H]/n = target). "
                     "A single realisation does NOT preserve it exactly.",
        "randomized": "every randomized bin, independently per bin (own seeded stream); "
                      "DC and Nyquist are real-valued draws",
        "intended_use": "a second-order Gaussian null for the smoothed cross-spectrum under "
                        "stationarity and a linear-Gaussian model",
        "invalid_for": "non-Gaussian, non-stationary, or nonlinear structure; it is not a universal "
                       "null and must not be promoted to one",
        "assumptions": "stationarity over the record; linear-Gaussian second-order model; the "
                       "smoothing halfwidth sets the spectral resolution of the target",
    },
    "mv_iaaft_rank_adjusted": {
        "generative_rule": (
            "Start from a seeded random permutation of each channel. Iterate: rFFT; set each bin's "
            "magnitude to that channel's original magnitude and keep the current phase (DC and Nyquist "
            "real); inverse rFFT; then rank-adjust by assigning each channel's original sorted values "
            "in the order of the spectrally constrained signal. Stop when the rank order is stable."
        ),
        "preserved": "EXACTLY, after the final rank adjustment: each channel's sorted values "
                     "(the marginal distribution). Auto-spectra are approximate. Cross-spectra are "
                     "NOT targeted and are reported, not guaranteed.",
        "randomized": "the initial permutation and the iterative phase dynamics",
        "intended_use": "a marginal-preserving null with approximately preserved auto-spectra",
        "invalid_for": "any claim requiring an exact post-rank cross-spectrum; IAAFT quantile "
                       "restoration generally breaks that, so the strict gate is reported UNMET "
                       "when it is missed",
        "assumptions": "stationary record; the iteration may not converge (reported)",
    },
    "zero_lag_real_part_gaussian": {
        "generative_rule": (
            "Estimate the cross-spectral matrix per bin (estimator named in the report, or a "
            "supplied estimate). Keep only its real part Re C(f), which is real symmetric PSD. "
            "Draw REAL Gaussian Fourier coefficients with covariance Re C(f) at every bin, "
            "including the randomized bins. Inverse rFFT."
        ),
        "preserved": "the real part Re C(f) of the estimated cross-spectrum, IN EXPECTATION over seeds. "
                     "This is an ensemble zero-lag / real-covariance null. Its definition constrains only "
                     "the ensemble real covariance. It does not define a per-realisation phase constraint, "
                     "and the estimate's imaginary part is discarded.",
        "randomized": "the real Gaussian Fourier coefficients at every bin. This generator draws real "
                      "coefficients, so its draws show 0-or-pi relative phases; that is an observed "
                      "implementation property, not part of the null's definition",
        "intended_use": "EXPLORATORY and assumption-dependent: a probe of zero-lag in-phase "
                        "structure under a stationary linear-Gaussian model",
        "invalid_for": "any claim about volume conduction, source geometry, filtering, or lagged "
                       "coupling. Those are not modelled, and a non-zero-lag effect cannot be "
                       "distinguished from one this null removes.",
        "assumptions": "stationarity; zero-lag (real) second-order structure is the only structure "
                       "of interest; the imaginary part of the CSD carries no information here. A "
                       "surrogate's 0-or-pi relative phases are a property of the surrogate, not "
                       "evidence about the recording; the null is not a volume-conduction detector.",
    },
}


@dataclass(frozen=True)
class SurrogateReport:
    null_id: str
    seed: int
    n_channels: int
    n_time: int
    randomized_bins: tuple
    fixed_bins: tuple
    status: dict
    marginal_max_abs_error: float
    auto_spectrum_rel_error: tuple
    cross_spectrum_rel_error: float | None
    pre_rank_auto_spectrum_rel_error: tuple | None = None
    pre_rank_cross_spectrum_rel_error: float | None = None
    iterations: int | None = None
    converged: bool | None = None
    ridge_rel: float | None = None
    rank_deficient_bins: tuple = ()
    ridge_applied_bins: tuple = ()
    zero_power_bins: tuple = ()
    dc_imag_discarded: float = 0.0
    nyquist_imag_discarded: float = 0.0
    tolerances: dict = field(default_factory=dict)
    denominator_eps: float = sp.EPS
    notes: tuple = ()
    estimator: str | None = None
    estimator_source: str | None = None
    n_tapers: int | None = None
    smoothing_halfwidth: int | None = None
    shrinkage: float | None = None
    effective_rank_per_bin: tuple | None = None
    min_eig_rel_per_bin: tuple | None = None
    condition_per_bin: tuple | None = None
    participation_ratio_per_bin: tuple | None = None
    min_eig_abs_per_bin: tuple | None = None
    estimator_dof_per_bin: tuple | None = None
    rank_status: str | None = None
    max_relative_phase_distance_from_zero_or_pi: float | None = None

    def to_dict(self):
        return asdict(self)


# --------------------------------------------------------------------------- helpers

def _to_signals(spectra, n):
    """Inverse-transform every channel; return signals and the largest discarded imaginary parts."""
    signals = []
    dc = 0.0
    nyq = 0.0
    for spectrum in spectra:
        signal, discarded = sp.irfft(spectrum, n)
        signals.append(signal)
        dc = max(dc, discarded["dc_imag"])
        nyq = max(nyq, discarded["nyquist_imag"])
    return signals, dc, nyq


def _marginal_error(surrogate, original):
    worst = 0.0
    for s_row, o_row in zip(surrogate, original):
        s_sorted = sorted(s_row)
        o_sorted = sorted(o_row)
        for a, b in zip(s_sorted, o_sorted):
            worst = max(worst, abs(a - b))
    return worst


def _auto_power_errors(spectra_a, spectra_b):
    return tuple(sp.power_relative_error(a, b) for a, b in zip(spectra_a, spectra_b))


def _csd_rel_error(csd_actual, csd_target):
    """Return the scale-invariant Frobenius relative error summed over bins.

    A zero target has zero error only when the actual CSD is also zero; otherwise
    its relative error is infinite. Any non-finite input likewise returns
    infinity so a strict tolerance check fails closed. Components are scaled
    before subtraction and accumulated with ``hypot`` to avoid squared-norm
    overflow and underflow across the finite float64 range.
    """
    def entries():
        for a_mat, t_mat in zip(csd_actual, csd_target):
            d = len(t_mat)
            for i in range(d):
                for j in range(d):
                    yield complex(a_mat[i][j]), complex(t_mat[i][j])

    scale = 0.0
    for actual, target in entries():
        components = (actual.real, actual.imag, target.real, target.imag)
        if not all(math.isfinite(value) for value in components):
            return math.inf
        scale = max(scale, *(abs(value) for value in components))

    if scale == 0.0:
        return 0.0

    numerator = 0.0
    denominator = 0.0
    for actual, target in entries():
        numerator = math.hypot(
            numerator,
            actual.real / scale - target.real / scale,
            actual.imag / scale - target.imag / scale,
        )
        denominator = math.hypot(denominator, target.real / scale, target.imag / scale)

    if denominator == 0.0:
        return math.inf if numerator != 0.0 else 0.0
    return numerator / denominator


def _target_for_compare(csd, n):
    """Target matrices for comparison: DC and Nyquist use their real parts (the real-bin contract)."""
    fixed = set(sp.fixed_bins(n))
    out = []
    for k, mat in enumerate(csd):
        if k in fixed:
            out.append([[complex(mat[i][j].real, 0.0) for j in range(len(mat))] for i in range(len(mat))])
        else:
            out.append(mat)
    return out


def _power_error_to_target(spectra, target_csd, n):
    """Per-channel relative error of the measured periodogram auto-spectrum against the target diagonal."""
    errors = []
    d = len(spectra)
    for c in range(d):
        num = 0.0
        den = 0.0
        for k in range(sp.n_freq(n)):
            measured = abs(spectra[c][k]) ** 2 / n
            target = target_csd[k][c][c].real
            num += (measured - target) ** 2
            den += target ** 2
        errors.append(math.sqrt(num) / (math.sqrt(den) + sp.EPS))
    return tuple(errors)


def _make_report(*, null_id, seed, n_channels, n_time, status, marginal, auto, cross,
                 dc_imag, nyq_imag, notes, **extra):
    return SurrogateReport(
        null_id=null_id,
        seed=seed,
        n_channels=n_channels,
        n_time=n_time,
        randomized_bins=tuple(sp.randomized_bins(n_time)),
        fixed_bins=tuple(sp.fixed_bins(n_time)),
        status=status,
        marginal_max_abs_error=marginal,
        auto_spectrum_rel_error=auto,
        cross_spectrum_rel_error=cross,
        dc_imag_discarded=dc_imag,
        nyquist_imag_discarded=nyq_imag,
        tolerances={
            "auto_spectrum_rel": AUTO_SPECTRUM_TOL,
            "cross_spectrum_strict_rel": CROSS_SPECTRUM_STRICT_TOL,
            "marginal_exact_abs": MARGINAL_EXACT_TOL,
        },
        notes=tuple(notes),
        **extra,
    )


def _cross_spectrum_error_or_none(spectra, reference, n, n_channels):
    if n_channels < 2:
        return None
    return _csd_rel_error(sp.periodogram_csd(spectra, n), sp.periodogram_csd(reference, n))


# --------------------------------------------------------------------- null 1: common phase

def common_phase_prichard_theiler(x, seed):
    """Shared phase rotation across channels (Prichard-Theiler style).

    Preserves every channel's power and the complex cross-spectrum exactly, so it
    preserves same-frequency inter-channel phase differences. It is therefore not
    a valid null for narrowband spatial winding.
    """
    seed = sp.check_seed(seed)
    data = sp.as_float_matrix(x)
    n_ch, n = len(data), len(data[0])
    spectra = [sp.rfft(channel) for channel in data]
    phases = {}
    for k in sp.randomized_bins(n):
        u = sp.rng_for(seed, f"common_phase|bin:{k}").random()
        phases[k] = cmath.exp(2j * math.pi * u)
    for k, phase in phases.items():
        for c in range(n_ch):
            spectra[c][k] *= phase
    signals, dc, nyq = _to_signals(spectra, n)
    measured = [sp.rfft(s) for s in signals]
    original = [sp.rfft(ch) for ch in data]
    report = _make_report(
        null_id="common_phase_prichard_theiler",
        seed=seed,
        n_channels=n_ch,
        n_time=n,
        status={
            "marginal": "NOT_PRESERVED_MEASURED",
            "auto_spectrum": "PRESERVED_EXACT_BY_CONSTRUCTION",
            "cross_spectrum": "PRESERVED_EXACT_BY_CONSTRUCTION",
            "same_frequency_relative_phase": "PRESERVED_EXACT_BY_CONSTRUCTION",
            "role": "CONTROL_DIAGNOSTIC_ONLY",
            "intended_use": "INVALID_FOR_NARROWBAND_SPATIAL_WINDING_NULL",
        },
        marginal=_marginal_error(signals, data),
        auto=_auto_power_errors(measured, original),
        cross=_cross_spectrum_error_or_none(measured, original, n, n_ch),
        dc_imag=dc,
        nyq_imag=nyq,
        notes=[
            "phase is shared across channels: relative phases are the invariant",
            "power and complex cross-spectrum are exact per bin by construction",
        ],
    )
    return signals, report


# ------------------------------------------------------- null 2: independent phase FT

def independent_phase_univariate_ft(x, seed):
    """Channel-wise independent phase randomisation (univariate FT surrogate).

    Preserves each channel's power spectrum but randomises all cross-channel
    phase relations. It tests a different and potentially too-weak null, and it
    must not be presented as volume-conduction-preserving.
    """
    seed = sp.check_seed(seed)
    data = sp.as_float_matrix(x)
    n_ch, n = len(data), len(data[0])
    spectra = [sp.rfft(channel) for channel in data]
    for c in range(n_ch):
        for k in sp.randomized_bins(n):
            u = sp.rng_for(seed, f"independent_phase|ch:{c}|bin:{k}").random()
            spectra[c][k] *= cmath.exp(2j * math.pi * u)
    signals, dc, nyq = _to_signals(spectra, n)
    measured = [sp.rfft(s) for s in signals]
    original = [sp.rfft(ch) for ch in data]
    report = _make_report(
        null_id="independent_phase_univariate_ft",
        seed=seed,
        n_channels=n_ch,
        n_time=n,
        status={
            "marginal": "NOT_PRESERVED_MEASURED",
            "auto_spectrum": "PRESERVED_EXACT_BY_CONSTRUCTION",
            "cross_spectrum": "NOT_PRESERVED_RANDOMISED_IN_EXPECTATION",
            "intended_use": "DIFFERENT_AND_POSSIBLY_TOO_WEAK_NULL",
        },
        marginal=_marginal_error(signals, data),
        auto=_auto_power_errors(measured, original),
        cross=_cross_spectrum_error_or_none(measured, original, n, n_ch),
        dc_imag=dc,
        nyq_imag=nyq,
        notes=[
            "cross-channel phase relations are independent across channels",
            "not a volume-conduction-preserving null",
        ],
    )
    return signals, report


# ------------------------------------------------- null 3: Cholesky Gaussian CSD

def draw_from_csd(csd_by_bin, n_time, seed, ridge_rel=1e-8, *, real_coefficients=False,
                  rank_tol=csdlib.DEFAULT_RANK_TOL, psd_tol=csdlib.DEFAULT_PSD_TOL):
    """Draw surrogate spectra with ``E[X X^H / n] = csd_by_bin[k]`` at each bin.

    ``csd_by_bin`` has one Hermitian matrix per rFFT bin ``0 .. n//2``.

    Failure behaviour (fails closed):
    - non-square, mismatched, non-finite, or non-Hermitian matrices raise
      ``SurrogateInputError``;
    - a matrix whose trace is not positive while its entries are nonzero raises
      ``NonPositiveDefiniteError``. An all-zero matrix is accepted and gives zero power;
    - a matrix whose Cholesky fails only by rounding (rank deficiency) is ridge
      regularised by ``ridge_rel * trace / d`` and the bin is reported. If ``ridge_rel``
      is zero, the failure is raised instead;
    - a genuinely indefinite matrix still fails after regularisation and raises.
    - a matrix whose smallest eigenvalue is below ``-psd_tol * scale`` is materially
      indefinite and raises before any regularisation (``matrix_diagnostics``), where
      ``scale = max(trace, largest entry)``.

    ``real_coefficients=True`` draws real Gaussian coefficients at every bin (the zero-lag
    null). The target must then be real-valued, and an imaginary part above rounding raises.

    Returns ``(spectra, info)`` where ``spectra[c][k]`` is the surrogate coefficient and
    ``info`` lists rank-deficient, ridge-applied, and zero-power bins, plus per-bin
    ``effective_rank``, ``min_eig_rel`` and ``condition`` diagnostics.
    """
    seed = sp.check_seed(seed)
    if isinstance(n_time, bool) or not isinstance(n_time, int) or n_time < 1:
        raise sp.SurrogateInputError("n_time must be a positive integer")
    if isinstance(ridge_rel, bool) or not isinstance(ridge_rel, (int, float)) or not math.isfinite(ridge_rel) or ridge_rel < 0:
        raise sp.SurrogateInputError("ridge_rel must be a finite non-negative number")
    nf = sp.n_freq(n_time)
    if len(csd_by_bin) != nf:
        raise sp.SurrogateInputError(f"csd_by_bin has {len(csd_by_bin)} bins; n_time={n_time} needs {nf}")
    d = len(csd_by_bin[0])
    if d < 1:
        raise sp.SurrogateInputError("CSD matrices must be at least 1x1")
    for k, mat in enumerate(csd_by_bin):
        if len(mat) != d or any(len(row) != d for row in mat):
            raise sp.SurrogateInputError(f"dimensional mismatch at bin {k}: expected {d}x{d}")
        try:
            csdlib._validate_hermitian_matrix(mat)
        except sp.SurrogateInputError as exc:
            raise sp.SurrogateInputError(f"bin {k}: {exc}") from exc

    fixed = set(sp.fixed_bins(n_time))
    spectra = [[0j] * nf for _ in range(d)]
    info = {"rank_deficient": [], "ridge_applied": [], "zero_power": [],
            "dc_imag": 0.0, "nyquist_imag": 0.0,
            "effective_rank": [], "min_eig_rel": [], "min_eig_abs": [], "condition": [],
            "participation_ratio": []}
    scale = math.sqrt(n_time)

    for k in range(nf):
        mat = csd_by_bin[k]
        is_fixed = k in fixed
        if is_fixed:
            imag_mag = max(abs(mat[i][j].imag) for i in range(d) for j in range(d))
            if k == 0:
                info["dc_imag"] = max(info["dc_imag"], imag_mag)
            else:
                info["nyquist_imag"] = max(info["nyquist_imag"], imag_mag)
            mat = [[complex(mat[i][j].real, 0.0) for j in range(d)] for i in range(d)]

        trace = sum(mat[i][i].real for i in range(d))
        bin_scale = max(abs(mat[i][j]) for i in range(d) for j in range(d))
        if real_coefficients and any(abs(mat[i][j].imag) > 1e-12 * bin_scale
                                     for i in range(d) for j in range(d)):
            raise sp.SurrogateInputError(f"bin {k}: real_coefficients=True requires a real-valued target")
        rank, min_rel, cond, part = csdlib._diagnose_validated(mat, rank_tol=rank_tol, psd_tol=psd_tol)
        info["effective_rank"].append(rank)
        info["min_eig_rel"].append(min_rel)
        info["condition"].append(cond)
        info["participation_ratio"].append(part)
        info["min_eig_abs"].append(min_rel * abs(trace))
        if trace == 0.0:  # all entries are zero here: nonzero entries with trace 0 were rejected above
            info["zero_power"].append(k)
            continue

        try:
            factor = sp.cholesky_hermitian(mat)
        except sp.NonPositiveDefiniteError:
            if ridge_rel <= 0.0:
                raise
            info["rank_deficient"].append(k)
            ridge = ridge_rel * trace / d
            regularised = [[mat[i][j] + (ridge if i == j else 0.0) for j in range(d)] for i in range(d)]
            factor = sp.cholesky_hermitian(regularised)
            info["ridge_applied"].append(k)

        rng = sp.rng_for(seed, f"cholesky|bin:{k}")
        g = sp.real_standard_normal(rng, d) if (is_fixed or real_coefficients) else sp.complex_standard_normal(rng, d)
        z = sp.mat_vec(factor, g)
        for c in range(d):
            spectra[c][k] = scale * z[c]
    return spectra, info


def cholesky_gaussian_cross_spectral(x, seed, smoothing_halfwidth=1, ridge_rel=1e-8):
    """Gaussian surrogate whose smoothed CSD is preserved IN EXPECTATION.

    The smoothed CSD is the target. Each single realisation deviates from it;
    the report labels both auto- and cross-spectral comparisons as
    single-realisation deviations, never as exact.
    """
    seed = sp.check_seed(seed)
    data = sp.as_float_matrix(x)
    n_ch, n = len(data), len(data[0])
    spectra = [sp.rfft(channel) for channel in data]
    raw = sp.periodogram_csd(spectra, n)
    target = sp.smooth_csd(raw, smoothing_halfwidth)
    out_spectra, info = draw_from_csd(target, n, seed, ridge_rel=ridge_rel)
    signals, dc, nyq = _to_signals(out_spectra, n)
    measured = [sp.rfft(s) for s in signals]
    compare_target = _target_for_compare(target, n)
    report = _make_report(
        null_id="cholesky_gaussian_cross_spectral",
        seed=seed,
        n_channels=n_ch,
        n_time=n,
        status={
            "marginal": "NOT_PRESERVED_MEASURED",
            "auto_spectrum": "EXPECTATION_ONLY_SINGLE_REALISATION_NOT_EXACT",
            "cross_spectrum": "EXPECTATION_ONLY_SINGLE_REALISATION_NOT_EXACT",
            "estimator_validity": (
                "SMOOTHED_PERIODOGRAM_RANK_UP_TO_2H_PLUS_1_REPORTED_PER_BIN"
                if smoothing_halfwidth >= 1
                else "DIAGNOSTIC_RANK_ONE_NOT_A_PHASE_RANDOMISING_NULL"
            ),
            "intended_use": "SECOND_ORDER_GAUSSIAN_NULL_UNDER_STATIONARITY_AND_LINEAR_GAUSSIAN_MODEL",
        },
        marginal=_marginal_error(signals, data),
        auto=_power_error_to_target(measured, compare_target, n),
        cross=_csd_rel_error(sp.periodogram_csd(measured, n), compare_target) if n_ch >= 2 else None,
        dc_imag=dc,
        nyq_imag=nyq,
        ridge_rel=ridge_rel,
        rank_deficient_bins=tuple(info["rank_deficient"]),
        ridge_applied_bins=tuple(info["ridge_applied"]),
        zero_power_bins=tuple(info["zero_power"]),
        notes=[
            f"target is the frequency-smoothed periodogram (halfwidth={smoothing_halfwidth})",
            "E[X X^H]/n equals the smoothed target; one realisation is not exact",
            "DC and Nyquist use real factors and real normals",
            "assumptions: stationarity, linear-Gaussian second-order model, not universal",
        ],
    )
    return signals, report


def _estimate_for_null(data, *, estimator, n_tapers, smoothing_halfwidth, shrinkage, spectral_estimate):
    """Return ``(csd_by_bin, info)`` from the named estimator, or from an explicit supplied estimate."""
    if spectral_estimate is not None:
        target = csdlib.validate_supplied_csd(spectral_estimate, len(data), len(data[0]))
        info = {"estimator": "supplied", "n_tapers": None, "smoothing_halfwidth": None,
                "shrinkage": None, "source": "explicitly_supplied"}
        return target, info
    return csdlib.estimate_csd(data, estimator, n_tapers=n_tapers,
                               smoothing_halfwidth=smoothing_halfwidth, shrinkage=shrinkage)


def _estimator_validity(est, n_channels):
    """What the chosen spectral estimate can and cannot support, stated in every report.

    A single unsmoothed periodogram is rank one for more than one channel, so it is a diagnostic
    and is never presented as phase-randomising. The labels describe the estimate; they do not
    change how the draw is made.
    """
    if est["source"] == "explicitly_supplied":
        return "SUPPLIED_NOT_VALIDATED_AGAINST_DATA"
    if est["estimator"] == "single_periodogram" or (
        est["estimator"] == "periodogram_boxcar" and est["smoothing_halfwidth"] == 0
    ):
        return "DIAGNOSTIC_RANK_ONE_NOT_A_PHASE_RANDOMISING_NULL"
    if est["estimator"] == "multitaper":
        if est["n_tapers"] >= n_channels + 1:
            return "MULTIWINDOW_ESTIMATE_WITH_RANK_HEADROOM_REPORTED_PER_BIN"
        return "MULTIWINDOW_ESTIMATE_LOW_RANK_REPORTED_PER_BIN"
    return "SMOOTHED_PERIODOGRAM_RANK_UP_TO_2H_PLUS_1_REPORTED_PER_BIN"


def cholesky_gaussian_csd(x, seed, *, estimator="multitaper", n_tapers=None, smoothing_halfwidth=1,
                          shrinkage=0.0, spectral_estimate=None, ridge_rel=1e-8,
                          rank_tol=csdlib.DEFAULT_RANK_TOL, psd_tol=csdlib.DEFAULT_PSD_TOL):
    """Gaussian surrogate whose ``E[X X^H / n]`` equals an explicit spectral estimate.

    The estimate is computed from ``x`` by ``estimator`` (``multitaper``,
    ``periodogram_boxcar``, or ``single_periodogram``), or supplied as ``spectral_estimate``
    (one Hermitian matrix per rFFT bin). A supplied estimate is validated for shape and
    Hermitian symmetry but is not checked against ``x``. The surrogate preserves the estimate
    IN EXPECTATION over seeds. A single surrogate deviates from it, and the report says so.
    """
    seed = sp.check_seed(seed)
    data = sp.as_float_matrix(x)
    n_ch, n = len(data), len(data[0])
    target, est = _estimate_for_null(data, estimator=estimator, n_tapers=n_tapers,
                                     smoothing_halfwidth=smoothing_halfwidth, shrinkage=shrinkage,
                                     spectral_estimate=spectral_estimate)
    out_spectra, info = draw_from_csd(target, n, seed, ridge_rel=ridge_rel,
                                      rank_tol=rank_tol, psd_tol=psd_tol)
    signals, dc, nyq = _to_signals(out_spectra, n)
    measured = [sp.rfft(s) for s in signals]
    compare_target = _target_for_compare(target, n)
    report = _make_report(
        null_id="cholesky_gaussian_csd",
        seed=seed,
        n_channels=n_ch,
        n_time=n,
        status={
            "marginal": "NOT_PRESERVED_MEASURED",
            "auto_spectrum": "EXPECTATION_ONLY_SINGLE_REALISATION_NOT_EXACT",
            "cross_spectrum": "EXPECTATION_ONLY_SINGLE_REALISATION_NOT_EXACT",
            "spectral_estimate_source": est["source"].upper(),
            "rank": RANK_STATUS,
            "estimator_validity": _estimator_validity(est, n_ch),
            "intended_use": "SECOND_ORDER_GAUSSIAN_NULL_UNDER_STATIONARITY_AND_LINEAR_GAUSSIAN_MODEL",
        },
        marginal=_marginal_error(signals, data),
        auto=_power_error_to_target(measured, compare_target, n),
        cross=_csd_rel_error(sp.periodogram_csd(measured, n), compare_target) if n_ch >= 2 else None,
        dc_imag=dc,
        nyq_imag=nyq,
        ridge_rel=ridge_rel,
        rank_deficient_bins=tuple(info["rank_deficient"]),
        ridge_applied_bins=tuple(info["ridge_applied"]),
        zero_power_bins=tuple(info["zero_power"]),
        estimator=est["estimator"],
        estimator_source=est["source"],
        n_tapers=est["n_tapers"],
        smoothing_halfwidth=est["smoothing_halfwidth"],
        shrinkage=est["shrinkage"],
        effective_rank_per_bin=tuple(info["effective_rank"]),
        min_eig_rel_per_bin=tuple(info["min_eig_rel"]),
        condition_per_bin=tuple(info["condition"]),
        participation_ratio_per_bin=tuple(info["participation_ratio"]),
        min_eig_abs_per_bin=tuple(info["min_eig_abs"]),
        estimator_dof_per_bin=est.get("dof_per_bin"),
        rank_status=RANK_STATUS,
        max_relative_phase_distance_from_zero_or_pi=csdlib.zero_or_pi_distance(signals),
        notes=[
            f"spectral estimate: {est['estimator']} ({est['source']})",
            "E[X X^H]/n equals the estimate in expectation; one realisation is not exact",
            "effective rank and conditioning are reported per bin; ridge only at rounding level",
            "a supplied estimate is not checked against the data",
            "DC and Nyquist use real factors and real normals",
            "assumptions: stationarity, linear-Gaussian second-order model, not universal",
        ],
    )
    return signals, report


def zero_lag_real_part_gaussian(x, seed, *, estimator="multitaper", n_tapers=None, smoothing_halfwidth=1,
                                shrinkage=0.0, spectral_estimate=None, ridge_rel=1e-8,
                                rank_tol=csdlib.DEFAULT_RANK_TOL, psd_tol=csdlib.DEFAULT_PSD_TOL):
    """EXPLORATORY, assumption-dependent null: real Gaussian coefficients with covariance Re C(f).

    Keeps only the real part of the estimated cross-spectrum and draws real Fourier
    coefficients. The target is an ensemble zero-lag / real-covariance null: it constrains
    E[X X^T] in expectation over seeds. It does not constrain each realisation's phases.
    Because this generator draws real coefficients, its realisations have zero imaginary
    parts, so their relative phases are 0 or pi. That is an observed implementation property
    (reported in the status), not part of the null definition. The null does not model volume
    conduction, source geometry, filtering, or lagged coupling, and must not be used to claim
    that any of those is controlled.
    """
    seed = sp.check_seed(seed)
    data = sp.as_float_matrix(x)
    n_ch, n = len(data), len(data[0])
    target, est = _estimate_for_null(data, estimator=estimator, n_tapers=n_tapers,
                                     smoothing_halfwidth=smoothing_halfwidth, shrinkage=shrinkage,
                                     spectral_estimate=spectral_estimate)
    real_target = [[[complex(mat[i][j].real, 0.0) for j in range(n_ch)] for i in range(n_ch)]
                   for mat in target]
    out_spectra, info = draw_from_csd(real_target, n, seed, ridge_rel=ridge_rel, real_coefficients=True,
                                      rank_tol=rank_tol, psd_tol=psd_tol)
    signals, dc, nyq = _to_signals(out_spectra, n)
    measured = [sp.rfft(s) for s in signals]
    compare_target = _target_for_compare(real_target, n)
    report = _make_report(
        null_id="zero_lag_real_part_gaussian",
        seed=seed,
        n_channels=n_ch,
        n_time=n,
        status={
            "marginal": "NOT_PRESERVED_MEASURED",
            "auto_spectrum": "EXPECTATION_ONLY_SINGLE_REALISATION_NOT_EXACT",
            "cross_spectrum_real_part": "EXPECTATION_ONLY_SINGLE_REALISATION_NOT_EXACT",
            "imaginary_part": "SET_TO_ZERO_BY_CONSTRUCTION",
            "generator_relative_phase_observed": (
                "REAL_COEFFICIENT_DRAWS_MEASURED_0_OR_PI_IMPLEMENTATION_DIAGNOSTIC_NOT_PART_OF_NULL_DEFINITION"
            ),
            "spectral_estimate_source": est["source"].upper(),
            "rank": RANK_STATUS,
            "estimator_validity": _estimator_validity(est, n_ch),
            "intended_use": "EXPLORATORY_ASSUMPTION_DEPENDENT_ZERO_LAG_REAL_PART_NULL",
            "volume_conduction": "NOT_MODELLED",
        },
        marginal=_marginal_error(signals, data),
        auto=_power_error_to_target(measured, compare_target, n),
        cross=_csd_rel_error(sp.periodogram_csd(measured, n), compare_target) if n_ch >= 2 else None,
        dc_imag=dc,
        nyq_imag=nyq,
        ridge_rel=ridge_rel,
        rank_deficient_bins=tuple(info["rank_deficient"]),
        ridge_applied_bins=tuple(info["ridge_applied"]),
        zero_power_bins=tuple(info["zero_power"]),
        estimator=est["estimator"],
        estimator_source=est["source"],
        n_tapers=est["n_tapers"],
        smoothing_halfwidth=est["smoothing_halfwidth"],
        shrinkage=est["shrinkage"],
        effective_rank_per_bin=tuple(info["effective_rank"]),
        min_eig_rel_per_bin=tuple(info["min_eig_rel"]),
        condition_per_bin=tuple(info["condition"]),
        participation_ratio_per_bin=tuple(info["participation_ratio"]),
        min_eig_abs_per_bin=tuple(info["min_eig_abs"]),
        estimator_dof_per_bin=est.get("dof_per_bin"),
        rank_status=RANK_STATUS,
        max_relative_phase_distance_from_zero_or_pi=csdlib.zero_or_pi_distance(signals),
        notes=[
            f"real part of the {est['estimator']} estimate ({est['source']}); imaginary parts are zero",
            "EXPLORATORY and assumption-dependent: not a volume-conduction, geometry, or filter model",
            "generator draws real coefficients: measured relative phases are 0 or pi (observed "
            "diagnostic; not part of the ensemble null definition)",
        ],
    )
    return signals, report


# -------------------------------------------------------- null 4: MV-IAAFT, rank-adjusted

def mv_iaaft_rank_adjusted(x, seed, max_iter=100):
    """Iterative amplitude-adjusted FT with rank adjustment, per-channel magnitudes.

    The final step is the rank adjustment, so the returned signal has EXACTLY the
    original sorted values per channel. The auto-spectra are approximate, and the
    cross-spectrum is not targeted. Both are measured before and after the final
    rank step and reported. A strict post-rank cross-spectral tolerance is
    reported as UNMET when missed, never claimed.
    """
    seed = sp.check_seed(seed)
    if isinstance(max_iter, bool) or not isinstance(max_iter, int) or max_iter < 1:
        raise sp.SurrogateInputError("max_iter must be a positive integer")
    data = sp.as_float_matrix(x)
    n_ch, n = len(data), len(data[0])
    nf = sp.n_freq(n)
    target_spectra = [sp.rfft(channel) for channel in data]
    target_amp = [[abs(v) for v in spectrum] for spectrum in target_spectra]
    sorted_vals = [sorted(channel) for channel in data]
    fixed = set(sp.fixed_bins(n))

    y = []
    for c in range(n_ch):
        perm = list(range(n))
        sp.rng_for(seed, f"mv_iaaft|init|ch:{c}").shuffle(perm)
        y.append([data[c][p] for p in perm])

    prev_orders = None
    converged = False
    iterations = 0
    pre_signals = None
    for it in range(1, max_iter + 1):
        iterations = it
        spectra = [sp.rfft(channel) for channel in y]
        constrained = []
        for c in range(n_ch):
            row = []
            for k in range(nf):
                amp = target_amp[c][k]
                v = spectra[c][k]
                if k in fixed:
                    sign = 1.0 if v.real >= 0.0 else -1.0
                    row.append(complex(sign * amp, 0.0))
                else:
                    phase = v / abs(v) if abs(v) > 0.0 else complex(1.0, 0.0)
                    row.append(amp * phase)
            constrained.append(row)
        pre_signals = [sp.irfft(row, n)[0] for row in constrained]
        orders = []
        new_y = []
        for c in range(n_ch):
            order = sorted(range(n), key=lambda t, s=pre_signals[c]: (s[t], t))
            orders.append(tuple(order))
            values = [0.0] * n
            for rank, t in enumerate(order):
                values[t] = sorted_vals[c][rank]
            new_y.append(values)
        y = new_y
        if prev_orders is not None and orders == prev_orders:
            converged = True
            break
        prev_orders = orders

    post_spectra = [sp.rfft(channel) for channel in y]
    pre_spectra = [sp.rfft(s) for s in pre_signals]
    marginal = _marginal_error(y, data)
    auto_post = _auto_power_errors(post_spectra, target_spectra)
    auto_pre = _auto_power_errors(pre_spectra, target_spectra)
    cross_post = _cross_spectrum_error_or_none(post_spectra, target_spectra, n, n_ch)
    cross_pre = _cross_spectrum_error_or_none(pre_spectra, target_spectra, n, n_ch)

    if cross_post is None:
        strict_status = "NOT_APPLICABLE_SINGLE_CHANNEL"
    elif cross_post <= CROSS_SPECTRUM_STRICT_TOL:
        strict_status = "MET_POST_RANK_STRICT"
    else:
        strict_status = "UNMET_POST_RANK_STRICT"
    auto_status = "MET_POST_RANK_WITHIN_TOL" if max(auto_post) <= AUTO_SPECTRUM_TOL else "UNMET_POST_RANK_WITHIN_TOL"

    report = _make_report(
        null_id="mv_iaaft_rank_adjusted",
        seed=seed,
        n_channels=n_ch,
        n_time=n,
        status={
            "marginal": "EXACT_POST_RANK" if marginal <= MARGINAL_EXACT_TOL else "NOT_EXACT",
            "auto_spectrum": auto_status,
            "cross_spectrum": "NOT_TARGETED_MEASURED_ONLY",
            "cross_spectrum_strict": strict_status,
            "converged": "YES" if converged else "NO_MAX_ITER_REACHED",
            "intended_use": "MARGINAL_PRESERVING_NULL_WITH_APPROXIMATE_AUTO_SPECTRA",
        },
        marginal=marginal,
        auto=auto_post,
        cross=cross_post,
        pre_rank_auto_spectrum_rel_error=auto_pre,
        pre_rank_cross_spectrum_rel_error=cross_pre,
        iterations=iterations,
        converged=converged,
        dc_imag=0.0,
        nyq_imag=0.0,
        notes=[
            "post-rank signal is returned: sorted values are exact, spectra are approximate",
            "cross-spectrum is measured, not targeted, and is not guaranteed",
            f"converged={converged} after {iterations} iteration(s); max_iter={max_iter}",
        ],
    )
    return y, report


GENERATORS = {
    "common_phase_prichard_theiler": common_phase_prichard_theiler,
    "independent_phase_univariate_ft": independent_phase_univariate_ft,
    "cholesky_gaussian_cross_spectral": cholesky_gaussian_cross_spectral,
    "mv_iaaft_rank_adjusted": mv_iaaft_rank_adjusted,
}
