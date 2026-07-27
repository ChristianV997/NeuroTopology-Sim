"""Shared physical and model constants for the PITNN exploratory track."""
from dataclasses import dataclass
import math


@dataclass(frozen=True)
class PITNNConstants:
    k_B: float = 1.380649e-23
    hbar: float = 1.054571817e-34
    eV: float = 1.602176634e-19
    temperature_K: float = 310.0
    mu_s: float = 1.0
    hht_dipole_separation_nm: float = 0.02
    screening_factor: float = 10.0
    chromophore_domain_size: int = 10_000
    subradiance_period_s: float = 14.4e-3
    ciss_suppression_ratio: float = 1_000.0
    topological_barrier_eV: float = 0.55

    @property
    def gamma_band_hz(self) -> float:
        return 1.0 / self.subradiance_period_s

    @property
    def topological_barrier_J(self) -> float:
        return self.topological_barrier_eV * self.eV

    @property
    def thermal_energy_J(self) -> float:
        return self.k_B * self.temperature_K

    @property
    def arrhenius_factor(self) -> float:
        return math.exp(-self.topological_barrier_J / self.thermal_energy_J)
