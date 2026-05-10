from sciencer_d.btc_icft.level_t.residual import residual_promotion_gate
from sciencer_d.btc_icft.schemas import ResidualGateInput


def _inp(**kwargs):
    base = dict(
        m_baseline_passed=True,
        delta_auc=0.05,
        delta_ece=-0.01,
        nulls_passed=True,
        ablations_passed=True,
        leakage_detected=False,
        artifact_dominance=False,
    )
    base.update(kwargs)
    return ResidualGateInput(**base)


def test_residual_gate_success_promotion():
    r = residual_promotion_gate(_inp())
    assert r.promoted
    assert r.reason == "promoted"


def test_residual_gate_blocks_missing_m():
    r = residual_promotion_gate(_inp(m_baseline_passed=False))
    assert not r.promoted


def test_residual_gate_blocks_delta_auc_below_threshold():
    r = residual_promotion_gate(_inp(delta_auc=0.02))
    assert not r.promoted


def test_residual_gate_blocks_delta_ece_positive():
    r = residual_promotion_gate(_inp(delta_ece=0.01))
    assert not r.promoted


def test_residual_gate_blocks_nulls_failed():
    r = residual_promotion_gate(_inp(nulls_passed=False))
    assert not r.promoted


def test_residual_gate_blocks_ablations_failed():
    r = residual_promotion_gate(_inp(ablations_passed=False))
    assert not r.promoted


def test_residual_gate_blocks_leakage_detected():
    r = residual_promotion_gate(_inp(leakage_detected=True))
    assert not r.promoted


def test_residual_gate_blocks_artifact_dominance():
    r = residual_promotion_gate(_inp(artifact_dominance=True))
    assert not r.promoted
