import numpy as np

from sim.pitnn.bayesian_falsification import compare_models
from sim.pitnn.mesoscale_membrane import membrane_current_variance, simulate_fluctuation_biased_fhn


def test_mesoscale_variance_drives_finite_fhn_statistic() -> None:
    variance = membrane_current_variance(0.95e-9)
    result = simulate_fluctuation_biased_fhn(variance)
    assert variance > 0
    assert np.all(np.isfinite(result["voltage_V"]))
    assert 0 <= result["threshold_crossing_fraction"] <= 1


def test_l1_removes_constant_non_predictive_topology_feature() -> None:
    x = np.linspace(0, 1, 80); signal = 0.1 + np.sin(2 * np.pi * x)
    result = compare_models(signal, {"q_emp_mean": 1.0}, topological_l1_penalty=1.0)
    assert abs(result["pitnn"]["topological_weight"]) < 1e-12
    assert result["verdict"] == "NOT_SUPPORTED"
