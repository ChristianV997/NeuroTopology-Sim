"""Permutation-test and mixed-effects statistics for group comparisons.

Sibling module to `analysis/stats.py` (kept separate: `stats.py` stays
dependency-light on flat numpy arrays; this module needs `pandas`/`statsmodels`
and operates on window-level dataframes with a subject-id grouping column).

Built to fix a real, previously-uncommitted bug class: the ds001787 (expert vs
novice meditation) report's headline finding was itself a pseudoreplication bug
-- window-pooled permutation tests found p<0.001 for effects that dropped to
non-significant trends (p=0.10-0.29) once corrected to the proper subject-level
unit of analysis. That correction was hand-derived in a throwaway script during
the session and never committed as reusable, tested code. This module is that
code, now committed and tested (see `tests/test_permutation.py`, in particular
`test_pseudoreplication_regression`, which directly reproduces the bug class on
synthetic data and asserts the window-pooled test finds spurious significance
while the subject-blocked test correctly does not).

Three functions:
- `permutation_test` -- window-pooled label-shuffle test. Correct when each
  element really is an independent unit; pseudoreplicated (and WRONG) when
  elements are repeated measurements nested within fewer independent subjects.
  Provided as a named, tested implementation for explicit side-by-side
  reporting, not as a general-purpose default for nested data.
- `subject_blocked_permutation_test` -- aggregates each subject to one value
  first, then permutes subject-level labels. Pseudoreplication is structurally
  impossible by construction: each subject contributes exactly one point to
  the null distribution regardless of window count.
- `mixedlm_group_effect` -- linear mixed-effects model (random intercept per
  subject) via `statsmodels`. The statistically correct fix: uses every
  window-level observation while properly partitioning within- vs
  between-subject variance, recovering power that per-subject aggregation
  discards. `converged` is surfaced explicitly -- a non-converged fit can look
  clean while being untrustworthy, a known statsmodels MixedLM footgun.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Callable

import numpy as np
import pandas as pd

from analysis.stats import cohens_d


def _default_statistic(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.mean(a) - np.mean(b))


@dataclass
class PermutationResult:
    observed_stat: float
    p_value: float
    n_permutations: int
    n_a: int
    n_b: int
    method: str
    seed: int
    alternative: str
    effect_size_d: float | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AnovaPermutationResult:
    observed_f: float
    observed_eta_squared: float
    p_value: float
    n_permutations: int
    n_groups: int
    group_n: dict
    seed: int
    method: str = "permutation_anova_label_shuffle"

    def to_dict(self) -> dict:
        return asdict(self)


def _eta_squared_f(arrays: list[np.ndarray]) -> tuple[float, float]:
    """One-way F statistic and eta-squared for `arrays`, one per group.

    Same eta-squared definition `dual_engine/fmri_tda_pipeline.group_compare` uses
    (ss_between / ss_total over the pooled sample), kept here as the single source
    of truth so `permutation_anova`'s null distribution and any caller's observed
    statistic are computed identically.
    """
    from scipy import stats

    f_stat, _ = stats.f_oneway(*arrays)
    grand = np.concatenate(arrays)
    ss_between = sum(len(a) * (a.mean() - grand.mean()) ** 2 for a in arrays)
    ss_total = np.sum((grand - grand.mean()) ** 2)
    eta_sq = float(ss_between / ss_total) if ss_total > 0 else 0.0
    return float(f_stat), eta_sq


def permutation_anova(
    values,
    groups,
    n_permutations: int = 10000,
    seed: int = 0,
) -> AnovaPermutationResult:
    """Label-shuffle permutation null for a >=2-group one-way ANOVA effect size.

    `values`/`groups` are one row per SUBJECT (not per window) -- this function does
    not aggregate repeated measures itself; callers with window-level data must
    collapse to one value per subject first (as `subject_blocked_permutation_test`
    does for the two-group case), or pseudoreplication inflates the null exactly
    as documented in this module's top-level docstring.

    Parametric ANOVA p-values assume normal, equal-variance groups -- assumptions
    a real, small (n<=15/group), possibly skewed clinical cohort need not satisfy.
    This reports the same eta-squared effect size but tests it against an
    assumption-free null built by shuffling group labels `n_permutations` times and
    recomputing eta-squared on each shuffle, exactly mirroring `permutation_test`'s
    two-group label-shuffle logic generalized to k>=2 groups.
    """
    values_arr = np.asarray(values, dtype=float)
    groups_arr = np.asarray(groups)
    if values_arr.ndim != 1 or groups_arr.ndim != 1 or values_arr.shape[0] != groups_arr.shape[0]:
        raise ValueError("values and groups must be 1D arrays of the same length")
    if not np.all(np.isfinite(values_arr)):
        raise ValueError("values must be finite")

    labels = sorted(set(groups_arr.tolist()), key=str)
    if len(labels) < 2:
        raise ValueError(f"permutation_anova requires >=2 groups, got {labels}")
    group_n = {str(label): int(np.sum(groups_arr == label)) for label in labels}
    if any(n < 2 for n in group_n.values()):
        raise ValueError(f"every group needs >=2 subjects for a variance-based statistic, got {group_n}")

    observed_arrays = [values_arr[groups_arr == label] for label in labels]
    observed_f, observed_eta = _eta_squared_f(observed_arrays)

    rng = np.random.default_rng(seed)
    shuffled = groups_arr.copy()
    as_extreme = 0
    for _ in range(n_permutations):
        rng.shuffle(shuffled)
        perm_arrays = [values_arr[shuffled == label] for label in labels]
        _, perm_eta = _eta_squared_f(perm_arrays)
        if perm_eta >= observed_eta:
            as_extreme += 1
    p_value = float((as_extreme + 1) / (n_permutations + 1))

    return AnovaPermutationResult(
        observed_f=observed_f,
        observed_eta_squared=observed_eta,
        p_value=p_value,
        n_permutations=n_permutations,
        n_groups=len(labels),
        group_n=group_n,
        seed=seed,
    )


@dataclass
class MixedLMResult:
    coef: float
    se: float
    p_value: float
    converged: bool
    n_obs: int
    n_groups: int
    method: str = "mixedlm_random_intercept"
    convergence_warning: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def permutation_test(
    a,
    b,
    statistic: Callable[[np.ndarray, np.ndarray], float] | None = None,
    n_permutations: int = 10000,
    seed: int = 0,
    alternative: str = "two-sided",
) -> PermutationResult:
    """Window-pooled label-shuffle permutation test.

    Treats every element of `a`/`b` as an independent unit. Use
    `subject_blocked_permutation_test` when elements are repeated measurements
    nested within subjects -- this function will silently pseudoreplicate in
    that case, which is exactly the point of keeping it as a distinct, named,
    explicitly-labeled function: callers report it side by side with the
    subject-blocked result, not in place of it.
    """
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    stat_fn = statistic or _default_statistic
    observed = stat_fn(a, b)

    rng = np.random.default_rng(seed)
    combined = np.concatenate([a, b])
    n_a = len(a)
    n_total = len(combined)

    null_stats = np.empty(n_permutations)
    for i in range(n_permutations):
        perm = rng.permutation(n_total)
        null_stats[i] = stat_fn(combined[perm[:n_a]], combined[perm[n_a:]])

    if alternative == "two-sided":
        p = float(np.mean(np.abs(null_stats) >= abs(observed)))
    elif alternative == "greater":
        p = float(np.mean(null_stats >= observed))
    elif alternative == "less":
        p = float(np.mean(null_stats <= observed))
    else:
        raise ValueError(f"Unknown alternative: {alternative!r}")

    return PermutationResult(
        observed_stat=observed,
        p_value=p,
        n_permutations=n_permutations,
        n_a=n_a,
        n_b=len(b),
        method="permutation_test_window_pooled",
        seed=seed,
        alternative=alternative,
        effect_size_d=cohens_d(a, b),
    )


def _paired_signflip_test(
    diffs: np.ndarray, n_permutations: int, seed: int, alternative: str,
) -> tuple[float, float]:
    """Within-subject sign-flip permutation test on per-subject paired
    differences. Returns (observed_mean_diff, p_value). Under the null (no
    condition effect) each subject's difference is equally likely to have
    either sign, so the exact-in-the-limit null is generated by independently
    flipping each difference's sign."""
    diffs = np.asarray(diffs, dtype=float)
    observed = float(np.mean(diffs))
    rng = np.random.default_rng(seed)
    n = len(diffs)
    null_stats = np.empty(n_permutations)
    for i in range(n_permutations):
        signs = rng.choice((-1.0, 1.0), size=n)
        null_stats[i] = float(np.mean(diffs * signs))
    if alternative == "two-sided":
        p = float(np.mean(np.abs(null_stats) >= abs(observed)))
    elif alternative == "greater":
        p = float(np.mean(null_stats >= observed))
    elif alternative == "less":
        p = float(np.mean(null_stats <= observed))
    else:
        raise ValueError(f"Unknown alternative: {alternative!r}")
    return observed, p


def subject_blocked_permutation_test(
    df: pd.DataFrame,
    value_col: str,
    group_col: str,
    subject_col: str,
    n_permutations: int = 10000,
    seed: int = 0,
    aggregate: str = "mean",
    alternative: str = "two-sided",
) -> PermutationResult:
    """Subject-blocked permutation test: pseudoreplication-safe by construction.

    First aggregates each subject's repeated window-level measurements to ONE
    value per (subject, group), THEN permutes at the subject level. This is the
    direct, reusable encoding of the ds001787 report's methodological
    correction.

    Design-aware (the fix for a real bug found while porting ds003816): the
    previous version aggregated each subject to a single group via
    ``group_col="first"``, which is only correct for a BETWEEN-subjects design
    (each subject belongs to exactly one group -- e.g. ds001787 expert vs
    novice). Applied to a WITHIN-subject design (every subject measured in both
    conditions -- ds005620 awake/sedated, ds003969 meditation/thinking, ds003816
    meditation/resting), ``first`` silently collapsed each subject to whichever
    condition's row happened to appear first, producing a meaningless
    between-subjects statistic -- or, when every subject's first row was the
    same condition, raising "requires exactly 2 groups". This function now
    detects the design: if any subject appears in both groups it runs the
    correct within-subject PAIRED sign-flip test (per-subject condition-mean
    difference, then sign-flip permutation -- exactly what the dataset reports'
    authors did by hand); otherwise it runs the original unpaired
    between-subjects test unchanged.
    """
    if aggregate not in ("mean", "median"):
        raise ValueError(f"Unknown aggregate: {aggregate!r}")

    # One value per (subject, group) cell. Drop cells that aggregate to NaN
    # (a subject/condition whose every window was skipped, e.g. all
    # out-of-range or missing-companion-file per the OSError skip path) so
    # they neither poison a subject mean in the between-subjects branch nor
    # produce a phantom "present in both groups" subject with no real data
    # in the within-subject branch.
    cell = (
        df.groupby([subject_col, group_col])[value_col]
        .agg(aggregate)
        .reset_index()
        .dropna(subset=[value_col])
    )

    groups = cell[group_col].unique()
    if len(groups) != 2:
        raise ValueError(
            f"subject_blocked_permutation_test requires exactly 2 groups, got {list(groups)}"
        )
    g_a, g_b = sorted(groups, key=str)

    # Subjects with real data in BOTH groups => within-subject (paired) design.
    counts = cell.groupby(subject_col)[group_col].nunique()
    paired_subjects = counts[counts == 2].index.tolist()

    if paired_subjects:
        wide = cell.pivot_table(index=subject_col, columns=group_col, values=value_col)
        wide = wide.loc[paired_subjects].dropna()
        # Convention matches the unpaired branch (statistic ~ g_a - g_b).
        diffs = (wide[g_a] - wide[g_b]).to_numpy(dtype=float)
        observed, p = _paired_signflip_test(diffs, n_permutations, seed, alternative)
        sd = float(np.std(diffs, ddof=1)) if len(diffs) > 1 else 0.0
        dz = float(np.mean(diffs) / sd) if sd > 0 else 0.0
        return PermutationResult(
            observed_stat=observed,
            p_value=p,
            n_permutations=n_permutations,
            n_a=len(diffs),
            n_b=len(diffs),
            method="permutation_test_subject_blocked_paired",
            seed=seed,
            alternative=alternative,
            effect_size_d=dz,  # paired Cohen's dz (mean diff / sd of diffs)
        )

    # Between-subjects: each subject in exactly one group (original behavior).
    a = cell.loc[cell[group_col] == g_a, value_col].to_numpy(dtype=float)
    b = cell.loc[cell[group_col] == g_b, value_col].to_numpy(dtype=float)
    result = permutation_test(
        a, b, n_permutations=n_permutations, seed=seed, alternative=alternative
    )
    result.method = "permutation_test_subject_blocked"
    return result


def mixedlm_group_effect(
    df: pd.DataFrame,
    value_col: str,
    group_col: str,
    subject_col: str,
    re_formula: str | None = None,
) -> MixedLMResult:
    """Linear mixed-effects model with a random intercept per subject.

    The statistically correct fix for the pseudoreplication problem
    `subject_blocked_permutation_test` solves by aggregation: this uses ALL
    window-level observations while properly partitioning within- vs
    between-subject variance, recovering statistical power the
    aggregate-then-test approach discards.

    `converged` MUST be checked before trusting `p_value` -- a non-converged
    fit can return parameters that look like a clean result.
    """
    import warnings as _warnings

    import statsmodels.formula.api as smf

    work = df[[value_col, group_col, subject_col]].dropna().copy()
    work = work.rename(
        columns={value_col: "_value", group_col: "_group", subject_col: "_subject"}
    )
    model = smf.mixedlm(
        "_value ~ _group", data=work, groups=work["_subject"], re_formula=re_formula
    )
    # Capture (do NOT suppress) any statsmodels ConvergenceWarning so a
    # non-converged fit carries the real reason forward, not just a bool.
    # record=True intercepts the warnings into `caught` instead of printing;
    # they are re-surfaced as MixedLMResult.convergence_warning below.
    with _warnings.catch_warnings(record=True) as caught:
        _warnings.simplefilter("always")
        fit = model.fit()
    warning_texts = [str(w.message) for w in caught if issubclass(w.category, Warning)]
    convergence_warning = "; ".join(warning_texts) if warning_texts else None

    group_terms = [p for p in fit.params.index if p.startswith("_group")]
    if not group_terms:
        raise ValueError(
            f"Could not find a group coefficient in fitted params: {list(fit.params.index)}"
        )
    term = group_terms[0]

    return MixedLMResult(
        coef=float(fit.params[term]),
        se=float(fit.bse[term]),
        p_value=float(fit.pvalues[term]),
        converged=bool(fit.converged),
        n_obs=int(fit.nobs),
        n_groups=int(work["_subject"].nunique()),
        convergence_warning=convergence_warning,
    )
