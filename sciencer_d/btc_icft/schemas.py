from dataclasses import dataclass


@dataclass(frozen=True)
class MBaselineResult:
    passed: bool
    reason: str = ""


@dataclass(frozen=True)
class ResidualGateInput:
    m_baseline_passed: bool
    delta_auc: float
    delta_ece: float | None
    nulls_passed: bool
    ablations_passed: bool
    leakage_detected: bool
    artifact_dominance: bool


@dataclass(frozen=True)
class ResidualGateResult:
    promoted: bool
    reason: str
