"""Local PDB structural ensemble parsing for tryptophan chromophores."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Iterable
import numpy as np

ANGSTROM_TO_M = 1e-10
_AROMATIC = {"CG", "CD1", "CD2", "CE2", "CE3", "CZ2", "CZ3", "CH2"}


@dataclass(frozen=True)
class ChromophoreSite:
    """TRP centroid/orientation in SI units, keyed by a stable PDB residue ID."""
    site_id: str
    centroid_m: np.ndarray
    normal: np.ndarray


@dataclass(frozen=True)
class StructuralEnsemble:
    """One or more local PDB conformers with immutable file provenance."""
    conformer_ids: tuple[str, ...]
    sites_by_conformer: tuple[tuple[ChromophoreSite, ...], ...]
    checksums_sha256: tuple[str, ...]
    parser_backend: str

    def sample(self, seed: int) -> tuple[str, tuple[ChromophoreSite, ...]]:
        """Select a conformer deterministically for static-disorder sampling."""
        if not self.conformer_ids: raise ValueError("ensemble is empty")
        index = int(np.random.default_rng(seed).integers(len(self.conformer_ids)))
        return self.conformer_ids[index], self.sites_by_conformer[index]


def _checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _parse_pdb(path: Path) -> tuple[ChromophoreSite, ...]:
    residues: dict[tuple[str, str, str], list[tuple[str, np.ndarray]]] = {}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.startswith(("ATOM", "HETATM")) or line[17:20].strip() != "TRP": continue
        try:
            key = (line[21].strip() or "_", line[22:26].strip(), line[26].strip() or "_")
            atom = line[12:16].strip(); coordinate = np.array([float(line[30:38]), float(line[38:46]), float(line[46:54])])
        except (ValueError, IndexError) as exc: raise ValueError(f"malformed TRP atom in {path}") from exc
        residues.setdefault(key, []).append((atom, coordinate))
    sites: list[ChromophoreSite] = []
    for key, atoms in sorted(residues.items()):
        aromatic = np.asarray([point for atom, point in atoms if atom in _AROMATIC], float)
        if aromatic.shape[0] < 3: raise ValueError(f"TRP {key} lacks three aromatic-ring atoms")
        centroid = aromatic.mean(axis=0) * ANGSTROM_TO_M
        _, _, vh = np.linalg.svd(aromatic - aromatic.mean(axis=0), full_matrices=False)
        normal = vh[-1]; normal /= np.linalg.norm(normal)
        site_id = f"{key[0]}:{key[1]}:{key[2]}"
        sites.append(ChromophoreSite(site_id, centroid, normal))
    if not sites: raise ValueError(f"no valid TRP chromophores in {path}")
    return tuple(sites)


def load_pdb_ensemble(paths: Iterable[str | Path]) -> StructuralEnsemble:
    """Load local PDB conformers without network access or synthetic fallback."""
    files = tuple(Path(path).resolve() for path in paths)
    if not files or any(not path.is_file() for path in files): raise FileNotFoundError("all PDB conformers must exist locally")
    conformers = tuple(_parse_pdb(path) for path in files)
    identities = tuple(site.site_id for site in conformers[0])
    if any(tuple(site.site_id for site in sites) != identities for sites in conformers[1:]):
        raise ValueError("conformers must contain the same ordered TRP site identities")
    return StructuralEnsemble(tuple(path.stem for path in files), conformers, tuple(_checksum(path) for path in files), "local_pdb_fixed_column")
