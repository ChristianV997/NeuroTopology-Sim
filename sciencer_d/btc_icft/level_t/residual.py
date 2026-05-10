from sciencer_d.btc_icft.schemas import ResidualGateInput, ResidualGateResult


def residual_promotion_gate(inp: ResidualGateInput) -> ResidualGateResult:
    if not inp.m_baseline_passed:
        return ResidualGateResult(False, "blocked: missing M baseline")
    if inp.delta_auc < 0.03:
        return ResidualGateResult(False, "blocked: delta_auc below threshold")
    if inp.delta_ece is not None and inp.delta_ece > 0:
        return ResidualGateResult(False, "blocked: delta_ece must be <= 0")
    if not inp.nulls_passed:
        return ResidualGateResult(False, "blocked: nulls not passed")
    if not inp.ablations_passed:
        return ResidualGateResult(False, "blocked: ablations not passed")
    if inp.leakage_detected:
        return ResidualGateResult(False, "blocked: leakage detected")
    if inp.artifact_dominance:
        return ResidualGateResult(False, "blocked: artifact dominance")
    return ResidualGateResult(True, "promoted")
