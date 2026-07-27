import numpy as np
from sim.pitnn.exceptional_points_fast import FullSpectrumEPConfig, full_spectrum_diagnostics
from sim.pitnn.microtubule_3d import MicrotubuleLattice, MicrotubuleLatticeConfig
from sim.pitnn.rg_coarse_graining import block_spin_decimate, temporal_rescale
from sim.pitnn.tryptophan_lindblad import LindbladConfig, TryptophanLindbladModel

def test_phonon_dissipator_and_finite_enhancement():
    positions = np.array([[0,0,0],[1e-9,0,0],[0,1e-9,0]], float)
    model = TryptophanLindbladModel(positions, np.tile([0,0,1e-29], (3,1)), LindbladConfig(phonon_rate_s=1e12))
    result = model.identify_subradiant_states()
    assert np.all(np.isfinite(model.phonon_spectral_density(np.array([0.0,1e12]))))
    assert np.allclose(np.diag(model.phonon_dissipator(np.eye(3)/3)), 0.0)
    assert max(result["lifetime_enhancement"]) < 1.0

def test_microtubule_axial_pbc():
    lattice = MicrotubuleLattice(MicrotubuleLatticeConfig(n_layers=3, periodic_z=True))
    parallel = lattice.edges[lattice.edge_kind == "parallel"]
    assert len(parallel) == 39
    assert any(int(a//13)==2 and int(b//13)==0 for a,b in parallel)
    assert np.all(np.isfinite(lattice.dmi_vectors()))

def test_rg_block_and_time_rescaling():
    spins = np.arange(2*8*3, dtype=float).reshape(2,8,3)
    assert block_spin_decimate(spins, 2).shape == (2,4,3)
    times = np.linspace(0, 7e-15, 8)
    assert np.isclose(temporal_rescale(times, 2)[-1], times[-1]/2)

def test_full_spectrum_ep_diagnostics():
    result = full_spectrum_diagnostics(1.5, 2.5, FullSpectrumEPConfig(n_sites=6))
    assert result["eigenvalues"].shape == (6,)
    assert np.isfinite(result["global_gap"])
    assert np.isfinite(result["liouvillian_gap_proxy"])
