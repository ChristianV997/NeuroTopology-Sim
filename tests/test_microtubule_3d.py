import numpy as np
import pytest
from sim.pitnn.microtubule_3d import MicrotubuleLattice, MicrotubuleLatticeConfig, mock_trp_centroids, parse_pdb_trp_centroids

def test_lattice_geometry_and_couplings():
    lattice = MicrotubuleLattice(MicrotubuleLatticeConfig(n_layers=3))
    assert lattice.positions.shape == (39, 3)
    assert np.allclose(np.linalg.norm(lattice.positions[:, :2], axis=1), 12e-9)
    tensors = lattice.exchange_tensors()
    assert tensors.shape[0] == 78
    assert np.isclose(np.max(tensors[:, 0, 0]) / np.min(tensors[:, 0, 0]), 2.5)
    assert lattice.dmi_vectors().shape == (78, 3)

def test_local_trp_mock_and_parser():
    assert mock_trp_centroids().shape == (8, 3)
    text = "ATOM      1  CA  TRP A   1       1.000   2.000   3.000  1.00 10.00           C\nATOM      2  CB  TRP A   1       3.000   2.000   3.000  1.00 10.00           C"
    assert np.allclose(parse_pdb_trp_centroids(text)[0], [2e-10, 2e-10, 3e-10])

def test_lattice_rejects_wrong_topology():
    with pytest.raises(ValueError): MicrotubuleLattice(MicrotubuleLatticeConfig(n_protofilaments=12))
