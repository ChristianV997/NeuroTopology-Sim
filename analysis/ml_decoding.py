"""Real ML decoding as a complementary validity check: cross-validated
classifiers (deliberately simple -- logistic regression, appropriate to this
project's small-n datasets) on real feature sets, with
`sklearn.model_selection.permutation_test_score` for a proper null.

This does not replace the per-metric permutation/subject-blocked tests
already built (`analysis/permutation.py`); it answers a different, additive
question -- "can any COMBINATION of real features discriminate state better
than chance?" -- alongside the existing per-metric univariate tests, not
instead of them.
"""
from __future__ import annotations

import numpy as np


def build_feature_matrix(
    feature_dicts: list[dict], feature_keys: list[str] | None = None,
) -> tuple[np.ndarray, list[str], list[int]]:
    """Build a numeric feature matrix from a list of per-row feature dicts.

    `feature_keys`, if not given, defaults to every key present in ALL
    dicts whose value is a finite real number in every one of them (a
    conservative auto-selection -- silently dropping a column that's only
    sometimes numeric would hide a real data problem rather than surfacing
    it). Rows with any NaN/missing value in the selected keys are dropped
    (not imputed) -- imputation would fabricate values this repo has no
    basis for.

    Returns `(X, feature_names, kept_row_indices)` -- `kept_row_indices`
    lets callers align `X`'s rows back to their own label array after
    dropping incomplete rows.
    """
    if not feature_dicts:
        return np.empty((0, 0)), [], []

    if feature_keys is None:
        candidate_keys = set(feature_dicts[0].keys())
        for d in feature_dicts[1:]:
            candidate_keys &= set(d.keys())
        feature_keys = sorted(
            k for k in candidate_keys
            if all(isinstance(d[k], (int, float)) and np.isfinite(d[k]) for d in feature_dicts)
        )

    rows = []
    kept_indices = []
    for i, d in enumerate(feature_dicts):
        try:
            values = [float(d[k]) for k in feature_keys]
        except (KeyError, TypeError, ValueError):
            continue
        if not all(np.isfinite(v) for v in values):
            continue
        rows.append(values)
        kept_indices.append(i)

    X = np.array(rows, dtype=float) if rows else np.empty((0, len(feature_keys)))
    return X, feature_keys, kept_indices


def evaluate_decoding(
    X: np.ndarray, y: np.ndarray, seed: int = 0, n_permutations: int = 1000, cv_folds: int = 5,
) -> dict:
    """Cross-validated logistic-regression decoding accuracy plus a proper
    permutation-test null via `sklearn.model_selection.permutation_test_score`.

    A deliberately simple model (standardized logistic regression), matching
    this repo's existing preference for simple models appropriate to its
    small-n datasets over anything more expressive that would be prone to
    overfitting a handful of subjects.

    Returns `{"status": "insufficient_data", ...}` if either class has fewer
    samples than `cv_folds` (stratified CV can't form valid folds otherwise)
    -- matching this repo's established skip-and-report convention.
    """
    from sklearn.linear_model import LogisticRegression
    from sklearn.model_selection import StratifiedKFold, permutation_test_score
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import StandardScaler

    y = np.asarray(y)
    classes, counts = np.unique(y, return_counts=True)
    if len(classes) != 2:
        return {"status": "not_applicable", "reason": f"expected exactly 2 classes, got {len(classes)}"}
    if counts.min() < cv_folds:
        return {
            "status": "insufficient_data",
            "reason": f"smallest class has {int(counts.min())} samples, need >= cv_folds={cv_folds} for stratified CV",
        }

    pipeline = Pipeline([("scale", StandardScaler()), ("clf", LogisticRegression(max_iter=1000))])
    cv = StratifiedKFold(n_splits=cv_folds, shuffle=True, random_state=seed)

    score, permutation_scores, p_value = permutation_test_score(
        pipeline, X, y, cv=cv, n_permutations=n_permutations, random_state=seed, scoring="accuracy",
    )

    return {
        "status": "computed",
        "n_samples": int(len(y)),
        "n_features": int(X.shape[1]),
        "classes": [str(c) for c in classes],
        "cv_folds": cv_folds,
        "accuracy": float(score),
        "chance_level": float(counts.max() / counts.sum()),
        "permutation_null_mean_accuracy": float(np.mean(permutation_scores)),
        "permutation_null_std_accuracy": float(np.std(permutation_scores)),
        "n_permutations": n_permutations,
        "p_value": float(p_value),
        "seed": seed,
    }


def build_decoding_report(
    feature_dicts: list[dict], labels: list, feature_keys: list[str] | None = None,
    seed: int = 0, n_permutations: int = 1000, cv_folds: int = 5,
) -> dict:
    """Build a feature matrix from `feature_dicts` (via `build_feature_matrix`)
    and evaluate decoding of the corresponding `labels`. `labels` must be
    the same length as `feature_dicts`; rows dropped by `build_feature_matrix`
    (missing/non-finite features) drop their label too, via the returned
    `kept_row_indices`.
    """
    X, feature_names, kept_indices = build_feature_matrix(feature_dicts, feature_keys=feature_keys)
    if X.shape[0] == 0 or X.shape[1] == 0:
        return {"status": "not_applicable", "reason": "no usable feature rows/columns after filtering"}

    y = np.asarray([labels[i] for i in kept_indices])
    result = evaluate_decoding(X, y, seed=seed, n_permutations=n_permutations, cv_folds=cv_folds)
    result["feature_names"] = feature_names
    result["n_rows_dropped"] = len(feature_dicts) - len(kept_indices)
    return result
