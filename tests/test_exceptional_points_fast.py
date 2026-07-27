from sim.pitnn.exceptional_points_fast import EPOptimizeConfig, optimize_exceptional_point


def test_fast_ep_optimizer_finds_low_gap_solution():
    result = optimize_exceptional_point(EPOptimizeConfig(maxiter=300))
    assert result["success"] and result["gap"] < 1e-4
    assert abs(result["pump_s"] + result["loss_s"] - 4.0) < 1e-3
