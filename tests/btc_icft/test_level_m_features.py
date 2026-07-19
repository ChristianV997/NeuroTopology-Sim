import math

from sciencer_d.btc_icft.level_m.features import extract_level_m_features


def test_level_m_features_keys_unchanged():
    out = extract_level_m_features([0.1, 0.3, 0.2, 1.0])
    assert set(out) == {"spectral_power_proxy", "entropy_proxy", "lzc_proxy", "artifact_score"}


def test_level_m_features_empty_signal_unchanged():
    out = extract_level_m_features([])
    assert out == {
        "spectral_power_proxy": 0.0,
        "entropy_proxy": 0.0,
        "lzc_proxy": 0.0,
        "artifact_score": 1.0,
    }


def test_level_m_features_normal_signal_finite_values():
    out = extract_level_m_features([0.1, -0.2, 0.5, -0.1, 0.8])
    assert all(isinstance(v, float) for v in out.values())
    assert all(math.isfinite(v) for v in out.values())


def test_level_m_features_constant_signal_no_crash():
    out = extract_level_m_features([1.0, 1.0, 1.0, 1.0])
    assert all(math.isfinite(v) for v in out.values())


def test_level_m_features_no_nan_or_inf_values():
    out = extract_level_m_features([10.0, -10.0, 10.0, -10.0, 0.0])
    assert all(not math.isnan(v) and math.isfinite(v) for v in out.values())


def test_artifact_score_not_saturated_for_smooth_zero_mean_signal():
    # A smoothly oscillating, exactly-zero-mean signal (as produced by z-normalization):
    # sample-to-sample jumps are small relative to the signal's own spread. Before the
    # fix, dividing by |signal_mean| (~0 for zero-mean input) made this always return 1.0
    # regardless of actual smoothness/artifact content.
    n = 200
    signal = [math.sin(2 * math.pi * i / n) for i in range(n)]
    assert abs(sum(signal) / n) < 1e-9  # exactly (near) zero mean by construction
    out = extract_level_m_features(signal)
    assert out["artifact_score"] < 0.5


def test_artifact_score_high_for_genuinely_jumpy_zero_mean_signal():
    # Alternating +1/-1 zero-mean signal: every sample is a jump as large as the full
    # signal spread, so this should score near the top of the scale.
    signal = [1.0 if i % 2 == 0 else -1.0 for i in range(100)]
    out = extract_level_m_features(signal)
    assert out["artifact_score"] > 0.9
