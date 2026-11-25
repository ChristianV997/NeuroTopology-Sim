"""Deterministic small-grid tests for the bounded FTA mode-follow probe."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from experiments.su2_field_transition_atlas.mode_probe import (
    ModeProbeConfig,
    finite_difference_directional_curvature,
    run_mode_probe,
    write_result,
)
from field_theory.su2 import SU2GridField
from field_theory.su2.nearest_neighbor import _active_mask


def test_fta_checkerboard_declared_outperforms_orthogonal_control(tmp_path: Path):
    config = ModeProbeConfig(
        oracle="periodic_checkerboard",
        shape=(8, 4, 4),
        spacing=(1.0, 1.0, 1.0),
        step_sizes=(0.02, 0.05),
        n_steps=6,
        seed=0,
    )
    result = run_mode_probe(config)

    assert result.classification == "bounded_mode_following_fd_curvature_probe"
    assert "finite_difference" in result.curvature_method
    assert "unavailable_on_base" in result.hessian_status
    assert result.initial_gradient_norm <= config.gradient_stationarity_tol
    assert result.declared_directional_curvature0 < -0.5
    assert abs(result.records["declared_control_inner"]) < 1.0e-12
    assert result.declared_predicted_larger_drop is True
    assert (
        result.control_directional_curvature0
        > result.declared_directional_curvature0
    )

    out = tmp_path / "fta.json"
    write_result(result, out)
    payload = json.loads(out.read_text())
    assert payload["schema_version"] == config.schema_version
    joined = " ".join(payload["limitations"]).lower()
    assert "not a converged transition path" in joined
    assert "not a metastable-barrier" in joined
    for key in ("0.02", "0.05"):
        block = payload["records"]["by_step_size"][key]
        assert block["declared_energy_drop"] > block["control_energy_drop"]
        assert "wall_seconds" in block["resource_declared"]
        assert "ru_maxrss_kib" in block["resource_declared"]
        row0 = block["declared"][0]
        assert "fd_directional_curvature" in row0
        assert "gradient_residual_norm" in row0
        assert "mode_overlap_with_initial" in row0


def test_fta_anisotropic_spacing_stationary_and_finite():
    config = ModeProbeConfig(
        oracle="periodic_checkerboard",
        shape=(8, 4, 4),
        spacing=(0.5, 1.0, 1.5),
        step_sizes=(0.03,),
        n_steps=4,
        seed=1,
    )
    result = run_mode_probe(config)
    assert result.initial_gradient_norm <= 1.0e-10
    assert np.isfinite(result.declared_directional_curvature0)
    assert np.isfinite(result.control_directional_curvature0)
    series = result.records["by_step_size"]["0.03"]["declared"]
    assert all(np.isfinite(row["energy"]) for row in series)
    assert abs(series[0]["mode_overlap_with_initial"] - 1.0) < 1.0e-12


def test_finite_difference_directional_curvature_matches_named_contract():
    values = np.zeros((8, 4, 4, 4), dtype=np.float64)
    pattern = ((-1.0) ** np.arange(8, dtype=np.float64))[:, None, None]
    values[..., 0] = np.broadcast_to(pattern, (8, 4, 4))
    field = SU2GridField(values, spacing=(1.0, 1.0, 1.0), boundary="periodic")
    active = _active_mask(field)
    direction = -values * values[..., 1, None]
    direction = direction.copy()
    direction[..., 1] += 1.0
    direction[~active] = 0.0
    direction /= np.linalg.norm(direction[active])
    kappa = finite_difference_directional_curvature(
        field, direction, f_pi=1.0, e=1.0, probe_step=5.0e-3
    )
    assert kappa < -0.5
