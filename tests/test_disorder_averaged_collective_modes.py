import numpy as np
import pytest

from scripts.run_disorder_averaged_collective_modes import (
    _append_checkpoint,
    _initialize_checkpoint,
    _load_checkpoint,
    _signed_permutation_pvalue,
    _summarize,
)


def test_exact_sign_flip_pvalue_is_deterministic_and_two_sided() -> None:
    values = np.array([0.4, 0.3, 0.2, 0.1])
    assert _signed_permutation_pvalue(values) == _signed_permutation_pvalue(-values)
    assert 0.0 < _signed_permutation_pvalue(values) <= 1.0


def test_summary_uses_matched_disorder_and_null_adjustment() -> None:
    records = []
    for seed in (10, 11):
        for spacing, candidate_tau, null_tau in ((3.0, 4.0, 2.0), (18.0, 2.0, 2.0)):
            records.extend((
                {"spacing_nm": spacing, "collective_rate_s": 0.0, "disorder_seed": seed, "converged": True, "tau_subradiant_s": null_tau},
                {"spacing_nm": spacing, "collective_rate_s": 1e7, "disorder_seed": seed, "converged": True, "tau_subradiant_s": candidate_tau},
            ))
    summary = _summarize(records, [3.0, 18.0], [0.0, 1e7])[0]
    assert summary["paired_disorder_samples"] == 2
    assert summary["mean_log_short_vs_long_null_adjusted_contrast"] == np.log(2.0)


def test_summary_rejects_nonfinite_lifetime_pairs():
    records = [
        {"spacing_nm": 3.0, "collective_rate_s": 0.0, "disorder_seed": 10, "converged": True, "tau_subradiant_s": np.inf},
        {"spacing_nm": 18.0, "collective_rate_s": 0.0, "disorder_seed": 10, "converged": True, "tau_subradiant_s": 2.0},
        {"spacing_nm": 3.0, "collective_rate_s": 1e7, "disorder_seed": 10, "converged": True, "tau_subradiant_s": 4.0},
        {"spacing_nm": 18.0, "collective_rate_s": 1e7, "disorder_seed": 10, "converged": True, "tau_subradiant_s": 2.0},
    ]
    summary = _summarize(records, [3.0, 18.0], [0.0, 1e7])[0]
    assert summary["paired_disorder_samples"] == 0
    assert summary["invalid_disorder_samples"] == 1
    assert summary["mean_log_short_vs_long_null_adjusted_contrast"] is None


def test_checkpoint_round_trip_and_fingerprint_guard(tmp_path):
    path = tmp_path / "records.jsonl"
    fingerprint = "abc123"
    _initialize_checkpoint(path, fingerprint)
    record = {"point_id": "spacing=3;collective_rate=0;seed=1", "converged": True}
    _append_checkpoint(path, record)
    assert _load_checkpoint(path, fingerprint) == {record["point_id"]: record}
    with pytest.raises(ValueError):
        _load_checkpoint(path, "different")
