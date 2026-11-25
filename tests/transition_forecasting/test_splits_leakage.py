"""Adversarial leakage-prevention tests for synthetic transition-forecasting splits."""
from __future__ import annotations

import numpy as np
import pytest

from analysis.transition_forecasting import (
    ForecastStatus,
    LockedSplit,
    locked_split,
    run_benchmark,
    validate_split,
)
from tests.transition_forecasting.test_benchmark import make_dataset


def test_interleaved_repeated_subjects_stay_disjoint_across_nested_validation():
    # Interleaved subjects: row-based slicing would split subjects across train and validation.
    subjects = np.array(["s0", "s1", "s2", "s3"] * 5)
    sessions = np.arange(len(subjects))
    timestamps = np.arange(len(subjects), dtype=float)

    split = locked_split(subjects, sessions, timestamps, "subject-held-out", validation_fraction=0.3)
    validate_split(split, subjects, sessions, timestamps)

    train_s = set(subjects[list(split.train)].tolist())
    val_s = set(subjects[list(split.validation)].tolist())
    test_s = set(subjects[list(split.test)].tolist())
    assert train_s and val_s and test_s
    assert not (train_s & val_s)
    assert not (train_s & test_s)
    assert not (val_s & test_s)


def test_interleaved_repeated_sessions_stay_disjoint_across_nested_validation():
    # Exact layout of make_dataset(): sessions tiled across subjects.
    dataset = make_dataset()
    split = locked_split(dataset.subjects, dataset.sessions, dataset.timestamps, "session-held-out")
    validate_split(split, dataset.subjects, dataset.sessions, dataset.timestamps)

    train_sess = set(dataset.sessions[list(split.train)].tolist())
    val_sess = set(dataset.sessions[list(split.validation)].tolist())
    test_sess = set(dataset.sessions[list(split.test)].tolist())
    assert train_sess and val_sess and test_sess
    assert not (train_sess & val_sess)
    assert not (train_sess & test_sess)
    assert not (val_sess & test_sess)


def test_nonmonotonic_timestamps_forward_time_orders_and_purges_correctly():
    # Shuffled timestamps with overlapping windows and positive prediction horizon.
    rng = np.random.default_rng(123)
    base_ts = np.arange(40, dtype=float)
    perm = rng.permutation(len(base_ts))
    timestamps = base_ts[perm]
    subjects = np.repeat(np.arange(4), 10)
    sessions = np.tile(np.arange(10), 4)

    split = locked_split(
        subjects,
        sessions,
        timestamps,
        "forward-time",
        cutoff=30.0,
        validation_fraction=0.25,
        prediction_horizon=2.0,
        window_lengths=2.0,
        embargo=1.0,
    )
    validate_split(
        split,
        subjects,
        sessions,
        timestamps,
        prediction_horizon=2.0,
        window_lengths=2.0,
        embargo=1.0,
    )

    assert len(split.purged) > 0
    # Outer boundary: min(test_ts - window) = 30 - 2 = 28; train/val rows must satisfy ts + 2 + 1 <= 28 -> ts <= 25
    assert float(np.max(timestamps[list(split.validation)])) <= 25.0
    assert float(np.min(timestamps[list(split.test)])) >= 30.0
    # Nested boundary: inner_train + horizon + embargo <= min(val_ts - window)
    val_earliest_start = float(np.min(timestamps[list(split.validation)] - 2.0))
    assert float(np.max(timestamps[list(split.train)] + 3.0)) <= val_earliest_start


def test_validate_split_rejects_horizon_and_window_overlap_leakage():
    n = 20
    subjects = np.repeat(np.arange(2), 10)
    sessions = np.arange(n)
    timestamps = np.arange(n, dtype=float)

    # Naive unpurged split: train=[0..14], test=[15..19]
    naive = LockedSplit(
        strategy="forward-time",
        train=tuple(range(15)),
        validation=(),
        test=tuple(range(15, 20)),
        cutoff=15.0,
    )
    # Valid when horizon=0, window=0, embargo=0
    validate_split(naive, subjects, sessions, timestamps)
    # Fails closed when prediction_horizon=2.0 causes t=14 -> 16 > 15
    with pytest.raises(ValueError, match="horizon or overlapping-window leakage"):
        validate_split(naive, subjects, sessions, timestamps, prediction_horizon=2.0)
    # Fails closed when window_lengths=2.0 causes test window [13, 15] to overlap train t=14
    with pytest.raises(ValueError, match="horizon or overlapping-window leakage"):
        validate_split(naive, subjects, sessions, timestamps, window_lengths=2.0)


def test_validate_split_rejects_nested_group_leakage():
    subjects = np.array(["a", "a", "b", "b", "c", "c"])
    sessions = np.arange(6)
    timestamps = np.arange(6, dtype=float)
    leaking_val = LockedSplit(
        strategy="subject-held-out",
        train=(0, 2),
        validation=(1, 3),  # Shares subjects "a" and "b" with train
        test=(4, 5),
    )
    with pytest.raises(ValueError, match="subject leakage"):
        validate_split(leaking_val, subjects, sessions, timestamps)


@pytest.mark.parametrize(
    "bad_kwargs,match",
    [
        ({"timestamps": np.array([0.0, np.nan, 2.0, 3.0])}, "timestamps must be finite"),
        ({"timestamps": np.array([True, False, True, False])}, "timestamps must be numeric"),
        ({"subjects": np.array(["a", None, "b", "b"], dtype=object)}, "missing"),
        ({"sessions": np.array(["s1", "  ", "s2", "s2"])}, "empty"),
        ({"prediction_horizon": -1.0}, "non-negative"),
        ({"embargo": True}, "not bool"),
        ({"window_lengths": -0.5}, "non-negative"),
    ],
)
def test_invalid_metadata_fails_closed(bad_kwargs, match):
    kwargs = {
        "subjects": np.array(["a", "a", "b", "b"]),
        "sessions": np.array(["s1", "s1", "s2", "s2"]),
        "timestamps": np.array([0.0, 1.0, 2.0, 3.0]),
        "strategy": "forward-time",
        "cutoff": 2.0,
        "validation_fraction": 0.0,
    }
    kwargs.update(bad_kwargs)
    with pytest.raises(ValueError, match=match):
        locked_split(**kwargs)


def test_boundary_cases_single_group_or_overpurged_fail_closed():
    # Only one training subject left after holding out "b" -> cannot form disjoint nested validation
    with pytest.raises(ValueError, match="at least two training groups"):
        locked_split(
            np.array(["a", "a", "a", "b", "b"]),
            np.arange(5),
            np.arange(5, dtype=float),
            "subject-held-out",
            validation_fraction=0.2,
        )
    # Purging consumes all training rows
    with pytest.raises(ValueError, match="non-empty train and test"):
        locked_split(
            np.array(["a", "a", "a", "b", "b"]),
            np.arange(5),
            np.arange(5, dtype=float),
            "forward-time",
            cutoff=3.0,
            prediction_horizon=10.0,
            validation_fraction=0.0,
        )


def test_run_benchmark_forward_time_enforces_horizon_and_window_purging_on_synthetic_data():
    dataset = make_dataset("triadic", synthetic=True)
    report = run_benchmark(
        dataset,
        split_strategy="forward-time",
        cutoff=48.0,
        validation_fraction=0.2,
        embargo=1.0,
        seed=7,
    )
    assert report.status == ForecastStatus.SYNTHETIC_DEMO_ONLY.value
    split_info = report.subject_session_split
    assert len(split_info["purged"]) > 0
    # Purged rows cannot be used for preprocessing fit
    purged_idx = split_info["purged"][0]
    leaked_report = run_benchmark(
        dataset,
        split_strategy="forward-time",
        cutoff=48.0,
        validation_fraction=0.2,
        embargo=1.0,
        preprocessing_fit_indices=split_info["train"] + [purged_idx],
        seed=7,
    )
    assert leaked_report.status == ForecastStatus.LEAKAGE_DETECTED.value
