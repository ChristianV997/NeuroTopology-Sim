"""Config schema validation tests for the SU(2)/Skyrme experiment layer."""

from __future__ import annotations

import copy

import pytest

from experiments.su2_skyrme.schema import (
    ExperimentConfigError,
    validate_experiment_config,
)


def _base_relax() -> dict:
    return {
        "schema_version": "0.1.0",
        "experiment_id": "unit-relax",
        "mode": "nearest_neighbor_relax",
        "seed": 0,
        "discretization": {
            "shape": [4, 4, 4],
            "spacing": [1.0, 1.0, 1.0],
            "boundary": "fixed_vacuum",
            "length_unit": "dimensionless",
        },
        "initial_condition": {"kind": "hedgehog", "radius": 1.0},
        "model": {"f_pi": 1.0, "e": 1.0, "damping": 0.0},
        "solver": {
            "max_iterations": 2,
            "initial_step": 1.0e-3,
            "gradient_tolerance": 1.0e-7,
            "max_backtracks": 4,
        },
    }


def test_valid_relax_config():
    cfg = validate_experiment_config(_base_relax())
    assert cfg.mode == "nearest_neighbor_relax"
    assert cfg.discretization.shape == (4, 4, 4)


def test_rejects_unknown_mode():
    raw = _base_relax()
    raw["mode"] = "consciousness_detector"
    with pytest.raises(ExperimentConfigError, match="mode must be one of"):
        validate_experiment_config(raw)


def test_rejects_unavailable_top_level_field():
    raw = _base_relax()
    raw["fixed_mask"] = True
    with pytest.raises(ExperimentConfigError, match="unavailable"):
        validate_experiment_config(raw)


def test_rejects_multi_hedgehog_ic():
    raw = _base_relax()
    raw["initial_condition"] = {"kind": "multi_hedgehog"}
    with pytest.raises(ExperimentConfigError, match="initial_condition.kind"):
        validate_experiment_config(raw)


def test_sweep_requires_axes_for_sweep_mode():
    raw = _base_relax()
    raw["mode"] = "nearest_neighbor_sweep"
    with pytest.raises(ExperimentConfigError, match="requires a sweep block"):
        validate_experiment_config(raw)


def test_relax_rejects_embedded_sweep():
    raw = _base_relax()
    raw["sweep"] = {"axes": {"f_pi": [1.0], "e": [1.0], "max_iterations": [1], "initial_step": [0.001]}}
    with pytest.raises(ExperimentConfigError, match="rejects sweep"):
        validate_experiment_config(raw)


def test_sweep_cap_and_duplicate_axis():
    raw = _base_relax()
    raw["mode"] = "nearest_neighbor_sweep"
    raw["sweep"] = {
        "axes": {
            "f_pi": [1.0],
            "e": [1.0, 1.0],
            "max_iterations": [1],
            "initial_step": [0.001],
        }
    }
    with pytest.raises(ExperimentConfigError, match="duplicates"):
        validate_experiment_config(raw)


def test_lorentzian_requires_dt_steps():
    raw = _base_relax()
    raw["mode"] = "lorentzian_evolve"
    with pytest.raises(ExperimentConfigError, match="dt and solver.steps"):
        validate_experiment_config(raw)


def test_lorentzian_ok():
    raw = _base_relax()
    raw["mode"] = "lorentzian_evolve"
    raw["solver"]["dt"] = 0.01
    raw["solver"]["steps"] = 2
    cfg = validate_experiment_config(raw)
    assert cfg.solver.dt == 0.01
    assert cfg.solver.save_every == 1


def test_oversized_grid_rejected():
    raw = _base_relax()
    raw["discretization"]["shape"] = [20, 20, 20]
    with pytest.raises(ExperimentConfigError, match="node_count"):
        validate_experiment_config(raw)


def test_unsupported_schema_version():
    raw = _base_relax()
    raw["schema_version"] = "9.9.9"
    with pytest.raises(ExperimentConfigError, match="schema_version"):
        validate_experiment_config(raw)


def test_damping_unavailable_on_relax():
    raw = _base_relax()
    raw["model"]["damping"] = 0.1
    with pytest.raises(ExperimentConfigError, match="damping"):
        validate_experiment_config(raw)


def test_to_dict_roundtrip_keys():
    cfg = validate_experiment_config(_base_relax())
    payload = cfg.to_dict()
    assert "unavailable_fields" in payload
    assert "claim_guardrail" in payload
    again = validate_experiment_config(
        {k: v for k, v in payload.items() if k != "unavailable_fields"}
    )
    assert again.experiment_id == cfg.experiment_id
    # mutate copy must not affect frozen-ish validation path
    mutated = copy.deepcopy(payload)
    mutated["seed"] = 3
    other = validate_experiment_config(
        {k: v for k, v in mutated.items() if k != "unavailable_fields"}
    )
    assert other.seed == 3
