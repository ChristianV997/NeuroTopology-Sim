import numpy as np
import pytest
from physics.open_quantum import LatticeConfig,ThermalBathConfig,LindbladLattice,calculate_lattice_currents,dense_gap,matrix_free_gap

def model(): return LindbladLattice.from_pbc(LatticeConfig(n_layers=1,interaction_cutoff_m=20e-9,bath=ThermalBathConfig(radiative_rate_s=1e6,dephasing_rate_s=1e6)))
def test_pbc_geometry_and_trace_preservation():
 m=model(); assert m.positions.shape==(13,3); assert np.allclose(np.linalg.norm(m.positions[:13,:2],axis=1),12e-9); rho=np.zeros((m.dimension,m.dimension),complex); rho[1,1]=1; assert m.trace_residual(rho)<1e-6; assert np.allclose(m.hamiltonian,m.hamiltonian.conj().T)
def test_dense_gap_positive_and_structured():
 r=dense_gap(model(),tolerance_s=1e-4); assert r.gap_s>0 and np.isfinite(r.decoherence_time_s); assert r.method=="exact_dense"; assert r.trace_preservation_residual_s<1e-6
 assert r.subradiant_gap_s==r.gap_s and r.superradiant_gap_s>=r.subradiant_gap_s
 assert np.isfinite(r.tau_subradiant_s) and r.tau_superradiant_s<=r.tau_subradiant_s
 assert r.stationary_state is not None
 currents=calculate_lattice_currents(r.stationary_state,model().hamiltonian)
 assert currents.shape==(model().dimension,model().dimension) and np.allclose(currents,-currents.T)

def test_local_pump_is_trace_preserving():
 cfg=LatticeConfig(n_layers=1,interaction_cutoff_m=20e-9,bath=ThermalBathConfig(radiative_rate_s=1e6,dephasing_rate_s=1e6,metabolic_pump_rate_s=2e6,pump_sites=(0,4)))
 m=LindbladLattice.from_pbc(cfg); rho=np.zeros((m.dimension,m.dimension),complex); rho[0,0]=1
 assert m.trace_residual(rho)<1e-6
 assert len(m.collapse_operators)>len(model().collapse_operators)
def test_matrix_free_gap_agrees_small_system():
    m=model(); dense=dense_gap(m,tolerance_s=1e-4); iterative=matrix_free_gap(m,k=6,tolerance_s=1e-4,maxiter=2000); assert iterative.gap_s>=0 and np.isfinite(iterative.stationary_residual_s); assert abs(iterative.gap_s-dense.gap_s)<1e7


def test_collective_bath_adds_completely_positive_channels():
    cfg=LatticeConfig(n_layers=1,interaction_cutoff_m=20e-9,bath=ThermalBathConfig(radiative_rate_s=1e6,dephasing_rate_s=1e6,collective_radiative_rate_s=1e6,collective_correlation_length_m=8e-9))
    correlated=LindbladLattice.from_pbc(cfg)
    independent=LindbladLattice.from_pbc(LatticeConfig(n_layers=1,interaction_cutoff_m=20e-9,bath=ThermalBathConfig(radiative_rate_s=1e6,dephasing_rate_s=1e6)))
    rho=np.eye(correlated.dimension,dtype=complex)/correlated.dimension
    assert len(correlated.collapse_operators)>len(independent.collapse_operators)
    assert correlated.trace_residual(rho)<1e-8


def test_thermal_config_rejects_nonfinite_temperature_and_energy():
    with pytest.raises(ValueError):
        ThermalBathConfig.from_temperature(float("nan"), 4.43, thermal_relaxation_s=1e6, dephasing_rate_s=1e6, radiative_rate_s=1e6)
    with pytest.raises(ValueError):
        ThermalBathConfig.from_temperature(310.0, float("inf"), thermal_relaxation_s=1e6, dephasing_rate_s=1e6, radiative_rate_s=1e6)
