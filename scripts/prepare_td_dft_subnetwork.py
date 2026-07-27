"""Prepare a reproducible local TRP subnetwork handoff for an external QM engine.

This script never invents excitation energies, transition dipoles, hydrogens,
charges, or multiplicities.  It extracts heavy-atom coordinates for selected
TRP residues and writes a manifest that is explicitly incomplete until a
validated structure-preparation and TD-DFT calculation has been performed.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def _checksum(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _extract(path: Path, requested: tuple[str, ...]) -> dict[str, list[tuple[str, float, float, float]]]:
    atoms: dict[str, list[tuple[str, float, float, float]]] = {key: [] for key in requested}
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.startswith(("ATOM", "HETATM")) or line[17:20].strip() != "TRP":
            continue
        key = f"{line[21].strip() or '_'}:{line[22:26].strip()}:{line[26].strip() or '_'}"
        if key not in atoms:
            continue
        atom = line[12:16].strip()
        try:
            coordinates = (float(line[30:38]), float(line[38:46]), float(line[46:54]))
        except ValueError as exc:
            raise ValueError(f"malformed coordinate for {key} in {path}") from exc
        atoms[key].append((atom, *coordinates))
    if any(len(values) < 3 for values in atoms.values()):
        missing = [key for key, values in atoms.items() if len(values) < 3]
        raise ValueError(f"requested TRP sites missing or incomplete: {missing}")
    return atoms


def prepare(pdb_path: Path, output_dir: Path, site_ids: tuple[str, ...]) -> dict[str, Any]:
    """Write heavy-atom XYZ files and a fail-closed QM handoff manifest."""
    if len(site_ids) < 2 or len(set(site_ids)) != len(site_ids):
        raise ValueError("at least two unique TRP site IDs are required")
    pdb_path = pdb_path.resolve()
    atoms = _extract(pdb_path, site_ids)
    output_dir.mkdir(parents=True, exist_ok=True)
    files: list[dict[str, Any]] = []
    for site_id, site_atoms in atoms.items():
        xyz = output_dir / (site_id.replace(":", "_") + "_heavy_atoms.xyz")
        lines = [str(len(site_atoms)), f"TRP heavy atoms from {pdb_path.name}; hydrogens intentionally absent"]
        for atom, x, y, z in site_atoms:
            element = atom[0] if atom[0] in "CHNOSP" else "C"
            lines.append(f"{element} {x:.8f} {y:.8f} {z:.8f}")
        xyz.write_text("\n".join(lines) + "\n", encoding="utf-8")
        files.append({"site_id": site_id, "path": str(xyz), "sha256": _checksum(xyz), "atom_count": len(site_atoms)})
    manifest: dict[str, Any] = {
        "schema": "ScienceR-Dsim.TDDFTSubnetworkHandoff.v1",
        "status": "PENDING_EXTERNAL_STRUCTURE_PREPARATION_AND_TDDFT",
        "source_pdb": str(pdb_path),
        "source_pdb_sha256": _checksum(pdb_path),
        "site_ids": list(site_ids),
        "files": files,
        "missing_required_steps": [
            "add or validate hydrogens and bond connectivity",
            "define protonation, charge, multiplicity, and environment/embedding",
            "run TD-DFT with a documented functional and basis set",
            "extract site-resolved excitation energies and transition dipoles",
            "repeat with an independent basis set or method for validation",
        ],
        "output_npz_contract": {
            "site_ids": f"shape ({len(site_ids)},), strings",
            "site_energies_eV": f"shape ({len(site_ids)},), finite transition energies",
            "transition_dipoles_debye": f"shape ({len(site_ids)}, 3), Cartesian vectors",
            "required_provenance": ["software", "method", "basis_set", "geometry_sha256", "independent_validation"],
        },
        "scientific_note": "This package is a geometry handoff only. It is not TD-DFT data and must not be used as an electronic input snapshot.",
    }
    manifest_path = output_dir / "td_dft_subnetwork_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdb", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("data/qm/td_dft_subnetwork"))
    parser.add_argument("--site-ids", nargs="+", default=["A:21:_", "B:21:_"])
    args = parser.parse_args()
    manifest = prepare(args.pdb, args.output_dir, tuple(args.site_ids))
    print(json.dumps({"status": manifest["status"], "manifest": str(args.output_dir / "td_dft_subnetwork_manifest.json")}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
