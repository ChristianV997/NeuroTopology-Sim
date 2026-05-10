from sciencer_d.btc_icft.simulations.synthetic_d import reactive_trajectory, trained_trajectory
from sciencer_d.btc_icft.simulations.synthetic_t import synthetic_winding_summary


def test_synthetic_trajectories_and_foam():
    rb, rr = reactive_trajectory()
    tb, tr = trained_trajectory()
    assert rr > rb
    assert tr < tb
    assert synthetic_winding_summary()["q_net"] == 0
