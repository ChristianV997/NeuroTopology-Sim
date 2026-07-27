"""Single-excitation Hamiltonians built from local structures and QM inputs."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import numpy as np
from .electronic_inputs import ElectronicStructureInputs
from .structure_parser import ChromophoreSite

EPS0 = 8.8541878128e-12
EV_TO_J = 1.602176634e-19
DEBYE_TO_CM = 3.33564e-30


@dataclass(frozen=True)
class HamiltonianModel:
    """Hermitian H_S in joules and its deterministic provenance hash."""
    hamiltonian_J: np.ndarray
    site_ids: tuple[str, ...]
    dielectric_constant: float
    cutoff_m: float
    checksum_sha256: str


def build_single_excitation_hamiltonian(sites: tuple[ChromophoreSite, ...], electronic: ElectronicStructureInputs, *, dielectric_constant: float, cutoff_m: float) -> HamiltonianModel:
    """Construct H_S with local QM energies/dipoles and dipole-dipole coupling."""
    if dielectric_constant <= 0 or cutoff_m <= 0: raise ValueError("dielectric_constant and cutoff_m must be positive")
    by_id = {site.site_id: site for site in sites}
    if set(by_id) != set(electronic.site_ids): raise ValueError("PDB and electronic inputs must have exactly matching site IDs")
    ordered = tuple(by_id[site_id] for site_id in electronic.site_ids); n = len(ordered)
    hamiltonian = np.diag(electronic.site_energies_eV * EV_TO_J).astype(complex)
    dipoles = electronic.transition_dipoles_debye * DEBYE_TO_CM
    for i in range(n):
        for j in range(i + 1, n):
            displacement = ordered[i].centroid_m - ordered[j].centroid_m; distance = float(np.linalg.norm(displacement))
            if distance == 0 or distance > cutoff_m: continue
            coupling = (float(dipoles[i] @ dipoles[j]) / distance**3 - 3 * float(dipoles[i] @ displacement) * float(dipoles[j] @ displacement) / distance**5) / (4 * np.pi * EPS0 * dielectric_constant)
            hamiltonian[i, j] = hamiltonian[j, i] = coupling
    hamiltonian = (hamiltonian + hamiltonian.conj().T) / 2
    digest = hashlib.sha256(np.ascontiguousarray(hamiltonian).view(np.uint8)).hexdigest()
    return HamiltonianModel(hamiltonian, electronic.site_ids, float(dielectric_constant), float(cutoff_m), digest)
