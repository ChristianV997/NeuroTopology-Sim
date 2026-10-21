"""Fail-closed contracts and no-label-inference guardrails (synthetic only)."""
from __future__ import annotations

import math

import numpy as np
import pytest

from sim.nuisance_scenarios.config import NuisanceScenarioConfig
from sim.nuisance_scenarios.factory import NuisanceScenarioFactory
from sim.nuisance_scenarios.snr_mixer import mix_at_target_snr


def test_conflicting_alias_and_canonical_fail_closed_in_constructor() -> None:
    """Regression: constructor must not silently prefer alias over canonical."""
    with pytest.raises(ValueError, match="conflict"):
        NuisanceScenarioConfig(noise_exponent=1.0, chi=2.0)


def test_conflicting_alias_and_canonical_fail_closed_in_from_dict() -> None:
    """Regression: from_dict must not silently prefer canonical over alias."""
    with pytest.raises(ValueError, match="conflict"):
        NuisanceScenarioConfig.from_dict(
            {
                "noise_exponent": 1.0,
                "chi": 2.0,
                "coordinate_jitter_std": 1.0,
                "jitter_std": 3.0,
                "seed": 7,
            }
        )


def test_matching_alias_and_canonical_accepted() -> None:
    """Equal alias/canonical pairs are allowed and round-trip cleanly."""
    cfg = NuisanceScenarioConfig(noise_exponent=1.5, chi=1.5, jitter_std=2.0, coordinate_jitter_std=2.0)
    assert cfg.chi == pytest.approx(1.5)
    assert cfg.jitter_std == pytest.approx(2.0)
    restored = NuisanceScenarioConfig.from_dict(cfg.to_dict())
    assert restored.chi == pytest.approx(1.5)
    assert restored.jitter_std == pytest.approx(2.0)


def test_config_rejects_non_finite_and_invalid_sampling_rate() -> None:
    with pytest.raises(ValueError, match="sfreq_hz"):
        NuisanceScenarioConfig(sfreq_hz=0.0)
    with pytest.raises(ValueError, match="sfreq_hz"):
        NuisanceScenarioConfig(sfreq_hz=float("nan"))
    with pytest.raises(ValueError, match="sfreq_hz"):
        NuisanceScenarioConfig(sampling_rate_hz=-5.0)
    with pytest.raises(ValueError, match="target_snr_db"):
        NuisanceScenarioConfig(target_snr_db=float("inf"))
    with pytest.raises(ValueError, match="target_snr_db"):
        NuisanceScenarioConfig(target_snr_db=float("nan"))


def test_config_rejects_duration_yielding_too_few_samples() -> None:
    """n_samples < 4 is invalid for colored-noise synthesis — fail at config time."""
    with pytest.raises(ValueError, match="n_samples"):
        NuisanceScenarioConfig(duration_s=0.01, sfreq_hz=100.0)


def test_mixer_rejects_non_finite_target_snr() -> None:
    clean = np.ones((2, 64))
    noise = np.ones((2, 64))
    with pytest.raises(ValueError, match="target_snr_db"):
        mix_at_target_snr(signal=clean, noise=noise, target_snr_db=float("nan"))
    with pytest.raises(ValueError, match="target_snr_db"):
        mix_at_target_snr(signal=clean, noise=noise, target_snr_db=float("-inf"))


def test_factory_never_infers_condition_labels_from_nuisance() -> None:
    """Generated fixtures must not invent class/condition labels from nuisance params.

    Operating-characteristic validity is not claimed from synthetic fixtures;
    summary payloads must stay free of inferred PASS/FAIL/ROC label fields.
    """
    cfg = NuisanceScenarioConfig(
        chi=1.0,
        target_snr_db=-6.0,
        jitter_std=1.5,
        seed=11,
        n_channels=4,
        duration_s=0.5,
        sampling_rate_hz=200.0,
        metadata={"note": "caller-supplied tag only"},
    )
    res = NuisanceScenarioFactory.generate(cfg, coordinates="synthetic_sphere")
    summary = res.summary_dict()
    forbidden = {
        "label",
        "labels",
        "class_label",
        "condition_label",
        "y_true",
        "y_pred",
        "roc",
        "auc",
        "pass_fail",
        "verdict",
        "detected",
    }
    flat_keys = set(summary.keys()) | set(summary["diagnostics"].keys()) | set(summary["config"].keys())
    assert forbidden.isdisjoint(flat_keys)
    assert summary["diagnostics"]["status"] == "HOLD / SYNTHETIC_ONLY"
    # Caller metadata is preserved verbatim — never rewritten into a condition label.
    assert res.config.metadata == {"note": "caller-supplied tag only"}
    assert not any(k in res.config.metadata for k in ("label", "class", "condition"))
    assert math.isfinite(res.diagnostics.realized_snr_db)
