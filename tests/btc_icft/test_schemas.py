from sciencer_d.btc_icft.schemas import MBaselineResult, ResidualGateInput


def test_schema_dataclasses():
    m = MBaselineResult(True, "ok")
    g = ResidualGateInput(True, 0.04, 0.0, True, True, False, False)
    assert m.passed
    assert g.delta_auc == 0.04
