"""Focused unit and numerical-consistency tests for sim.stochastic_escape_benchmark."""

from __future__ import annotations

import json
import pytest

from runs.run_record import RunRecordV1
from sim.stochastic_escape_benchmark import (
    EscapeBenchmarkConfig,
    build_escape_run_record,
    kramers_asymptotic_summary,
    run_stochastic_escape_benchmark,
    simulate_censored_escape,
    solve_survival_pde,
)


def test_config_validation_rejects_invalid_domain():
    with pytest.raises(ValueError):
        EscapeBenchmarkConfig(r=-0.1).validate()
    with pytest.raises(ValueError):
        EscapeBenchmarkConfig(D=0.0).validate()
    # q_min >= saddle (-sqrt(0.25) = -0.5) must fail closed
    with pytest.raises(ValueError):
        EscapeBenchmarkConfig(r=0.25, q_min=-0.4).validate()


def test_kramers_asymptotic_gating():
    # Non-asymptotic regime: r=0.25 -> delta_V = 1/6 ~ 0.1667, D=0.05 -> ratio ~ 3.33 < 6.0
    low_barrier = kramers_asymptotic_summary(r=0.25, D=0.05)
    assert low_barrier["asymptotic_valid"] is False
    assert low_barrier["kramers_rate"] is None
    assert low_barrier["kramers_mfpt"] is None

    # Asymptotic regime: r=0.25 -> delta_V = 1/6, D=0.02 -> ratio ~ 8.33 >= 6.0
    deep_barrier = kramers_asymptotic_summary(r=0.25, D=0.02)
    assert deep_barrier["asymptotic_valid"] is True
    assert deep_barrier["kramers_rate"] > 0.0
    assert deep_barrier["kramers_mfpt"] > 0.0


def test_per_trial_seed_determinism_and_censoring():
    r1 = simulate_censored_escape(r=0.25, D=0.04, q0=0.5, T=8.0, q_min=-1.25, q_max=2.0, n_trials=200, base_seed=42)
    r2 = simulate_censored_escape(r=0.25, D=0.04, q0=0.5, T=8.0, q_min=-1.25, q_max=2.0, n_trials=200, base_seed=42)
    assert r1["survival_T"] == r2["survival_T"]
    assert r1["rmst_T"] == r2["rmst_T"]
    assert 0.0 <= r1["censored_fraction"] <= 1.0
    assert pytest.approx(1.0) == r1["censored_fraction"] + r1["escaped_fraction"]


def test_pde_oracle_matches_censored_mc_and_sensitivity():
    cfg = EscapeBenchmarkConfig(r=0.25, D=0.04, q0=0.50, T=12.0, q_min=-1.25, q_max=2.0, dt_mc=0.005, n_trials=1200)
    res = run_stochastic_escape_benchmark(cfg, run_sensitivity=True)

    pde = res["pde_oracle"]
    mc = res["mc_censored"]
    compat = res["pde_vs_mc_compatibility"]
    sens = res["sensitivity"]

    assert 0.0 < pde["survival_T"] < 1.0
    assert 0.0 < pde["rmst_T"] < cfg.T
    # Compatible finite-horizon survival and RMST agree within 3 MC standard errors
    assert compat["survival_z_score"] < 3.0
    assert compat["rmst_z_score"] < 3.0
    # Timestep and upper/lower domain sensitivity remain small
    assert sens["pde_dt_halved_survival_diff"] < 1e-3
    assert sens["pde_qmax_extended_survival_diff"] < 1e-3

    # Check RunRecordV1 packaging & JSON round-trip
    rec = build_escape_run_record(res, run_id="test_escape_01")
    loaded = RunRecordV1.from_dict(json.loads(json.dumps(rec.to_dict())))
    assert loaded.run_kind == "benchmark"
    assert loaded.spec_id == "stochastic_escape_normal_form_v1"
    assert loaded.metrics["pde_rmst_T"] == pde["rmst_T"]
