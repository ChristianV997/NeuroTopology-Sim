"""Local quantum-chemistry input contract; PDB coordinates alone are insufficient."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import numpy as np


@dataclass(frozen=True)
class ElectronicStructureInputs:
    """Site energies (eV) and transition dipoles (Debye) from a local QM workflow."""
    site_ids: tuple[str, ...]
    site_energies_eV: np.ndarray
    transition_dipoles_debye: np.ndarray
    source_path: Path
    checksum_sha256: str


def load_electronic_inputs(path: str | Path) -> ElectronicStructureInputs:
    """Load a strictly local NPZ with site_ids, site_energies_eV, dipoles_debye."""
    source = Path(path).resolve()
    if source.suffix.lower() != ".npz" or not source.is_file(): raise FileNotFoundError("local electronic inputs must be an existing .npz file")
    with np.load(source, allow_pickle=False) as payload:
        required = {"site_ids", "site_energies_eV", "transition_dipoles_debye"}
        if not required.issubset(payload.files): raise ValueError(f"electronic NPZ requires {sorted(required)}")
        site_ids = tuple(str(value) for value in payload["site_ids"].tolist())
        energies = np.asarray(payload["site_energies_eV"], float).reshape(-1)
        dipoles = np.asarray(payload["transition_dipoles_debye"], float)
    if not site_ids or len(set(site_ids)) != len(site_ids) or energies.shape != (len(site_ids),) or dipoles.shape != (len(site_ids), 3):
        raise ValueError("electronic input shapes or unique site IDs are invalid")
    if not np.all(np.isfinite(energies)) or not np.all(np.isfinite(dipoles)) or np.any(np.linalg.norm(dipoles, axis=1) == 0):
        raise ValueError("electronic inputs must be finite with non-zero transition dipoles")
    return ElectronicStructureInputs(site_ids, energies, dipoles, source, hashlib.sha256(source.read_bytes()).hexdigest())
