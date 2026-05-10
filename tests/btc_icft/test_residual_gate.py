from sciencer_d.btc_icft.level_t.residual import residual_promotion_gate
from sciencer_d.btc_icft.schemas import ResidualGateInput


def test_residual_gate_blocks_missing_m():
    r = residual_promotion_gate(ResidualGateInput(False, 0.1, -0.01, True, True, False, False))
    assert not r.promoted
