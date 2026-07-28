import json

import numpy as np
import pytest

from theory_campaign.core import CampaignConfig, dimensionless_groups, evaluate_lattice_point, exact_sign_flip_pvalue
from theory_campaign.memory import MemoryConfig, simulate_memory_mode


def test_dimensionless_groups_are_reproducible():
    config = CampaignConfig(spacing_nm=4.0, correlation_length_nm=8.0, disorder_sigma_nm=0.2)
    groups = dimensionless_groups(config, coherent_coupling_s=2.0e8)
    assert groups["rho_spacing_to_correlation"] == pytest.approx(0.5)
    assert groups["delta_disorder_to_spacing"] == pytest.approx(0.05)
    assert all(np.isfinite(list(groups.values())))


def test_exact_sign_flip_is_deterministic_and_two_sided():
    values = np.array([0.4, 0.3, 0.2, 0.1])
    assert exact_sign_flip_pvalue(values) == exact_sign_flip_pvalue(-values)
    assert 0.0 < exact_sign_flip_pvalue(values) <= 1.0


def test_lattice_point_contains_matched_nulls():
    result = evaluate_lattice_point(CampaignConfig(n_layers=1, disorder_seed=7, dense_max_dimension=32))
    assert {record["null"] for record in result["records"]} == {
        "candidate", "independent_bath", "short_correlation_null"
    }
    assert all(record["solver"]["converged"] for record in result["records"])
    assert np.isfinite(result["primary_contrast"]["value"])


def test_memory_output_is_finite_and_bounded():
    result = simulate_memory_mode(MemoryConfig(memory_time_s=1e-10, duration_s=1e-8, steps=200))
    assert result["observables"]["initial_population"] == pytest.approx(1.0)
    assert all(np.isfinite(result[key]).all() for key in ("times_s", "coherence_real", "coherence_imag", "population"))
    assert min(result["population"]) >= 0.0


def test_short_memory_approaches_matched_markov_reference():
    short = simulate_memory_mode(MemoryConfig(memory_time_s=1e-13, duration_s=1e-9, steps=3000))
    finer = simulate_memory_mode(MemoryConfig(memory_time_s=1e-13, duration_s=1e-9, steps=6000))
    assert short["observables"]["final_population"] == pytest.approx(
        finer["observables"]["final_population"], rel=2e-2, abs=1e-8
    )


def test_json_serialization_has_no_nonfinite_values(tmp_path):
    result = simulate_memory_mode(MemoryConfig(memory_time_s=1e-10, duration_s=1e-8, steps=40))
    path = tmp_path / "memory.json"
    path.write_text(json.dumps(result, allow_nan=False), encoding="utf-8")
    assert path.stat().st_size > 0
