"""Finite Lindblad lattice with local pumping and explicit SI units."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import numpy as np
EPS0=8.8541878128e-12; HBAR=1.054571817e-34; EV=1.602176634e-19; KB=1.380649e-23; DEBYE=3.33564e-30
@dataclass(frozen=True)
class ThermalBathConfig:
    temperature_K:float=310.; radiative_rate_s:float=.1e9; thermal_relaxation_s:float=0.; thermal_excitation_s:float=0.; dephasing_rate_s:float=10e12; ciss_dephasing_rate_s:float=0.; metabolic_pump_rate_s:float=0.; pump_sites:tuple[int,...]=(0,); collective_radiative_rate_s:float=0.; collective_correlation_length_m:float=1e-9
    @classmethod
    def from_temperature(cls,temperature_K:float,transition_energy_eV:float,*,thermal_relaxation_s:float,dephasing_rate_s:float,radiative_rate_s:float,ciss_dephasing_rate_s:float=0.,metabolic_pump_rate_s:float=0.,pump_sites:tuple[int,...]=(0,))->"ThermalBathConfig":
        if (not np.isfinite(temperature_K) or temperature_K<=0
                or not np.isfinite(transition_energy_eV) or transition_energy_eV<0):
            raise ValueError("temperature must be finite and positive and transition energy finite and non-negative")
        rates=(thermal_relaxation_s,dephasing_rate_s,radiative_rate_s,ciss_dephasing_rate_s,metabolic_pump_rate_s)
        if any(x<0 or not np.isfinite(x) for x in rates): raise ValueError("rates must be finite and non-negative")
        excitation=thermal_relaxation_s*float(np.exp(-transition_energy_eV*EV/(KB*temperature_K)))
        return cls(float(temperature_K),float(radiative_rate_s),float(thermal_relaxation_s),excitation,float(dephasing_rate_s),float(ciss_dephasing_rate_s),float(metabolic_pump_rate_s),tuple(int(x) for x in pump_sites))
@dataclass(frozen=True)
class LatticeConfig:
    n_protofilaments:int=13; n_layers:int=1; radius_m:float=12e-9; axial_spacing_m:float=.923e-9; dielectric_constant:float=7.; transition_energy_eV:float=4.43; dipole_debye:float=2.1; interaction_cutoff_m:float=8e-9; bath:ThermalBathConfig=ThermalBathConfig()
@dataclass(frozen=True)
class SolverState: rho:np.ndarray; time_s:float
class LindbladLattice:
    """13-protofilament exciton lattice; pump/CISS parameters are phenomenological."""
    def __init__(self,positions_m:np.ndarray,dipoles_Cm:np.ndarray,config:LatticeConfig=LatticeConfig()):
        self.positions=np.asarray(positions_m,float); self.dipoles=np.asarray(dipoles_Cm,float); self.config=config
        if self.positions.ndim!=2 or self.positions.shape[1]!=3 or self.dipoles.shape!=self.positions.shape: raise ValueError("positions and dipoles must have shape (N,3)")
        if len(self.positions)==0 or not np.all(np.isfinite(self.positions)) or not np.all(np.isfinite(self.dipoles)): raise ValueError("finite non-empty coordinates required")
        config_values=(config.radius_m,config.axial_spacing_m,config.dielectric_constant,config.transition_energy_eV,config.dipole_debye,config.interaction_cutoff_m,config.bath.temperature_K)
        if (config.n_protofilaments<1 or config.n_layers<1
                or any(not isinstance(value,(int,np.integer)) or isinstance(value,bool) for value in (config.n_protofilaments,config.n_layers))
                or any(not np.isfinite(value) for value in config_values)
                or config.radius_m<=0 or config.axial_spacing_m<=0 or config.dielectric_constant<=0
                or config.transition_energy_eV<0 or config.dipole_debye<0 or config.interaction_cutoff_m<=0
                or config.bath.temperature_K<=0):
            raise ValueError("invalid lattice geometry, energy, dielectric, cutoff, or temperature")
        rates=(config.bath.radiative_rate_s,config.bath.thermal_relaxation_s,config.bath.thermal_excitation_s,config.bath.dephasing_rate_s,config.bath.ciss_dephasing_rate_s,config.bath.metabolic_pump_rate_s,config.bath.collective_radiative_rate_s)
        if any(x<0 or not np.isfinite(x) for x in rates): raise ValueError("rates must be finite and non-negative")
        if config.bath.collective_correlation_length_m <= 0 or not np.isfinite(config.bath.collective_correlation_length_m): raise ValueError("collective correlation length must be finite and positive")
        if any(site<0 or site>=len(self.positions) for site in config.bath.pump_sites): raise ValueError("pump sites must index lattice sites")
        if config.bath.metabolic_pump_rate_s and not config.bath.pump_sites: raise ValueError("active pump requires at least one pump site")
        self.hamiltonian=self._build_hamiltonian(); self.collapse_operators=self.construct_collapse_operators()
    @classmethod
    def from_pbc(cls,config:LatticeConfig=LatticeConfig())->"LindbladLattice":
        if config.n_protofilaments!=13 or config.n_layers<1: raise ValueError("PBC requires 13 protofilaments and positive layers")
        p,k=np.meshgrid(np.arange(13),np.arange(config.n_layers),indexing="xy"); theta=2*np.pi*p/13
        pos=np.column_stack((config.radius_m*np.cos(theta).ravel(),config.radius_m*np.sin(theta).ravel(),(k*config.axial_spacing_m+p*config.axial_spacing_m).ravel())); radial=np.column_stack((np.cos(theta).ravel(),np.sin(theta).ravel(),np.zeros(p.size)))
        return cls(pos,config.dipole_debye*DEBYE*radial,config)
    @property
    def n_sites(self)->int:return len(self.positions)
    @property
    def dimension(self)->int:return self.n_sites+1
    def _build_hamiltonian(self)->np.ndarray:
        n=self.n_sites; h=np.zeros((n+1,n+1),complex); h[1:,1:]=np.eye(n)*self.config.transition_energy_eV*EV; eps=4*np.pi*EPS0*self.config.dielectric_constant
        for i in range(n):
            for j in range(i+1,n):
                d=self.positions[i]-self.positions[j]; r=float(np.linalg.norm(d))
                if r==0 or r>self.config.interaction_cutoff_m: continue
                v=(float(self.dipoles[i]@self.dipoles[j])/r**3-3*float(self.dipoles[i]@d)*float(self.dipoles[j]@d)/r**5)/eps; h[i+1,j+1]+=v; h[j+1,i+1]+=v
        return (h+h.conj().T)/2
    def construct_collapse_operators(self)->tuple[np.ndarray,...]:
        """Build trace-preserving decay, dephasing, thermal, and local pump jumps."""
        n=self.n_sites; b=self.config.bath; ops=[]
        for site in range(n):
            for row,col,rate in ((0,site+1,b.radiative_rate_s),(0,site+1,b.thermal_relaxation_s),(site+1,0,b.thermal_excitation_s)):
                if rate: op=np.zeros((n+1,n+1),complex); op[row,col]=np.sqrt(rate); ops.append(op)
            deph=b.dephasing_rate_s+b.ciss_dephasing_rate_s
            if deph: op=np.zeros((n+1,n+1),complex); op[site+1,site+1]=np.sqrt(deph); ops.append(op)
        for site in b.pump_sites:
            if b.metabolic_pump_rate_s: op=np.zeros((n+1,n+1),complex); op[site+1,0]=np.sqrt(b.metabolic_pump_rate_s); ops.append(op)
        if b.collective_radiative_rate_s:
            # A positive semidefinite exponential kernel defines a completely
            # positive spatially correlated emission bath, including its null
            # limit when the collective rate is exactly zero.
            distances=np.linalg.norm(self.positions[:,None,:]-self.positions[None,:,:],axis=2)
            kernel=b.collective_radiative_rate_s*np.exp(-distances/b.collective_correlation_length_m)
            values,vectors=np.linalg.eigh(kernel)
            for value,vector in zip(values,vectors.T):
                if value > np.finfo(float).eps*max(1.,b.collective_radiative_rate_s):
                    op=np.zeros((n+1,n+1),complex); op[0,1:]=np.sqrt(value)*vector.conj(); ops.append(op)
        return tuple(ops)
    def rhs(self,rho:np.ndarray)->np.ndarray:
        state=np.asarray(rho,complex)
        if state.shape!=(self.dimension,self.dimension): raise ValueError(f"rho must have shape {(self.dimension,self.dimension)}")
        out=-1j*(self.hamiltonian@state-state@self.hamiltonian)/HBAR
        for op in self.collapse_operators:
            q=op.conj().T@op; out+=op@state@op.conj().T-.5*(q@state+state@q)
        return out
    def liouvillian(self)->np.ndarray:
        d=self.dimension; eye=np.eye(d); out=-1j*(np.kron(eye,self.hamiltonian)-np.kron(self.hamiltonian.T,eye))/HBAR
        for op in self.collapse_operators:
            q=op.conj().T@op; out+=np.kron(op.conj(),op)-.5*(np.kron(eye,q)+np.kron(q.T,eye))
        return out
    def trace_residual(self,rho:np.ndarray)->float:return float(abs(np.trace(self.rhs(np.asarray(rho,complex)))))
    def thermal_detailed_balance(self)->float:
        down=self.config.bath.thermal_relaxation_s; return float(self.config.bath.thermal_excitation_s/down) if down else 0.
def pbc_positions(config:LatticeConfig=LatticeConfig())->np.ndarray:return LindbladLattice.from_pbc(config).positions
def load_local_centroids(path:str|Path)->np.ndarray:
    p=Path(path)
    if p.suffix.lower()==".npy": arr=np.load(p)
    elif p.suffix.lower()==".npz":
        with np.load(p) as z: arr=z[z.files[0]]
    else: raise ValueError("only local .npy/.npz centroid files are accepted")
    arr=np.asarray(arr,float)
    if arr.ndim!=2 or arr.shape[1]!=3 or not np.all(np.isfinite(arr)): raise ValueError("centroids must have finite shape (N,3)")
    return arr
