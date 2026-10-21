"""Configuration representations for synthetic nuisance scenarios and parameter grids.

Strictly synthetic configuration structures for operating-characteristic sweeps.
No biological realism or head model claims are implied.
"""
from __future__ import annotations

import dataclasses
import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Any, Iterator, Mapping, Optional, Sequence, Union

SUPPORTED_COORDINATE_UNITS = frozenset({"mm", "cm", "m"})

# Colored-noise synthesis requires at least 4 samples (Nyquist + positive bins).
_MIN_N_SAMPLES = 4


def _require_alias_agreement(
    canonical_name: str,
    canonical_value: Any,
    alias_name: str,
    alias_value: Any,
) -> None:
    """Fail closed when both alias and canonical keys are present but disagree."""
    if canonical_value is None or alias_value is None:
        return
    if isinstance(canonical_value, (int, float)) and isinstance(alias_value, (int, float)):
        c_f = float(canonical_value)
        a_f = float(alias_value)
        if not (math.isfinite(c_f) and math.isfinite(a_f) and c_f == a_f):
            raise ValueError(
                f"conflict: '{canonical_name}'={canonical_value!r} disagrees with "
                f"alias '{alias_name}'={alias_value!r}"
            )
        return
    if str(canonical_value).strip().lower() != str(alias_value).strip().lower():
        raise ValueError(
            f"conflict: '{canonical_name}'={canonical_value!r} disagrees with "
            f"alias '{alias_name}'={alias_value!r}"
        )


@dataclass(frozen=True)
class NuisanceScenarioConfig:
    """Explicit parameters defining a single synthetic nuisance scenario.

    Parameters:
        noise_exponent: Spectral slope exponent chi in 1/f^chi (chi >= 0.0).
        target_snr_db: Desired signal-to-noise ratio in decibels.
        coordinate_jitter_std: Standard deviation of 3D Gaussian coordinate displacement.
        coordinate_units: Physical units of coordinates and jitter ('mm', 'cm', or 'm').
        renormalize_to_sphere: If True, projects jittered coordinates back to original sphere radius.
                               If False (default), applies unconstrained additive 3D Cartesian jitter.
        sfreq_hz: Sampling frequency in Hertz.
        duration_s: Duration of signal in seconds.
        n_channels: Number of synthetic channels.
        seed: RNG master seed for reproducible scenario realization.
        scenario_id: Optional explicit identifier; generated deterministically if empty.
        metadata: User-defined context or pipeline tags.
    """

    noise_exponent: float = 1.0
    target_snr_db: float = 0.0
    coordinate_jitter_std: float = 0.0
    coordinate_units: str = "mm"
    renormalize_to_sphere: bool = False
    sfreq_hz: float = 250.0
    duration_s: float = 2.0
    n_channels: int = 4
    seed: int = 42
    scenario_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __init__(
        self,
        noise_exponent: Optional[float] = None,
        target_snr_db: float = 0.0,
        coordinate_jitter_std: Optional[float] = None,
        coordinate_units: Optional[str] = None,
        renormalize_to_sphere: bool = False,
        sfreq_hz: Optional[float] = None,
        duration_s: float = 2.0,
        n_channels: int = 4,
        seed: int = 42,
        scenario_id: str = "",
        metadata: Optional[dict[str, Any]] = None,
        *,
        chi: Optional[float] = None,
        jitter_std: Optional[float] = None,
        jitter_units: Optional[str] = None,
        sampling_rate_hz: Optional[float] = None,
    ) -> None:
        # Prefer alias when only one side is supplied; refuse silent disagreement.
        _require_alias_agreement("noise_exponent", noise_exponent, "chi", chi)
        _require_alias_agreement(
            "coordinate_jitter_std", coordinate_jitter_std, "jitter_std", jitter_std
        )
        _require_alias_agreement(
            "coordinate_units", coordinate_units, "jitter_units", jitter_units
        )
        _require_alias_agreement("sfreq_hz", sfreq_hz, "sampling_rate_hz", sampling_rate_hz)

        eff_chi = chi if chi is not None else (noise_exponent if noise_exponent is not None else 1.0)
        eff_jit = jitter_std if jitter_std is not None else (
            coordinate_jitter_std if coordinate_jitter_std is not None else 0.0
        )
        eff_units = jitter_units if jitter_units is not None else (
            coordinate_units if coordinate_units is not None else "mm"
        )
        eff_sfreq = sampling_rate_hz if sampling_rate_hz is not None else (
            sfreq_hz if sfreq_hz is not None else 250.0
        )
        eff_meta = metadata if metadata is not None else {}

        object.__setattr__(self, "noise_exponent", float(eff_chi))
        object.__setattr__(self, "target_snr_db", float(target_snr_db))
        object.__setattr__(self, "coordinate_jitter_std", float(eff_jit))
        object.__setattr__(self, "coordinate_units", str(eff_units))
        object.__setattr__(self, "renormalize_to_sphere", bool(renormalize_to_sphere))
        object.__setattr__(self, "sfreq_hz", float(eff_sfreq))
        object.__setattr__(self, "duration_s", float(duration_s))
        object.__setattr__(self, "n_channels", int(n_channels))
        object.__setattr__(self, "seed", int(seed))
        object.__setattr__(self, "metadata", eff_meta)

        # Validation
        if not math.isfinite(self.noise_exponent) or self.noise_exponent < 0.0:
            raise ValueError(
                f"noise_exponent (chi) must be a non-negative finite float, got {self.noise_exponent}"
            )
        if not math.isfinite(self.target_snr_db):
            raise ValueError(
                f"target_snr_db must be a finite float, got {self.target_snr_db}"
            )
        if not math.isfinite(self.coordinate_jitter_std) or self.coordinate_jitter_std < 0.0:
            raise ValueError(
                f"coordinate_jitter_std must be a non-negative finite float, got {self.coordinate_jitter_std}"
            )
        if self.coordinate_units.lower() not in SUPPORTED_COORDINATE_UNITS:
            raise ValueError(
                f"coordinate_units must be one of {sorted(SUPPORTED_COORDINATE_UNITS)}, got '{self.coordinate_units}'"
            )
        if not math.isfinite(self.sfreq_hz) or self.sfreq_hz <= 0.0:
            raise ValueError(
                f"sfreq_hz must be a positive finite float, got {self.sfreq_hz}"
            )
        if not math.isfinite(self.duration_s) or self.duration_s <= 0.0:
            raise ValueError(
                f"duration_s must be a positive finite float, got {self.duration_s}"
            )
        if self.n_channels <= 0:
            raise ValueError(
                f"n_channels must be a positive integer, got {self.n_channels}"
            )
        n_samp = int(round(self.duration_s * self.sfreq_hz))
        if n_samp < _MIN_N_SAMPLES:
            raise ValueError(
                f"n_samples must be >= {_MIN_N_SAMPLES} for colored-noise synthesis, "
                f"got {n_samp} from duration_s={self.duration_s} * sfreq_hz={self.sfreq_hz}"
            )

        eff_id = scenario_id if scenario_id else self._generate_id()
        object.__setattr__(self, "scenario_id", eff_id)

    @property
    def chi(self) -> float:
        """Alias for noise_exponent."""
        return self.noise_exponent

    @property
    def jitter_std(self) -> float:
        """Alias for coordinate_jitter_std."""
        return self.coordinate_jitter_std

    @property
    def jitter_units(self) -> str:
        """Alias for coordinate_units."""
        return self.coordinate_units

    @property
    def sampling_rate_hz(self) -> float:
        """Alias for sfreq_hz."""
        return self.sfreq_hz

    @property
    def n_samples(self) -> int:
        """Total number of time samples across duration."""
        return int(round(self.duration_s * self.sfreq_hz))

    def _generate_id(self) -> str:
        """Construct deterministic, human-readable and hash-stable scenario identifier."""
        renorm_tag = "sphrenorm" if self.renormalize_to_sphere else "rawcart"
        base_desc = (
            f"nuis_chi{self.noise_exponent:.2f}_"
            f"snr{self.target_snr_db:+.1f}dB_"
            f"jit{self.coordinate_jitter_std:.2f}{self.coordinate_units.lower()}_{renorm_tag}_"
            f"seed{self.seed}"
        )
        return base_desc

    def to_dict(self) -> dict[str, Any]:
        """Convert configuration to JSON-safe dictionary."""
        d = dataclasses.asdict(self)
        d["coordinate_units"] = self.coordinate_units.lower()
        d["chi"] = self.chi
        d["jitter_std"] = self.jitter_std
        d["sampling_rate_hz"] = self.sampling_rate_hz
        d["n_samples"] = self.n_samples
        return d

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> NuisanceScenarioConfig:
        """Instantiate configuration from dictionary.

        Accepts canonical field names and documented aliases (``chi``,
        ``jitter_std``, ``jitter_units``, ``sampling_rate_hz``). Alias-only
        payloads must not silently fall back to defaults.
        """
        d = dict(data)
        meta = d.pop("metadata", {})
        # Derived sample count is never a constructor input.
        d.pop("n_samples", None)

        # Refuse silent disagreement before collapsing aliases.
        _require_alias_agreement("noise_exponent", d.get("noise_exponent"), "chi", d.get("chi"))
        _require_alias_agreement(
            "coordinate_jitter_std",
            d.get("coordinate_jitter_std"),
            "jitter_std",
            d.get("jitter_std"),
        )
        _require_alias_agreement(
            "coordinate_units",
            d.get("coordinate_units"),
            "jitter_units",
            d.get("jitter_units"),
        )
        _require_alias_agreement(
            "sfreq_hz", d.get("sfreq_hz"), "sampling_rate_hz", d.get("sampling_rate_hz")
        )

        # Map aliases → constructor kwargs without discarding values.
        # Prefer explicit alias when the canonical key is absent.
        if "noise_exponent" not in d and "chi" in d:
            d["noise_exponent"] = d["chi"]
        if "coordinate_jitter_std" not in d and "jitter_std" in d:
            d["coordinate_jitter_std"] = d["jitter_std"]
        if "coordinate_units" not in d and "jitter_units" in d:
            d["coordinate_units"] = d["jitter_units"]
        if "sfreq_hz" not in d and "sampling_rate_hz" in d:
            d["sfreq_hz"] = d["sampling_rate_hz"]

        # Strip aliases so cls(**d) does not receive unexpected duplicates
        # as both positional dataclass fields and keyword-only aliases.
        d.pop("chi", None)
        d.pop("jitter_std", None)
        d.pop("jitter_units", None)
        d.pop("sampling_rate_hz", None)
        return cls(**d, metadata=meta)


@dataclass
class NuisanceGridConfig:
    """Specification for multi-dimensional nuisance parameter sweeps."""

    chi_values: Sequence[float] = (0.0, 1.0, 1.5, 2.0)
    snr_db_values: Sequence[float] = (-10.0, -3.0, 0.0, 6.0, 15.0)
    jitter_std_values: Sequence[float] = (0.0, 1.0, 2.5, 5.0)
    seeds: Sequence[int] = (42,)
    renormalize_options: Sequence[bool] = (False,)
    coordinate_units: str = "mm"
    sfreq_hz: float = 250.0
    duration_s: float = 2.0
    n_channels: int = 4

    def generate_scenarios(self) -> list[NuisanceScenarioConfig]:
        """Generate full Cartesian product of scenario configurations."""
        scenarios: list[NuisanceScenarioConfig] = []
        for chi in self.chi_values:
            for snr in self.snr_db_values:
                for jit in self.jitter_std_values:
                    for renorm in self.renormalize_options:
                        for seed in self.seeds:
                            cfg = NuisanceScenarioConfig(
                                noise_exponent=float(chi),
                                target_snr_db=float(snr),
                                coordinate_jitter_std=float(jit),
                                coordinate_units=self.coordinate_units,
                                renormalize_to_sphere=bool(renorm),
                                sfreq_hz=float(self.sfreq_hz),
                                duration_s=float(self.duration_s),
                                n_channels=int(self.n_channels),
                                seed=int(seed),
                            )
                            scenarios.append(cfg)
        return scenarios

    def scenarios(self) -> list[NuisanceScenarioConfig]:
        """Alias for generate_scenarios."""
        return self.generate_scenarios()
