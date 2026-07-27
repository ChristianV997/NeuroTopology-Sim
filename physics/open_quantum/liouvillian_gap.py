"""Liouvillian gaps, radiative-mode lifetimes, and steady-state currents."""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
from scipy.sparse import csc_matrix,eye
from scipy.sparse.linalg import LinearOperator,eigs,splu
from .lindblad_lattice import HBAR,LindbladLattice
@dataclass(frozen=True)
class GapResult:
    gap_s:float; decoherence_time_s:float; stationary_eigenvalue_s:complex; method:str; stationary_residual_s:float; trace_preservation_residual_s:float; hermiticity_residual:float; stationary_modes:int; gap_zero:bool; converged:bool
    subradiant_gap_s:float=0.; superradiant_gap_s:float=0.; tau_subradiant_s:float=float("inf"); tau_superradiant_s:float=float("inf"); chiral_current_s:float=0.; exhibits_chiral_current:bool=False; stationary_state:np.ndarray|None=None; iteration_count:int=0
def calculate_lattice_currents(rho_ss:np.ndarray,H:np.ndarray)->np.ndarray:
    """Return Hamiltonian probability-current matrix J_ij=2 Im(H_ij rho_ji)/hbar in s^-1."""
    rho=np.asarray(rho_ss,complex); ham=np.asarray(H,complex)
    if rho.shape!=ham.shape or rho.ndim!=2 or rho.shape[0]!=rho.shape[1]: raise ValueError("rho_ss and H must be same square shape")
    current=2*np.imag(ham*rho.T)/HBAR; np.fill_diagonal(current,0.); return (current-current.T)/2
def _analyse(values:np.ndarray,tol:float)->tuple[float,complex,int,bool,float,float]:
    vals=np.asarray(values,complex); stationary=vals[int(np.argmin(np.abs(vals)))]; modes=int(np.count_nonzero(np.abs(vals)<=tol)); non=vals[np.abs(vals-stationary)>tol]; decays=-non.real[(-non.real)>tol]
    if not len(decays) or modes>1:return 0.,stationary,modes,True,0.,0.
    sub=float(np.min(decays)); super=float(np.max(decays)); return sub,stationary,modes,False,sub,super
def _stationary_density(vector:np.ndarray|None,d:int)->np.ndarray|None:
    if vector is None:return None
    rho=np.asarray(vector,complex).reshape((d,d),order="F"); rho=(rho+rho.conj().T)/2; trace=np.trace(rho)
    if abs(trace)<1e-20:return None
    return rho/trace
def _chiral_score(model:LindbladLattice,rho:np.ndarray|None)->tuple[float,bool]:
    if rho is None:return 0.,False
    current=calculate_lattice_currents(rho,model.hamiltonian)[1:,1:]; angles=np.arctan2(model.positions[:,1],model.positions[:,0]); orientation=np.sin(angles[None,:]-angles[:,None]); score=float(np.sum(current*orientation)/2); scale=float(np.sum(np.abs(current)))
    return score,bool(abs(score)>max(1e-12,1e-6*scale))
def _result(model:LindbladLattice,values:np.ndarray,method:str,tol:float,converged:bool,vectors:np.ndarray|None=None,iteration_count:int=0)->GapResult:
    gap,stationary,modes,zero,sub,super=_analyse(values,tol); index=int(np.argmin(np.abs(values))); rho=_stationary_density(vectors[:,index] if vectors is not None else None,model.dimension); chiral,flag=_chiral_score(model,rho); tau_sub=float(np.inf if zero or sub==0 else 1/sub); tau_super=float(np.inf if super==0 else 1/super); probe=np.eye(model.dimension,dtype=complex)/model.dimension
    stationary_residual=float(abs(stationary)); resolved=converged and (method=="exact_dense" or stationary_residual<=max(tol,1e-3))
    return GapResult(gap,tau_sub,complex(stationary),method,stationary_residual,model.trace_residual(probe),float(np.linalg.norm(model.hamiltonian-model.hamiltonian.conj().T)),modes,zero,resolved,sub,super,tau_sub,tau_super,chiral,flag,rho,iteration_count)
def dense_gap(model:LindbladLattice,*,tolerance_s:float=1e-8,max_dimension:int=32)->GapResult:
    """Exactly diagonalise models through Hilbert dimension 32 (1024 Liouville modes)."""
    if model.dimension>max_dimension:raise ValueError("dense Liouvillian limited to dimension <=32")
    values,vectors=np.linalg.eig(model.liouvillian()); return _result(model,values,"exact_dense",tolerance_s,True,vectors)
def matrix_free_gap(model:LindbladLattice,*,k:int=6,tolerance_s:float=1e-8,maxiter:int|None=None)->GapResult:
    d=model.dimension; size=d*d
    # Explicit sparse storage permits a controlled SuperLU shift-invert
    # solve.  This avoids ARPACK's unbounded implicit inner iteration.
    superop=csc_matrix(model.liouvillian()); sigma=1e-5
    lu=splu(superop-sigma*eye(size,format="csc",dtype=np.complex128))
    calls=0
    def inverse(v:np.ndarray)->np.ndarray:
        nonlocal calls
        calls+=1
        return lu.solve(v)
    opinv=LinearOperator((size,size),matvec=inverse,dtype=np.complex128); kk=max(2,min(k,size-2))
    values=eigs(superop,k=kk,sigma=sigma,which="LM",OPinv=opinv,tol=1e-8,maxiter=maxiter,return_eigenvectors=False)
    return _result(model,values,"matrix_free_estimate",tolerance_s,True,iteration_count=calls)

def solve_gap(model:LindbladLattice,*,dense_max_dimension:int=32,k:int=6,tolerance_s:float=1e-8,maxiter:int|None=None)->GapResult:
    """Choose exact dense spectra through N=32, SuperLU-preconditioned Krylov above it."""
    return dense_gap(model,tolerance_s=tolerance_s,max_dimension=dense_max_dimension) if model.dimension<=dense_max_dimension else matrix_free_gap(model,k=k,tolerance_s=tolerance_s,maxiter=maxiter)
