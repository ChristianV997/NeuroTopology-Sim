"""Tests for `sim/active_inference.py` -- all offline, no network, no LLM.

Ground-truth pattern: a synthetic objective with a known optimal parameter
region, following the same discipline as this repo's other instrument tests
(e.g. `tests/test_permutation.py`'s pseudoreplication regression case).
"""
from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pytest

from sim.active_inference import (
    ActiveInferenceController,
    _BinBelief,
    search_vortex_noise_threshold,
)


# ── _BinBelief: conjugate normal-normal update math ──────────────────────────

def test_bin_belief_update_moves_mean_toward_observation():
    belief = _BinBelief(mean=0.0, precision=1.0 / 100.0)
    belief.update(observation=5.0, obs_precision=1.0 / 0.1)
    assert 4.0 < belief.mean <= 5.0


def test_bin_belief_update_shrinks_variance():
    belief = _BinBelief(mean=0.0, precision=1.0 / 100.0)
    var_before = belief.variance
    belief.update(observation=1.0, obs_precision=1.0 / 0.1)
    assert belief.variance < var_before


def test_bin_belief_update_matches_hand_computed_conjugate_formula():
    prior_precision = 1.0 / 4.0
    obs_precision = 1.0 / 1.0
    belief = _BinBelief(mean=2.0, precision=prior_precision)
    belief.update(observation=10.0, obs_precision=obs_precision)
    expected_precision = prior_precision + obs_precision
    expected_mean = (prior_precision * 2.0 + obs_precision * 10.0) / expected_precision
    assert belief.precision == pytest.approx(expected_precision)
    assert belief.mean == pytest.approx(expected_mean)


# ── ActiveInferenceController: constructor validation ─────────────────────────

def test_controller_rejects_too_few_bins():
    with pytest.raises(ValueError):
        ActiveInferenceController(param_min=0, param_max=1, n_bins=1)


def test_controller_rejects_degenerate_range():
    with pytest.raises(ValueError):
        ActiveInferenceController(param_min=1, param_max=1, n_bins=5)


# ── ActiveInferenceController: convergence on a known-optimum objective ──────

def test_controller_converges_to_known_optimum():
    """objective(x) = -(x-3)^2 + small noise is maximized (== the preferred
    outcome, 0) exactly at x=3. A working controller's belief-based
    best_estimate() should land close to that known optimum, not at an
    arbitrary bin."""
    rng = np.random.default_rng(1)

    def objective(x: float) -> float:
        return -(x - 3.0) ** 2 + rng.normal(0, 0.05)

    controller = ActiveInferenceController(
        param_min=0, param_max=6, n_bins=25,
        preferred_mean=0.0, preferred_variance=0.1,
        obs_variance=0.05, epistemic_weight=0.3,
    )
    controller.run(objective, n_iterations=60)
    assert controller.best_estimate() == pytest.approx(3.0, abs=0.3)


def test_controller_concentrates_samples_near_known_optimum():
    """A working explore/exploit balance should spend a disproportionate
    share of its later samples near the true optimum, not sample uniformly."""
    rng = np.random.default_rng(2)

    def objective(x: float) -> float:
        return -(x - 3.0) ** 2 + rng.normal(0, 0.05)

    controller = ActiveInferenceController(
        param_min=0, param_max=6, n_bins=25,
        preferred_mean=0.0, preferred_variance=0.1,
        obs_variance=0.05, epistemic_weight=0.3,
    )
    controller.run(objective, n_iterations=60)
    near_optimum = sum(1 for p, _ in controller.history if abs(p - 3.0) < 0.5)
    assert near_optimum > len(controller.history) / 3


def test_controller_explores_multiple_bins_before_settling():
    """Regression test for a real bug found while building this module: an
    earlier version computed risk from each bin's own (epistemic) belief
    variance, which made an unvisited bin's huge prior uncertainty look
    astronomically "risky" against a narrow preference distribution and
    made the controller greedily re-sample the very first bin it tried
    forever, never exploring. A correctly balanced controller must visit
    a reasonable spread of distinct bins early on, not collapse to one."""
    rng = np.random.default_rng(3)

    def objective(x: float) -> float:
        return -(x - 3.0) ** 2 + rng.normal(0, 0.05)

    controller = ActiveInferenceController(
        param_min=0, param_max=6, n_bins=25,
        preferred_mean=0.0, preferred_variance=0.1,
        obs_variance=0.05, epistemic_weight=0.3,
    )
    controller.run(objective, n_iterations=15)
    distinct_bins_visited = len({round(p, 6) for p, _ in controller.history})
    assert distinct_bins_visited >= 8, (
        f"only {distinct_bins_visited} distinct bins visited in 15 iterations "
        "-- controller may have collapsed to greedy exploitation"
    )


# ── search_vortex_noise_threshold: real synthetic-experiment integration ─────

def _reference_crossover_amplitude(target_Qz: float, N: int = 16) -> float:
    """Independent dense-grid reference for the noise_amplitude at which
    `perturbed_vortex`'s mean winding charge crosses `target_Qz`, averaged
    over many seeds per amplitude to smooth out per-draw noise. Computed
    directly from the objective the controller optimizes, not copied from
    any cached/hand-picked number."""
    from core.topology import compute_Qz
    from validation.synthetic import perturbed_vortex

    amps = np.linspace(0.0, 2.5, 40)
    means = []
    for amp in amps:
        vals = [
            float(np.mean(compute_Qz(perturbed_vortex(N=N, noise_amplitude=amp, seed=s))[0]))
            for s in range(15)
        ]
        means.append(np.mean(vals))
    means = np.array(means)
    return float(amps[np.argmin(np.abs(means - target_Qz))])


def test_search_vortex_noise_threshold_converges_near_reference_crossover():
    """The active-inference search must land close to an independently
    computed dense-grid reference for where Qz_mean crosses the target --
    proving the controller actually locates the informative parameter
    region, not an arbitrary one."""
    reference = _reference_crossover_amplitude(target_Qz=0.5, N=16)
    _, estimate = search_vortex_noise_threshold(
        target_Qz=0.5, N=16, n_iterations=40, seed=0,
    )
    assert estimate == pytest.approx(reference, abs=0.5)


def test_search_vortex_noise_threshold_far_from_reference_at_zero_amplitude():
    """Sanity check on the reference/estimate relationship itself: noise_amplitude=0
    always yields Qz=1.0 (see validation/synthetic.py::perturbed_vortex), so a
    target of 0.5 must resolve to a nonzero crossover amplitude -- otherwise the
    reference helper or the search itself would be trivially degenerate."""
    reference = _reference_crossover_amplitude(target_Qz=0.5, N=16)
    assert reference > 0.3


def test_search_vortex_noise_threshold_returns_controller_with_history():
    controller, estimate = search_vortex_noise_threshold(
        target_Qz=0.5, N=16, n_iterations=10, seed=0,
    )
    assert len(controller.history) == 10
    assert controller.param_min <= estimate <= controller.param_max


# ── Scope boundary: never wired into the real-EEG pipeline ───────────────────

def test_active_inference_module_does_not_import_real_eeg_pipeline():
    """Per the project plan's explicit scoping: the active inference
    controller is a simulation-optimization tool for `sim/` /
    `validation/synthetic.py` only, and must never be imported by or import
    from the real-EEG dataset pipeline (`sciencer_d.btc_icft`) or any
    published dataset report path."""
    src_path = Path(__file__).resolve().parent.parent / "sim" / "active_inference.py"
    tree = ast.parse(src_path.read_text())
    imported_modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported_modules.append(node.module)
    assert not any(m.startswith("sciencer_d") for m in imported_modules)
