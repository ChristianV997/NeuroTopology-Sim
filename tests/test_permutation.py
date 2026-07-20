"""Tests for analysis/permutation.py, mirroring test_stats.py's synthetic
ground-truth pattern: recover known effects, correctly reject known nulls,
deterministic seeding -- plus the pseudoreplication regression test that is
the entire reason this module exists.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from analysis.permutation import (
    mixedlm_group_effect,
    permutation_test,
    subject_blocked_permutation_test,
)


# ---------------------------------------------------------------------------
# permutation_test (window-pooled)
# ---------------------------------------------------------------------------

def test_permutation_test_recovers_known_effect():
    rng = np.random.default_rng(1)
    a = rng.normal(0, 1, 200)
    b = rng.normal(1, 1, 200)  # Delta mu = 1, same as test_stats.py's cohens_d test
    result = permutation_test(a, b, n_permutations=2000, seed=0)
    assert result.p_value < 0.05
    assert result.observed_stat < 0  # a.mean < b.mean
    assert result.effect_size_d == pytest.approx(-1.0, abs=0.2)


def test_permutation_test_correctly_rejects_known_null():
    rng = np.random.default_rng(2)
    a = rng.normal(0, 1, 200)
    b = rng.normal(0, 1, 200)  # identical distribution
    result = permutation_test(a, b, n_permutations=2000, seed=0)
    assert result.p_value > 0.05


def test_permutation_test_deterministic():
    rng = np.random.default_rng(3)
    a = rng.normal(0, 1, 50)
    b = rng.normal(0.5, 1, 50)
    r1 = permutation_test(a, b, n_permutations=1000, seed=42)
    r2 = permutation_test(a, b, n_permutations=1000, seed=42)
    assert r1.p_value == r2.p_value
    assert r1.observed_stat == r2.observed_stat


def test_permutation_test_alternative_directions():
    a = np.array([5.0, 5.0, 5.0, 5.0])
    b = np.array([1.0, 1.0, 1.0, 1.0])
    greater = permutation_test(a, b, n_permutations=500, seed=0, alternative="greater")
    less = permutation_test(a, b, n_permutations=500, seed=0, alternative="less")
    assert greater.p_value < less.p_value


def test_permutation_test_unknown_alternative_raises():
    with pytest.raises(ValueError):
        permutation_test([1.0, 2.0], [3.0, 4.0], alternative="bogus")


def test_permutation_test_method_label():
    result = permutation_test([1.0, 2.0], [3.0, 4.0], n_permutations=100)
    assert result.method == "permutation_test_window_pooled"


def test_permutation_result_to_dict_json_serializable():
    import json

    result = permutation_test([1.0, 2.0, 3.0], [2.0, 3.0, 4.0], n_permutations=100)
    json.dumps(result.to_dict())  # must not raise


# ---------------------------------------------------------------------------
# subject_blocked_permutation_test
# ---------------------------------------------------------------------------

def _make_df(subject_means: dict[str, float], group_of: dict[str, str],
             n_windows: int, within_subject_noise: float, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for subject, mean in subject_means.items():
        for w in range(n_windows):
            rows.append({
                "subject_id": subject,
                "group": group_of[subject],
                "value": mean + rng.normal(0, within_subject_noise),
            })
    return pd.DataFrame(rows)


def test_subject_blocked_recovers_known_subject_level_effect():
    subject_means = {f"a{i}": 1.0 for i in range(10)} | {f"b{i}": 0.0 for i in range(10)}
    group_of = {f"a{i}": "A" for i in range(10)} | {f"b{i}": "B" for i in range(10)}
    df = _make_df(subject_means, group_of, n_windows=20, within_subject_noise=0.2, seed=0)
    result = subject_blocked_permutation_test(df, "value", "group", "subject_id", n_permutations=2000, seed=0)
    assert result.p_value < 0.05
    assert result.method == "permutation_test_subject_blocked"
    assert result.n_a == 10 and result.n_b == 10


def test_subject_blocked_correctly_rejects_known_null():
    rng = np.random.default_rng(5)
    subject_means = {f"a{i}": rng.normal(0, 0.3) for i in range(10)}
    subject_means |= {f"b{i}": rng.normal(0, 0.3) for i in range(10)}
    group_of = {f"a{i}": "A" for i in range(10)} | {f"b{i}": "B" for i in range(10)}
    df = _make_df(subject_means, group_of, n_windows=20, within_subject_noise=0.2, seed=5)
    result = subject_blocked_permutation_test(df, "value", "group", "subject_id", n_permutations=2000, seed=0)
    assert result.p_value > 0.05


def test_subject_blocked_requires_exactly_two_groups():
    df = pd.DataFrame({
        "subject_id": ["a", "b", "c"],
        "group": ["X", "Y", "Z"],
        "value": [1.0, 2.0, 3.0],
    })
    with pytest.raises(ValueError, match="exactly 2 groups"):
        subject_blocked_permutation_test(df, "value", "group", "subject_id")


# ---------------------------------------------------------------------------
# Within-subject (paired) design detection -- the ds003816/ds005620/ds003969
# fix: every subject is measured in BOTH conditions, so the correct test is a
# paired sign-flip, not the between-subjects unpaired test.
# ---------------------------------------------------------------------------

def _make_within_subject_df(subject_effect: dict[str, float], n_windows: int,
                            within_noise: float, seed: int) -> pd.DataFrame:
    """Each subject appears in BOTH groups A and B; `subject_effect[s]` is the
    per-subject B-minus-A shift (the paired effect for that subject)."""
    rng = np.random.default_rng(seed)
    rows = []
    for subject, eff in subject_effect.items():
        base = rng.normal(0, 1.0)  # subject's own baseline (nuisance, paired out)
        for group, level in (("A", 0.0), ("B", eff)):
            for _w in range(n_windows):
                rows.append({
                    "subject_id": subject,
                    "group": group,
                    "value": base + level + rng.normal(0, within_noise),
                })
    return pd.DataFrame(rows)


def test_subject_blocked_detects_within_subject_design_and_uses_paired():
    """When every subject is in both groups, the method must switch to the
    paired sign-flip test, not the unpaired between-subjects test."""
    df = _make_within_subject_df({f"s{i}": 0.0 for i in range(12)},
                                 n_windows=10, within_noise=0.2, seed=0)
    result = subject_blocked_permutation_test(df, "value", "group", "subject_id",
                                              n_permutations=2000, seed=0)
    assert result.method == "permutation_test_subject_blocked_paired"
    assert result.n_a == result.n_b == 12


def test_subject_blocked_paired_recovers_known_within_subject_effect():
    """A consistent per-subject B>A shift, even with large between-subject
    baseline variance the paired design removes, must be detected."""
    df = _make_within_subject_df({f"s{i}": 0.8 for i in range(15)},
                                 n_windows=12, within_noise=0.2, seed=1)
    result = subject_blocked_permutation_test(df, "value", "group", "subject_id",
                                              n_permutations=5000, seed=0)
    assert result.p_value < 0.05
    # convention: statistic ~ g_a - g_b = A - B, so a B>A effect is negative
    assert result.observed_stat < 0


def test_subject_blocked_paired_correctly_rejects_within_subject_null():
    df = _make_within_subject_df({f"s{i}": 0.0 for i in range(15)},
                                 n_windows=12, within_noise=0.2, seed=2)
    result = subject_blocked_permutation_test(df, "value", "group", "subject_id",
                                              n_permutations=5000, seed=0)
    assert result.p_value > 0.05


def test_subject_blocked_paired_pairs_out_between_subject_variance():
    """The decisive property: a real within-subject effect swamped by huge
    between-subject baseline variance. The paired test must still find it
    (it differences the baseline away); an unpaired test on the same subject
    means would be drowned out. This is the within-subject analogue of the
    pseudoreplication regression test above."""
    rng = np.random.default_rng(9)
    rows = []
    for i in range(14):
        base = rng.normal(0, 5.0)  # enormous between-subject spread
        for group, level in (("A", 0.0), ("B", 0.5)):  # small but consistent B>A
            for _w in range(10):
                rows.append({"subject_id": f"s{i}", "group": group,
                             "value": base + level + rng.normal(0, 0.2)})
    df = pd.DataFrame(rows)
    paired = subject_blocked_permutation_test(df, "value", "group", "subject_id",
                                              n_permutations=5000, seed=0)
    assert paired.method == "permutation_test_subject_blocked_paired"
    assert paired.p_value < 0.05, "paired test failed to recover an effect it should pair out baseline variance to see"


def test_subject_blocked_paired_handles_all_nan_cell():
    """Regression test: a subject whose every window in one condition is NaN
    (e.g. all skipped by the OSError/out-of-range skip path) must not crash
    the paired test with a phantom 'present in both groups' subject that
    pivot_table then drops. It should simply be excluded from the paired set."""
    rows = []
    for i in range(10):
        for group, level in (("A", 0.0), ("B", 0.6)):
            for _w in range(8):
                rows.append({"subject_id": f"s{i}", "group": group,
                             "value": level + np.random.default_rng(i).normal(0, 0.2)})
    # one extra subject whose condition-B windows are ALL NaN
    for _w in range(8):
        rows.append({"subject_id": "s_bad", "group": "A", "value": 0.1})
        rows.append({"subject_id": "s_bad", "group": "B", "value": float("nan")})
    df = pd.DataFrame(rows)
    result = subject_blocked_permutation_test(df, "value", "group", "subject_id",
                                              n_permutations=2000, seed=0)
    assert result.method == "permutation_test_subject_blocked_paired"
    assert result.n_a == 10  # s_bad excluded, 10 clean paired subjects remain


# ---------------------------------------------------------------------------
# THE key regression test: pseudoreplication (the exact ds001787 bug class)
# ---------------------------------------------------------------------------

def test_pseudoreplication_regression():
    """Reproduces the exact bug class the ds001787 report exposed: an apparent
    per-window effect that is actually driven by only 2 of 10 subjects in one
    group. The window-pooled test (naive, wrong) must find spurious
    significance because it treats many repeated near-identical windows from
    a couple of outlier subjects as independent evidence. The subject-blocked
    test (correct) must NOT reject the null, because among the 10 independent
    subjects per group, only 2 actually differ -- exactly the situation where
    ds001787's real analysis found window-pooled p<0.001 collapse to
    subject-level p=0.10-0.29.
    """
    rng = np.random.default_rng(7)

    # Group A: 8 "ordinary" subjects centered at 0, 2 outlier subjects at +3.
    # Group B: 10 subjects, all centered at 0. No real group-level effect --
    # group A's outliers are the ONLY reason a naive pooled test would see one.
    subject_means: dict[str, float] = {}
    group_of: dict[str, str] = {}
    for i in range(8):
        subject_means[f"a{i}"] = rng.normal(0, 0.3)
        group_of[f"a{i}"] = "A"
    for i in range(8, 10):
        subject_means[f"a{i}"] = rng.normal(3.0, 0.3)  # the 2 outlier subjects
        group_of[f"a{i}"] = "A"
    for i in range(10):
        subject_means[f"b{i}"] = rng.normal(0, 0.3)
        group_of[f"b{i}"] = "B"

    # Each subject contributes MANY windows, tightly clustered around their own
    # subject mean -- this is what inflates the pooled test's apparent n
    # without adding genuine independent evidence.
    df = _make_df(subject_means, group_of, n_windows=50, within_subject_noise=0.15, seed=7)

    a_windows = df.loc[df["group"] == "A", "value"].to_numpy()
    b_windows = df.loc[df["group"] == "B", "value"].to_numpy()

    pooled = permutation_test(a_windows, b_windows, n_permutations=2000, seed=0)
    blocked = subject_blocked_permutation_test(df, "value", "group", "subject_id", n_permutations=2000, seed=0)

    assert pooled.p_value < 0.05, (
        f"expected the naive pooled test to find spurious significance, got p={pooled.p_value}"
    )
    assert blocked.p_value > 0.05, (
        f"expected the subject-blocked test to correctly NOT reject the null, got p={blocked.p_value}"
    )
    # the pooled test's n is the (pseudoreplicated) window count; the blocked
    # test's n is the true subject count -- this is the whole point.
    assert pooled.n_a == 500 and pooled.n_b == 500  # 10 subjects * 50 windows, each group
    assert blocked.n_a == 10 and blocked.n_b == 10


# ---------------------------------------------------------------------------
# mixedlm_group_effect
# ---------------------------------------------------------------------------

def test_mixedlm_recovers_known_fixed_effect():
    rng = np.random.default_rng(10)
    rows = []
    true_coef = 1.5
    for i in range(20):
        subject_intercept = rng.normal(0, 0.5)
        group = "treatment" if i < 10 else "control"
        effect = true_coef if group == "treatment" else 0.0
        for w in range(15):
            rows.append({
                "subject_id": f"s{i}",
                "group": group,
                "value": subject_intercept + effect + rng.normal(0, 0.3),
            })
    df = pd.DataFrame(rows)
    result = mixedlm_group_effect(df, "value", "group", "subject_id")
    assert result.converged
    assert result.coef == pytest.approx(true_coef, abs=0.5) or result.coef == pytest.approx(-true_coef, abs=0.5)
    assert result.p_value < 0.05
    assert result.n_groups == 20
    assert result.n_obs == 300


def test_mixedlm_correctly_rejects_known_null():
    rng = np.random.default_rng(11)
    rows = []
    for i in range(20):
        subject_intercept = rng.normal(0, 0.5)
        group = "A" if i < 10 else "B"
        for w in range(15):
            rows.append({
                "subject_id": f"s{i}",
                "group": group,
                "value": subject_intercept + rng.normal(0, 0.3),  # no group effect
            })
    df = pd.DataFrame(rows)
    result = mixedlm_group_effect(df, "value", "group", "subject_id")
    assert result.converged
    assert result.p_value > 0.05


def test_mixedlm_surfaces_convergence_flag():
    """Regardless of whether this particular fit converges, `converged` must be
    a real, checkable boolean surfaced on the result -- not silently omitted."""
    rng = np.random.default_rng(12)
    rows = []
    for i in range(6):
        for w in range(3):
            rows.append({
                "subject_id": f"s{i}",
                "group": "A" if i < 3 else "B",
                "value": rng.normal(0, 1),
            })
    df = pd.DataFrame(rows)
    result = mixedlm_group_effect(df, "value", "group", "subject_id")
    assert isinstance(result.converged, bool)


def test_mixedlm_result_to_dict_json_serializable():
    import json

    rng = np.random.default_rng(13)
    rows = [
        {"subject_id": f"s{i}", "group": "A" if i < 5 else "B", "value": rng.normal(0, 1)}
        for i in range(10) for _ in range(5)
    ]
    df = pd.DataFrame(rows)
    result = mixedlm_group_effect(df, "value", "group", "subject_id")
    json.dumps(result.to_dict())  # must not raise
