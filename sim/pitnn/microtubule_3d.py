"""Deterministic periodic 13-protofilament microtubule geometry."""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np

@dataclass(frozen=True)
class MicrotubuleLatticeConfig:
    n_layers: int = 8
    n_protofilaments: int = 13
    radius_m: float = 12e-9
    axial_spacing_m: float = 0.923e-9
    j_perpendicular: float = 1.0
    j_parallel: float = 2.5
    dmi_strength: float = 0.1
    periodic_z: bool = True

class MicrotubuleLattice:
    """Build a cylindrical lattice with explicit toroidal axial PBC."""
    def __init__(self, config: MicrotubuleLatticeConfig = MicrotubuleLatticeConfig()):
        if config.n_protofilaments != 13 or config.n_layers < 1 or config.radius_m <= 0:
            raise ValueError("B-type lattice requires 13 protofilaments and positive dimensions")
        self.config = config
        self.positions, self.protofilament, self.layer = self._build_positions()
        self.edges, self.edge_kind = self._build_edges()
    @property
    def n_sites(self) -> int:
        return self.config.n_protofilaments * self.config.n_layers
    @property
    def axial_period_m(self) -> float:
        return self.config.n_layers * self.config.axial_spacing_m
    def _index(self, proto: int, layer: int) -> int:
        return (layer % self.config.n_layers) * 13 + (proto % 13)
    def _build_positions(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        c = self.config
        p, k = np.meshgrid(np.arange(13), np.arange(c.n_layers), indexing="xy")
        angle = 2.0 * np.pi * p / 13.0
        positions = np.column_stack((c.radius_m*np.cos(angle).ravel(), c.radius_m*np.sin(angle).ravel(), (k*c.axial_spacing_m + p*c.axial_spacing_m).ravel()))
        return positions, p.ravel(), k.ravel()
    def _build_edges(self) -> tuple[np.ndarray, np.ndarray]:
        edges, kinds = [], []
        for layer in range(self.config.n_layers):
            for proto in range(13):
                next_layer = layer + 1
                if next_layer < self.config.n_layers or self.config.periodic_z:
                    edges.append((self._index(proto, layer), self._index(proto, next_layer))); kinds.append("parallel")
                edges.append((self._index(proto, layer), self._index(proto + 1, layer))); kinds.append("lateral")
        return np.asarray(edges, dtype=int), np.asarray(kinds, dtype="U8")
    def exchange_tensors(self) -> np.ndarray:
        values = np.where(self.edge_kind == "parallel", self.config.j_parallel, self.config.j_perpendicular)
        return values[:, None, None] * np.eye(3)[None, :, :]
    def dmi_vectors(self) -> np.ndarray:
        start = self.positions[self.edges[:, 0]]
        displacement = self.positions[self.edges[:, 1]] - start
        if self.config.periodic_z:
            displacement[:, 2] -= self.axial_period_m * np.round(displacement[:, 2] / self.axial_period_m)
        displacement /= np.maximum(np.linalg.norm(displacement, axis=1, keepdims=True), np.finfo(float).eps)
        radial = start.copy(); radial[:, 2] = 0.0
        radial /= np.maximum(np.linalg.norm(radial, axis=1, keepdims=True), np.finfo(float).eps)
        return self.config.dmi_strength * np.cross(radial, displacement)

def parse_pdb_trp_centroids(pdb_text: str) -> np.ndarray:
    """Parse local PDB TRP atom records and return centroids in metres."""
    groups: dict[tuple[str, int], list[list[float]]] = {}
    for line in pdb_text.splitlines():
        if not (line.startswith("ATOM") or line.startswith("HETATM")) or line[17:20].strip() != "TRP": continue
        try: key = (line[21].strip(), int(line[22:26])); xyz = [float(line[30:38]), float(line[38:46]), float(line[46:54])]
        except (ValueError, IndexError) as exc: raise ValueError("malformed TRP PDB record") from exc
        groups.setdefault(key, []).append(xyz)
    if not groups: raise ValueError("no TRP records found")
    return np.asarray([np.mean(atoms, axis=0)*1e-10 for atoms in groups.values()], dtype=float)

def mock_trp_centroids(n: int = 8) -> np.ndarray:
    """Generate deterministic local Trp centroids in metres."""
    if n < 1: raise ValueError("n must be positive")
    theta = np.linspace(0.0, 2.0*np.pi, n, endpoint=False)
    return np.column_stack((2e-9*np.cos(theta), 2e-9*np.sin(theta), 0.4e-9*np.sin(2*theta)))
