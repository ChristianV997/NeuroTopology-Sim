"""Live diagnostic key / evidence-tag contract (skips without live solver)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from experiments.su2_skyrme.adapter import StubSolverBackend, probe_solver_availability
from experiments.su2_skyrme.result_contract import validate_result_dict
from experiments.su2_skyrme.runner import run_experiment
from experiments.su2_skyrme.schema import load_experiment_config


FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
CONFIG_DIR = Path(__file__).resolve().parents[3] / "experiments" / "su2_skyrme" / "configs"
_LIVE = probe_solver_availability()


def _load_fixture() -> dict:
    return json.loads(
        (FIXTURE_DIR / "expected_relax_diagnostics.json").read_text(encoding="utf-8")
    )


def test_stub_diagnostics_match_fixture_keys():
    """Stub path always validates the full fixture key / tag contract."""
    fixture = _load_fixture()
    config = load_experiment_config(CONFIG_DIR / "smoke_relax.json")
    result = run_experiment(config, backend=StubSolverBackend(), allow_stub=True)
    by_name = {d.name: d for d in result.diagnostics}
    for name in fixture["required_diagnostic_names"]:
        assert name in by_name, f"missing diagnostic {name}"
        assert by_name[name].units, f"{name} must carry units"
    for name, evidence in fixture["evidence_by_name"].items():
        assert by_name[name].evidence == evidence
    numeric_names = [
        n
        for n in fixture["required_diagnostic_names"]
        if n not in fixture["evidence_by_name"]
    ]
    for name in numeric_names:
        assert by_name[name].evidence == fixture["stub_backend_evidence"]
    assert validate_result_dict(result.to_dict()) == []


@pytest.mark.skipif(
    _LIVE.import_status != "available",
    reason="field_theory.su2 live import unavailable on this tree",
)
def test_live_diagnostics_match_fixture_keys_and_evidence():
    fixture = _load_fixture()
    config = load_experiment_config(CONFIG_DIR / "smoke_relax.json")
    result = run_experiment(config, allow_stub=False)
    assert result.solver_api_status == "available"
    by_name = {d.name: d for d in result.diagnostics}
    # Core contract always required on live path (main foundation + enriched).
    for name in fixture["core_diagnostic_names"]:
        assert name in by_name, f"missing live core diagnostic {name}"
        assert "units" in by_name[name].to_dict()
    for name, evidence in fixture["evidence_by_name"].items():
        assert by_name[name].evidence == evidence
    # Enriched residual fields are optional on origin/main; when present they
    # must be computed + present (never fabricated as assumed).
    for name in fixture["enriched_diagnostic_names"]:
        if name not in by_name:
            continue
        record = by_name[name]
        if record.availability == "present":
            assert record.evidence == fixture["live_backend_evidence"]
    for name in fixture["core_diagnostic_names"]:
        if name in fixture["evidence_by_name"]:
            continue
        if by_name[name].availability == "present":
            assert by_name[name].evidence == fixture["live_backend_evidence"]
    assert validate_result_dict(result.to_dict()) == []
