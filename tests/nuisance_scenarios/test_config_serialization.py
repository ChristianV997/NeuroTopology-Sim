"""Config serialization / alias replay contracts (synthetic only)."""
from __future__ import annotations

import json

import numpy as np
import pytest

from sim.nuisance_scenarios.config import NuisanceScenarioConfig
from sim.nuisance_scenarios.factory import NuisanceScenarioFactory


def test_from_dict_preserves_alias_only_payload() -> None:
    """Regression: alias keys must not be dropped before construction.

    Previously ``from_dict`` popped ``chi`` / ``jitter_std`` / ``sampling_rate_hz``
    without mapping them, so alias-only JSON silently fell back to defaults
    (e.g. chi=1.0 instead of 1.5), breaking serialization replay.
    """
    payload = {
        "chi": 1.5,
        "target_snr_db": -3.0,
        "jitter_std": 2.5,
        "jitter_units": "cm",
        "sampling_rate_hz": 100.0,
        "duration_s": 1.0,
        "n_channels": 3,
        "seed": 99,
        "renormalize_to_sphere": True,
        "scenario_id": "alias-replay",
        "metadata": {"source": "unit-test"},
    }
    cfg = NuisanceScenarioConfig.from_dict(payload)
    assert cfg.chi == pytest.approx(1.5)
    assert cfg.noise_exponent == pytest.approx(1.5)
    assert cfg.jitter_std == pytest.approx(2.5)
    assert cfg.coordinate_jitter_std == pytest.approx(2.5)
    assert cfg.jitter_units == "cm"
    assert cfg.sampling_rate_hz == pytest.approx(100.0)
    assert cfg.sfreq_hz == pytest.approx(100.0)
    assert cfg.renormalize_to_sphere is True
    assert cfg.metadata["source"] == "unit-test"


def test_to_dict_from_dict_roundtrip_preserves_generation() -> None:
    """Full to_dict → JSON → from_dict must replay bit-identical factory output."""
    cfg = NuisanceScenarioConfig(
        chi=1.7,
        target_snr_db=4.0,
        jitter_std=1.25,
        jitter_units="mm",
        seed=4242,
        n_channels=4,
        duration_s=0.5,
        sampling_rate_hz=200.0,
    )
    blob = json.dumps(cfg.to_dict())
    restored = NuisanceScenarioConfig.from_dict(json.loads(blob))
    assert restored.chi == pytest.approx(cfg.chi)
    assert restored.jitter_std == pytest.approx(cfg.jitter_std)
    assert restored.sampling_rate_hz == pytest.approx(cfg.sampling_rate_hz)

    a = NuisanceScenarioFactory.generate(cfg, coordinates="synthetic_sphere")
    b = NuisanceScenarioFactory.generate(restored, coordinates="synthetic_sphere")
    np.testing.assert_array_equal(a.noisy_signal, b.noisy_signal)
    np.testing.assert_array_equal(a.jittered_coordinates, b.jittered_coordinates)
    assert a.diagnostics.status == "HOLD / SYNTHETIC_ONLY"
    assert b.diagnostics.status == "HOLD / SYNTHETIC_ONLY"


def test_unavailable_spectral_fit_serializes_as_strict_json() -> None:
    """An unavailable low-frequency fit must use JSON null, not NaN."""
    cfg = NuisanceScenarioConfig(
        sfreq_hz=5.0,
        duration_s=1.6,
        n_channels=2,
    )
    result = NuisanceScenarioFactory.generate(cfg)

    def reject_nonstandard_constant(value: str) -> None:
        raise ValueError(f"non-standard JSON constant: {value}")

    payload = json.loads(result.to_json(), parse_constant=reject_nonstandard_constant)
    assert payload["diagnostics"]["estimated_chi"] is None
    assert payload["diagnostics"]["chi_fit_r2"] is None


def test_module_has_no_network_or_remote_data_imports() -> None:
    """Factory package must not silently acquire network or remote-data clients."""
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[2] / "sim" / "nuisance_scenarios"
    banned = {
        "urllib",
        "urllib.request",
        "requests",
        "http",
        "http.client",
        "socket",
        "aiohttp",
        "ftplib",
        "paramiko",
        "boto3",
        "botocore",
        "openneuro",
        "mne_bids",
    }
    offenders: list[str] = []
    for path in sorted(root.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    top = alias.name.split(".")[0]
                    if alias.name in banned or top in banned:
                        offenders.append(f"{path.name}:{alias.name}")
            elif isinstance(node, ast.ImportFrom) and node.module:
                top = node.module.split(".")[0]
                if node.module in banned or top in banned:
                    offenders.append(f"{path.name}:{node.module}")
    assert offenders == []
