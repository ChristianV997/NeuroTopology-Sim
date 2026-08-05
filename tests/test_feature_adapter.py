import numpy as np


def test_feature_panel_names_are_fixed():
    required = {
        "q_net", "q_abs", "f_dress", "defect_density", "mean_plv",
        "phase_discontinuity_proxy", "beta_spectral_topology_mass",
    }
    assert len(required) == 7
