from sciencer_d.btc_icft.level_d.dukkha_lock import compute_d_lock


def reactive_trajectory() -> tuple[float, float]:
    base = compute_d_lock(control_cost=1, recovery_latency=1, residual_half_life=1, selfing=1, reactivity=1, rnt_half_life=1, precision_lock=1, flexibility=1, decentering=1)
    reactive = compute_d_lock(control_cost=2, recovery_latency=2, residual_half_life=1.5, selfing=2, reactivity=2.5, rnt_half_life=1.5, precision_lock=2, flexibility=0.5, decentering=0.5)
    return base, reactive


def trained_trajectory() -> tuple[float, float]:
    base = compute_d_lock(control_cost=2, recovery_latency=2, residual_half_life=2, selfing=2, reactivity=2, rnt_half_life=2, precision_lock=2, flexibility=0.5, decentering=0.5)
    trained = compute_d_lock(control_cost=1, recovery_latency=1, residual_half_life=1, selfing=1, reactivity=1, rnt_half_life=1, precision_lock=1, flexibility=1.5, decentering=1.5)
    return base, trained
