"""Strict local NPZ contract for the DM1 cloud-evaluator payload."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import numpy as np


@dataclass(frozen=True)
class CloudSnapshot:
    """Validated SI Hamiltonian, coupling metadata, boundaries, and current pairs."""
    hamiltonian_J: np.ndarray
    site_couplings_J: np.ndarray
    boundary_configuration: dict[str, object]
    active_site_pairs: tuple[tuple[int, int], ...]
    source_path: Path
    checksum_sha256: str


def _parse_boundary(value: np.ndarray) -> dict[str, object]:
    try:
        parsed = json.loads(str(np.asarray(value).item()))
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("boundary_configuration must be a scalar JSON object") from exc
    if not isinstance(parsed, dict): raise ValueError("boundary_configuration must decode to an object")
    return parsed


def load_cloud_snapshot(path: str | Path) -> CloudSnapshot:
    """Load a local TD-DFT/dense-solver snapshot with no synthetic fallback."""
    source = Path(path).resolve()
    if source.suffix.lower() != ".npz" or not source.is_file(): raise FileNotFoundError("cloud snapshot must be an existing local .npz")
    required = {"H_sys_si", "hamiltonian_unit", "site_couplings_si", "boundary_configuration", "active_site_pairs"}
    try:
        with np.load(source, allow_pickle=False) as data:
            if not required.issubset(data.files): raise ValueError(f"snapshot missing keys: {sorted(required - set(data.files))}")
            unit = str(np.asarray(data["hamiltonian_unit"]).item())
            hamiltonian = np.asarray(data["H_sys_si"], complex)
            couplings = np.asarray(data["site_couplings_si"], complex)
            boundary = _parse_boundary(data["boundary_configuration"])
            pairs = np.asarray(data["active_site_pairs"], int)
    except (OSError, ValueError) as exc:
        raise ValueError(f"invalid local cloud snapshot: {exc}") from exc
    if unit != "J": raise ValueError("H_sys_si and site_couplings_si must be declared in joules")
    if hamiltonian.ndim != 2 or hamiltonian.shape[0] != hamiltonian.shape[1] or hamiltonian.shape[0] < 2:
        raise ValueError("H_sys_si must be square with dimension at least two")
    if couplings.shape != hamiltonian.shape or not np.all(np.isfinite(hamiltonian)) or not np.all(np.isfinite(couplings)):
        raise ValueError("Hamiltonian/coupling tensors must be finite and shape-compatible")
    if not np.allclose(hamiltonian, hamiltonian.conj().T, atol=1e-30, rtol=1e-10): raise ValueError("H_sys_si must be Hermitian")
    if not np.allclose(couplings, couplings.conj().T, atol=1e-30, rtol=1e-10): raise ValueError("site_couplings_si must be Hermitian")
    if pairs.ndim != 2 or pairs.shape[1] != 2 or not len(pairs): raise ValueError("active_site_pairs must have shape (n,2)")
    pairs_tuple = tuple((int(left), int(right)) for left, right in pairs)
    if any(left == right or left < 0 or right < 0 or left >= hamiltonian.shape[0] or right >= hamiltonian.shape[0] for left, right in pairs_tuple):
        raise ValueError("active_site_pairs contain invalid site indices")
    return CloudSnapshot(hamiltonian, couplings, boundary, pairs_tuple, source, hashlib.sha256(source.read_bytes()).hexdigest())
