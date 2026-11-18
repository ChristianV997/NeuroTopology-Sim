"""Optional live-path smoke when field_theory.su2 is importable.

On the antigravity base tip this module is absent and tests skip. Overlay
verification: ``PYTHONPATH=/path/to/main/tree pytest ...`` (or merge main).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from experiments.su2_skyrme.adapter import LiveSolverBackend, probe_solver_availability
from experiments.su2_skyrme.result_contract import validate_result_dict
from experiments.su2_skyrme.runner import run_experiment
from experiments.su2_skyrme.schema import load_experiment_config
from pathlib import Path

CONFIG_DIR = Path(__file__).resolve().parents[3] / "experiments" / "su2_skyrme" / "configs"


@pytest.fixture(scope="module")
def live_availability():
    return probe_solver_availability()


def test_live_relax_when_importable(live_availability):
    if live_availability.import_status != "available":
        pytest.skip(f"solver unavailable: {live_availability.notes}")
    config = load_experiment_config(CONFIG_DIR / "smoke_relax.json")
    backend = LiveSolverBackend()
    fixed = datetime(2026, 1, 1, tzinfo=timezone.utc)
    first = run_experiment(config, backend=backend, created_at=fixed)
    second = run_experiment(config, backend=backend, created_at=fixed)
    assert first.status in {"converged", "iteration_limit", "completed", "line_search_stalled"}
    assert first.solver_api_status == "available"
    assert first.solver_backend == "field_theory.su2"
    assert first.result_id == second.result_id
    assert first.to_json() == second.to_json()
    assert validate_result_dict(first.to_dict()) == []
    assert first.claim_tags["consciousness_interpretation"] == "forbidden"
    assert first.claim_tags["scientific_status"] == "NOT_ASSESSED"
    names = {d.name for d in first.diagnostics}
    assert "final_energy_total" in names
    assert "consciousness_metric" in names
    # Enriched residual fields may be absent on origin/main foundation — never invent.
    energy = next(d for d in first.diagnostics if d.name == "final_energy_total")
    assert energy.evidence == "computed"
    assert energy.availability == "present"


def test_live_lorentzian_unavailable_path(live_availability):
    if live_availability.import_status != "available":
        pytest.skip(f"solver unavailable: {live_availability.notes}")
    if "evolve_lorentzian_skyrme" in live_availability.public_symbols:
        pytest.skip("lorentzian present; unavailable-path not exercised")
    config = load_experiment_config(CONFIG_DIR / "smoke_lorentzian.json")
    result = run_experiment(config, backend=LiveSolverBackend())
    assert result.status == "solver_unavailable"
    assert result.failure_message
    assert "468" in (result.failure_message or "") or "lorentzian" in (
        result.failure_message or ""
    ).lower()
