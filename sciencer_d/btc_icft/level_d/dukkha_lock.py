def compute_d_lock(
    *,
    control_cost: float,
    recovery_latency: float,
    residual_half_life: float,
    selfing: float,
    reactivity: float,
    rnt_half_life: float,
    precision_lock: float,
    flexibility: float,
    decentering: float,
) -> float:
    return (
        control_cost
        + recovery_latency
        + residual_half_life
        + selfing
        + reactivity
        + rnt_half_life
        + precision_lock
        - flexibility
        - decentering
    )
