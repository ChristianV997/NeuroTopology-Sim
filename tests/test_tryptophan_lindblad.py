import numpy as np
from sim.pitnn.microtubule_3d import mock_trp_centroids
from sim.pitnn.tryptophan_lindblad import TryptophanLindbladModel

def test_lindblad_hamiltonian_propagation_and_dark_states():
    positions = mock_trp_centroids(4); dipoles = np.tile([1e-29, 0.0, 0.0], (4, 1))
    model = TryptophanLindbladModel(positions, dipoles)
    assert np.allclose(model.hamiltonian, model.hamiltonian.conj().T)
    rho = np.zeros((4, 4), complex); rho[0, 0] = 1
    history = model.propagate(rho, np.linspace(0, 1e-14, 5))
    assert history.shape == (5, 4, 4) and np.all(np.isfinite(history))
    assert len(model.identify_subradiant_states()["subradiant_indices"]) >= 1
