"""Offline, falsification-first exact-dynamics contracts.

Optional solver integrations are intentionally isolated from dashboard code.
"""
from .structure_parser import ChromophoreSite, StructuralEnsemble, load_pdb_ensemble
from .electronic_inputs import ElectronicStructureInputs, load_electronic_inputs
from .hamiltonian_builder import HamiltonianModel, build_single_excitation_hamiltonian
from .evaluate import FalsificationConfig, evaluate_falsification
from .cloud_snapshot import CloudSnapshot, load_cloud_snapshot

__all__ = ["ChromophoreSite", "StructuralEnsemble", "load_pdb_ensemble", "ElectronicStructureInputs",
           "load_electronic_inputs", "HamiltonianModel", "build_single_excitation_hamiltonian",
           "FalsificationConfig", "evaluate_falsification", "CloudSnapshot", "load_cloud_snapshot"]
