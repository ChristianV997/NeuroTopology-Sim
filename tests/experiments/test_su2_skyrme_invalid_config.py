"""Invalid-config rejection tests for the SU(2)/Skyrme experiment schema."""

from __future__ import annotations

import copy
from pathlib import Path

import pytest

from experiments.su2_skyrme.schema import ConfigError, load_config, validate_config

_REPO = Path(__file__).resolve().parents[2]
_CONFIGS = _REPO / "experiments" / "su2_skyrme" / "configs"


def _valid_raw() -> dict:
    return {
        "schema_version": "su2_skyrme.experiment.config.v1",
        "experiment_id": "invalid_config_base",
        "mode": "single",
        "seed": 1,
        "discretization": {
            "shape": [4, 4, 4],
            "spacing": [1.0, 1.0, 1.0],
            "length_unit": "dimensionless",
        },
        "boundary_conditions": "fixed_vacuum",
        "initial_condition": {"kind": "vacuum"},
        "model": {"f_pi": 1.0, "e": 1.0},
        "solver": {"backend": "auto", "max_iterations": 2},
    }


def test_smoke_configs_load():
    load_config(_CONFIGS / "smoke_single.yaml")
    load_config(_CONFIGS / "smoke_single.json")
    load_config(_CONFIGS / "smoke_grid.yaml")


@pytest.mark.parametrize(
    "mutator,match",
    [
        (lambda d: d.update({"schema_version": "nope"}), "schema_version"),
        (lambda d: d.update({"mode": "batch"}), "mode"),
        (lambda d: d.update({"seed": -1}), "seed"),
        (lambda d: d["discretization"].update({"shape": [1, 4, 4]}), "shape"),
        (lambda d: d["discretization"].update({"spacing": [1.0, -1.0, 1.0]}), "spacing"),
        (lambda d: d.update({"boundary_conditions": "open"}), "boundary_conditions"),
        (lambda d: d["initial_condition"].update({"kind": "random"}), "initial_condition.kind"),
        (lambda d: d["model"].update({"f_pi": 0.0}), "f_pi"),
        (lambda d: d["solver"].update({"backend": "magic"}), "backend"),
        (lambda d: d["solver"].update({"max_iterations": 0}), "max_iterations"),
    ],
)
def test_invalid_fields_raise_config_error(mutator, match):
    raw = _valid_raw()
    mutator(raw)
    with pytest.raises(ConfigError, match=match):
        validate_config(raw)


def test_grid_mode_requires_axes():
    raw = _valid_raw()
    raw["mode"] = "grid"
    with pytest.raises(ConfigError, match="grid"):
        validate_config(raw)


def test_grid_point_cap_enforced():
    raw = _valid_raw()
    raw["mode"] = "grid"
    raw["grid"] = {
        "f_pi_values": [float(i + 1) for i in range(20)],
        "e_values": [float(i + 1) for i in range(20)],
    }
    with pytest.raises(ConfigError, match="maximum"):
        validate_config(raw)


def test_missing_experiment_id_rejected():
    raw = _valid_raw()
    del raw["experiment_id"]
    with pytest.raises(ConfigError, match="experiment_id"):
        validate_config(raw)


def test_deepcopy_baseline_still_valid():
    assert validate_config(copy.deepcopy(_valid_raw())).experiment_id == "invalid_config_base"
