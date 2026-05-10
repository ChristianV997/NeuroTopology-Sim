from sciencer_d.btc_icft.level_d.dukkha_lock import compute_d_lock


def test_d_lock_formula():
    x = compute_d_lock(control_cost=1, recovery_latency=2, residual_half_life=3, selfing=1, reactivity=1, rnt_half_life=1, precision_lock=1, flexibility=2, decentering=1)
    assert x == 7
