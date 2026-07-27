import json

import numpy as np

from scripts.analyze_research_campaign import analyze_campaign
from scripts.run_research_campaign import parameter_grid, run_campaign


def test_parameter_grid_shape_and_bounds():
    grid = parameter_grid()
    assert len(grid) == 240
    assert {point.temperature_K for point in grid} == {290.0, 310.0, 320.0}
    assert {point.tau0 for point in grid} == {0.0, 1e-4, 1e-2, 1e-1}
    assert {point.bath for point in grid} == {"markovian", "non_markovian"}


def test_small_campaign_is_finite_and_analyzable(tmp_path):
    summary = run_campaign(tmp_path / "campaign", steps=8, seed=12, backend="numpy",
                           fast_tda=True, fast_ep=True, mcwf_trajectories=2, max_nodes=4)
    assert summary["n_nodes"] == 4
    with np.load(tmp_path / "campaign" / "campaign_arrays.npz") as arrays:
        assert np.all(np.isfinite(arrays["spin_final"]))
        assert np.all(np.isfinite(arrays["density_final"]))
    report = analyze_campaign(tmp_path / "campaign")
    assert report["n_nodes"] == 4
    payload = json.loads((tmp_path / "campaign" / "research_insights_summary.json").read_text())
    assert payload["schema"] == "PITNN.ResearchInsights.v1"


def test_bath_modes_have_expected_backflow(tmp_path):
    run_campaign(tmp_path / "campaign", steps=2, seed=1, backend="numpy",
                 fast_ep=True, mcwf_trajectories=1, max_nodes=20)
    records = [json.loads(line) for line in (tmp_path / "campaign" / "campaign_records.jsonl").read_text().splitlines()]
    markov = [r["bath"]["blp_non_markovianity"] for r in records if r["parameters"]["bath"] == "markovian"]
    colored = [r["bath"]["blp_non_markovianity"] for r in records if r["parameters"]["bath"] == "non_markovian"]
    assert max(markov) == 0.0
    assert max(colored) > 0.0
