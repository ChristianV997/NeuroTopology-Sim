"""Coupled, finite microtubule exciton lattices in SI units.

This module is a numerical model of dipolar coupling, not evidence that a
biological microtubule sustains quantum coherence on any particular scale.
"""
from __future__ import annotations

from dataclasses import dataclass
import numpy as np

from .lindblad_lattice import DEBYE, LatticeConfig, LindbladLattice


@dataclass(frozen=True)
class MultiLatticeConfig:
    """Geometry for parallel 13-protofilament lattices; distances are metres."""

    inter_lattice_spacing_m: float = 10e-9
    lattice_count: int = 2

    def __post_init__(self) -> None:
        if self.lattice_count < 2:
            raise ValueError("lattice_count must be at least two")
        if not np.isfinite(self.inter_lattice_spacing_m) or self.inter_lattice_spacing_m <= 0:
            raise ValueError("inter_lattice_spacing_m must be finite and positive")


def coupled_lattice(
    lattice_config: LatticeConfig,
    coupling_config: MultiLatticeConfig = MultiLatticeConfig(),
) -> LindbladLattice:
    """Build parallel PBC lattices with dipolar interactions retained by cutoff.

    Each cylinder is translated along x by ``inter_lattice_spacing_m``.  The
    underlying Hamiltonian applies the configured dielectric and neighbour
    cutoff, including both intra- and inter-lattice couplings.
    """
    base = LindbladLattice.from_pbc(lattice_config)
    offsets = np.arange(coupling_config.lattice_count, dtype=float)[:, None] * np.array(
        [coupling_config.inter_lattice_spacing_m, 0.0, 0.0]
    )
    positions = (base.positions[None, :, :] + offsets[:, None, :]).reshape(-1, 3)
    dipoles = np.tile(base.dipoles, (coupling_config.lattice_count, 1))
    # Pump sites are defined relative to a single lattice.  Repeat them so a
    # coupled configuration does not accidentally drive only the first tube.
    if lattice_config.bath.metabolic_pump_rate_s:
        sites_per_lattice = base.n_sites
        pump_sites = tuple(
            offset + site
            for offset in range(0, coupling_config.lattice_count * sites_per_lattice, sites_per_lattice)
            for site in lattice_config.bath.pump_sites
        )
        bath = lattice_config.bath.__class__(
            lattice_config.bath.temperature_K,
            lattice_config.bath.radiative_rate_s,
            lattice_config.bath.thermal_relaxation_s,
            lattice_config.bath.thermal_excitation_s,
            lattice_config.bath.dephasing_rate_s,
            lattice_config.bath.ciss_dephasing_rate_s,
            lattice_config.bath.metabolic_pump_rate_s,
            pump_sites,
        )
        lattice_config = LatticeConfig(
            n_protofilaments=lattice_config.n_protofilaments,
            n_layers=lattice_config.n_layers,
            radius_m=lattice_config.radius_m,
            axial_spacing_m=lattice_config.axial_spacing_m,
            dielectric_constant=lattice_config.dielectric_constant,
            transition_energy_eV=lattice_config.transition_energy_eV,
            dipole_debye=lattice_config.dipole_debye,
            interaction_cutoff_m=lattice_config.interaction_cutoff_m,
            bath=bath,
        )
    return LindbladLattice(positions, dipoles, lattice_config)
