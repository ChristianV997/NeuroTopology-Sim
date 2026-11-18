"""Adapter boundary wiring, probe dedupe, and kwargs filtering tests."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import pytest

from experiments.su2_skyrme.adapter import (
    AdapterRunRequest,
    LiveSolverBackend,
    REQUIRED_LORENTZIAN_SYMBOLS,
    REQUIRED_RELAX_SYMBOLS,
    SolverAvailability,
    filter_supported_kwargs,
    probe_solver_availability,
)
from experiments.su2_skyrme.schema import (
    DiscretizationConfig,
    InitialConditionConfig,
    ModelConfig,
    SolverSettings,
)


def _request(*, boundary: str = "periodic") -> AdapterRunRequest:
    return AdapterRunRequest(
        mode="nearest_neighbor_relax",
        discretization=DiscretizationConfig(
            shape=(4, 4, 4),
            spacing=(1.0, 1.0, 1.0),
            boundary=boundary,
            length_unit="dimensionless",
        ),
        initial_condition=InitialConditionConfig(kind="hedgehog", radius=1.0),
        model=ModelConfig(),
        solver=SolverSettings(max_iterations=1),
        seed=0,
    )


def _install_live_mocks(
    monkeypatch: pytest.MonkeyPatch,
    *,
    hedgehog_fn,
    relax_fn,
) -> MagicMock:
    monkeypatch.setattr(
        "experiments.su2_skyrme.adapter.probe_solver_availability",
        lambda: SolverAvailability(
            import_status="available",
            module_path="field_theory.su2",
            public_symbols=REQUIRED_RELAX_SYMBOLS,
            missing_symbols=(),
            notes="mocked",
            dependency_blocker=None,
        ),
    )
    import sys

    fake_su2 = MagicMock()
    fake_su2.hedgehog = hedgehog_fn
    fake_su2.vacuum = MagicMock()
    fake_nn = MagicMock()
    fake_nn.relax_skyrme_field_nearest_neighbor = relax_fn
    monkeypatch.setitem(sys.modules, "field_theory", MagicMock())
    monkeypatch.setitem(sys.modules, "field_theory.su2", fake_su2)
    monkeypatch.setitem(sys.modules, "field_theory.su2.nearest_neighbor", fake_nn)
    return fake_nn


def test_live_hedgehog_forwards_boundary_when_supported(monkeypatch: pytest.MonkeyPatch):
    """When hedgehog accepts boundary, the adapter must forward it."""
    import numpy as np

    captured: dict[str, Any] = {}
    fake_field = SimpleNamespace(
        components=np.zeros((4, 4, 4, 4), dtype=np.float64),
        spacing=(1.0, 1.0, 1.0),
        boundary="periodic",
        length_unit="dimensionless",
    )

    def fake_hedgehog(shape, *, radius, spacing, boundary, length_unit):
        captured["boundary"] = boundary
        captured["shape"] = shape
        return fake_field

    fake_result = SimpleNamespace(
        energy_history=[1.0],
        topological_charge_history=[0.5],
        iterations=1,
        raw_gradient_norm=1.0,
        continuum_l2_residual=1.0,
        active_l2_measure=64.0,
        active_l2_rms_residual=1.0,
        stationarity_status="not_established",
        minimum_certified=False,
        cell_volume=1.0,
        active_site_count=64,
        termination="iteration_limit",
        field=fake_field,
    )
    fake_nn = _install_live_mocks(
        monkeypatch,
        hedgehog_fn=fake_hedgehog,
        relax_fn=MagicMock(return_value=fake_result),
    )
    backend = LiveSolverBackend()
    payload = backend.run(_request(boundary="periodic"))
    assert captured["boundary"] == "periodic"
    assert payload.status == "iteration_limit"
    fake_nn.relax_skyrme_field_nearest_neighbor.assert_called_once()


def test_live_hedgehog_drops_boundary_on_foundation_signature(
    monkeypatch: pytest.MonkeyPatch,
):
    """origin/main hedgehog has no boundary kwarg — adapter must not pass it."""
    import numpy as np

    captured: dict[str, Any] = {}
    fake_field = SimpleNamespace(
        components=np.zeros((4, 4, 4, 4), dtype=np.float64),
        spacing=(1.0, 1.0, 1.0),
        boundary="fixed_vacuum",
        length_unit="dimensionless",
    )

    def foundation_hedgehog(shape, *, radius, spacing, length_unit):
        captured["keys"] = sorted(("radius", "spacing", "length_unit"))
        captured["radius"] = radius
        return fake_field

    fake_result = SimpleNamespace(
        energy_history=[1.0],
        topological_charge_history=[0.5],
        iterations=1,
        stationarity_status="not_established",
        minimum_certified=False,
        termination="iteration_limit",
        field=fake_field,
    )

    def foundation_relax(
        field,
        *,
        f_pi,
        e,
        max_iterations,
        initial_step,
        gradient_tolerance,
        max_backtracks,
    ):
        captured["relax_kwargs"] = {
            "f_pi": f_pi,
            "e": e,
            "max_iterations": max_iterations,
        }
        return fake_result

    _install_live_mocks(
        monkeypatch,
        hedgehog_fn=foundation_hedgehog,
        relax_fn=foundation_relax,
    )
    backend = LiveSolverBackend()
    payload = backend.run(_request(boundary="periodic"))
    assert payload.status == "iteration_limit"
    assert "boundary" not in captured
    assert "raw_gradient_norm" not in payload.diagnostics
    assert payload.diagnostics["final_energy_total"] == 1.0


def test_filter_supported_kwargs_var_keyword_passthrough():
    def flexible(**kwargs):
        return kwargs

    assert filter_supported_kwargs(flexible, {"a": 1, "b": 2}) == {"a": 1, "b": 2}


def test_probe_missing_symbols_are_unique():
    availability = probe_solver_availability()
    assert len(availability.missing_symbols) == len(set(availability.missing_symbols))
    assert len(availability.public_symbols) == len(set(availability.public_symbols))
    # Overlap between required symbol lists must not produce duplicates on import miss.
    combined = REQUIRED_RELAX_SYMBOLS + REQUIRED_LORENTZIAN_SYMBOLS
    assert len(combined) > len(set(combined))
    if availability.import_status == "unavailable":
        assert set(availability.missing_symbols) == set(combined)
