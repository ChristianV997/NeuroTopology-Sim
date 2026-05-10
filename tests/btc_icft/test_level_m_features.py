from sciencer_d.btc_icft.level_m.features import extract_level_m_features


def test_level_m_features_keys():
    out = extract_level_m_features([0.1, 0.3, 0.2, 1.0])
    assert set(out) == {"spectral_power_proxy", "entropy_proxy", "lzc_proxy", "artifact_score"}
