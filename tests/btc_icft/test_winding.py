from sciencer_d.btc_icft.level_t.winding import antivortex_fixture, single_vortex_fixture, vortex_antivortex_pair_fixture, winding_metrics


def test_winding_fixtures():
    assert winding_metrics(single_vortex_fixture())["q_net"] == 1
    assert winding_metrics(antivortex_fixture())["q_net"] == -1
    pair = winding_metrics(vortex_antivortex_pair_fixture())
    assert pair["q_net"] == 0
    assert pair["q_abs"] == 2
