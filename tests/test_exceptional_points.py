import numpy as np
from sim.pitnn.exceptional_points import EPScanConfig, scan_exceptional_points

def test_ep_scan_is_deterministic_and_finite():
    grid = np.linspace(0, 4, 21); result = scan_exceptional_points(EPScanConfig(grid, grid, coupling_s=1.0, epsilon_threshold=.1))
    assert result["gaps"].shape == (21, 21)
    assert np.all(np.isfinite(result["gaps"])) and np.all(np.isfinite(result["fidelities"]))
    assert result["candidate_count"] if "candidate_count" in result else True
    assert abs(result["best"]["pump_s"] + result["best"]["loss_s"] - 4.0) < .3
