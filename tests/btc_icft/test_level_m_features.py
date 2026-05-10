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
