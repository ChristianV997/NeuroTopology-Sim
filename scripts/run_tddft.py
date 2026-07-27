"""Run isolated TRP-fragment TD-DFT calculations and emit validated NPZ data.

The calculation is intentionally explicit about its scope.  Each selected PDB
residue is treated as an isolated molecular fragment.  A full protein
embedding, protonation model, and solvent model are not inferred from a PDB.
By default hydrogens are required; ``--allow-heavy-atom-fragment`` exists only
for debugging and marks the output ``not_biologically_validated``.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import numpy as np
from Bio.PDB import PDBParser

EV_PER_HARTREE = 27.211386245988
DEBYE_PER_AU = 2.541746473


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _element(atom: Any) -> str:
    element = str(getattr(atom, "element", "")).strip().upper()
    if element:
        return element
    name = atom.get_name().strip().upper()
    return name[0] if name and name[0].isalpha() else ""


def _residue_atoms(pdb_path: Path, site_id: str, allow_heavy: bool) -> list[tuple[str, tuple[float, float, float]]]:
    chain_id, residue_number, insertion = site_id.split(":")
    structure = PDBParser(QUIET=True).get_structure("tubulin", str(pdb_path))
    matches = []
    for model in structure:
        for chain in model:
            if chain.id != chain_id:
                continue
            for residue in chain:
                hetflag, resseq, icode = residue.id
                if residue.get_resname().strip() == "TRP" and str(resseq) == residue_number and (icode.strip() or "_") == insertion:
                    matches.append(residue)
    if len(matches) != 1:
        raise ValueError(f"expected exactly one TRP residue for {site_id}, found {len(matches)}")
    atoms = []
    for atom in matches[0].get_atoms():
        element = _element(atom)
        if not element:
            raise ValueError(f"atom {atom.get_name()} in {site_id} has no chemical element")
        atoms.append((element, tuple(float(value) for value in atom.coord)))
    has_hydrogen = any(element == "H" for element, _ in atoms)
    if not has_hydrogen and not allow_heavy:
        raise RuntimeError(f"{site_id} has no hydrogens in the PDB; use a hydrogen-completed structure or explicitly pass --allow-heavy-atom-fragment")
    return atoms


def _run_fragment(atoms: list[tuple[str, tuple[float, float, float]]], basis: str, nstates: int) -> tuple[float, np.ndarray]:
    from pyscf import dft, gto, tdscf

    molecule = gto.Mole()
    molecule.atom = [(element, coordinates) for element, coordinates in atoms]
    molecule.unit = "Angstrom"
    molecule.basis = basis
    molecule.charge = 0
    molecule.spin = 0
    molecule.verbose = 0
    molecule.build()
    mean_field = dft.RKS(molecule)
    mean_field.xc = "b3lyp"
    mean_field.conv_tol = 1e-9
    if mean_field.kernel() < 0:
        raise RuntimeError("ground-state DFT did not converge")
    excited = tdscf.TDDFT(mean_field)
    excited.nstates = nstates
    excitation_energies = np.asarray(excited.kernel(), float).reshape(-1)
    if excitation_energies.size == 0 or not np.all(np.isfinite(excitation_energies)):
        raise RuntimeError("TD-DFT returned no finite excitation energies")
    transition_dipoles = np.asarray(excited.transition_dipole(), complex)
    if transition_dipoles.ndim == 1:
        transition_dipoles = transition_dipoles.reshape(1, -1)
    if transition_dipoles.shape[0] != excitation_energies.size or transition_dipoles.shape[1] != 3:
        raise RuntimeError(f"unexpected TD-DFT transition dipole shape {transition_dipoles.shape}")
    first = int(np.flatnonzero(excitation_energies > 0)[0])
    return float(excitation_energies[first] * EV_PER_HARTREE), np.asarray(transition_dipoles[first].real * DEBYE_PER_AU, float)


def run(pdb_path: Path, output_npz: Path, site_ids: tuple[str, ...], bases: tuple[str, ...], nstates: int, allow_heavy: bool) -> dict[str, Any]:
    """Calculate one first-excitation energy/dipole per isolated TRP fragment."""
    if len(site_ids) < 2 or len(set(site_ids)) != len(site_ids):
        raise ValueError("at least two unique site IDs are required")
    if len(bases) < 2:
        raise ValueError("at least two basis sets are required for independent validation")
    fragments = {site_id: _residue_atoms(pdb_path, site_id, allow_heavy) for site_id in site_ids}
    by_basis: dict[str, dict[str, tuple[float, np.ndarray]]] = {}
    for basis in bases:
        by_basis[basis] = {site_id: _run_fragment(atoms, basis, nstates) for site_id, atoms in fragments.items()}
    primary_basis = bases[0]
    energies = np.asarray([by_basis[primary_basis][site_id][0] for site_id in site_ids], float)
    dipoles = np.asarray([by_basis[primary_basis][site_id][1] for site_id in site_ids], float)
    validation_basis = bases[1]
    validation_energies = np.asarray([by_basis[validation_basis][site_id][0] for site_id in site_ids], float)
    validation_dipoles = np.asarray([by_basis[validation_basis][site_id][1] for site_id in site_ids], float)
    energy_delta = float(np.max(np.abs(energies - validation_energies)))
    dipole_delta = float(np.max(np.abs(dipoles - validation_dipoles)))
    payload: dict[str, Any] = {
        "schema": "ScienceR-Dsim.TDDFTValidatedInputs.v1",
        "site_ids": list(site_ids),
        "site_energies_eV": energies.tolist(),
        "transition_dipoles_debye": dipoles.tolist(),
        "software": "PySCF",
        "method": "B3LYP TD-DFT",
        "basis_set": primary_basis,
        "independent_validation": {"basis_set": validation_basis, "max_energy_delta_eV": energy_delta, "max_dipole_delta_debye": dipole_delta},
        "geometry_sha256": _sha256(pdb_path),
        "fragment_scope": "isolated_TRP_residue",
        "hydrogen_complete": not allow_heavy,
        "status": "COMPUTED_ISOLATED_FRAGMENT_NOT_FULL_TUBULIN_EMBEDDING",
    }
    output_npz.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(output_npz, site_ids=np.asarray(site_ids), site_energies_eV=energies, transition_dipoles_debye=dipoles, software=np.asarray("PySCF"), method=np.asarray("B3LYP TD-DFT"), basis_set=np.asarray(primary_basis), geometry_sha256=np.asarray(payload["geometry_sha256"]), independent_validation_json=np.asarray(json.dumps(payload["independent_validation"])), fragment_scope=np.asarray(payload["fragment_scope"]))
    output_npz.with_suffix(".json").write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdb", type=Path, required=True)
    parser.add_argument("--output-npz", type=Path, required=True)
    parser.add_argument("--site-ids", nargs="+", default=["A:21:_", "B:21:_"])
    parser.add_argument("--basis-list", nargs="+", default=["def2-SVP", "def2-TZVP"])
    parser.add_argument("--nstates", type=int, default=5)
    parser.add_argument("--allow-heavy-atom-fragment", action="store_true")
    args = parser.parse_args()
    if args.nstates < 1:
        parser.error("--nstates must be positive")
    result = run(args.pdb.resolve(), args.output_npz.resolve(), tuple(args.site_ids), tuple(args.basis_list), args.nstates, args.allow_heavy_atom_fragment)
    print(json.dumps({"status": result["status"], "output_npz": str(args.output_npz)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
