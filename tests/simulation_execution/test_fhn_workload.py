"""Contract tests for the deterministic FHN workload adapter."""
from __future__ import annotations

from dataclasses import asdict
from pathlib import Path
import sys

import pytest

APP_SRC = Path(__file__).resolve().parents[2] / "apps" / "awareness_studio" / "src"
if str(APP_SRC) not in sys.path:
    sys.path.insert(0, str(APP_SRC))

from sim.pitnn.hodgkin_huxley_ciss import FHNConfig
from tools.simulation_execution.fhn_workload import prepare_spec


@pytest.mark.parametrize(
    "field,value",
    [("duration_s", 1.0), ("dt_s", 0.0), ("input_current", float("nan"))],
)
def test_fhn_preparation_rejects_unbounded_or_nonfinite_parameters(tmp_path: Path, field: str, value: float):
    config = asdict(FHNConfig(duration_s=0.001, dt_s=0.00001))
    config[field] = value
    with pytest.raises(ValueError):
        prepare_spec(
            tmp_path / "spec.json",
            run_id="bounded-test",
            code_commit="revision-test",
            seed=1,
            configuration=config,
        )
    assert not (tmp_path / "spec.json").exists()


def test_fhn_preparation_refuses_spec_overwrite(tmp_path: Path):
    path = tmp_path / "spec.json"
    config = asdict(FHNConfig(duration_s=0.001, dt_s=0.00001))
    prepare_spec(path, run_id="bounded-test", code_commit="revision-test", seed=1, configuration=config)
    with pytest.raises(FileExistsError):
        prepare_spec(path, run_id="bounded-test", code_commit="revision-test", seed=1, configuration=config)
