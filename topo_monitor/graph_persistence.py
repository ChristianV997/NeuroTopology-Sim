"""Persistent H1 analysis for dynamic weighted graphs."""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
@dataclass(frozen=True)
class PersistenceResult:
    diagram_h1: np.ndarray
    beta_curve: np.ndarray
    landscape: np.ndarray
    threshold: float
    sweep_thresholds: np.ndarray|None=None
    sweep_beta1: np.ndarray|None=None
    integrated_landscape_area: float=0.0

def _validate(a:np.ndarray)->np.ndarray:
    arr=np.asarray(a,float)
    if arr.ndim!=2 or arr.shape[0]!=arr.shape[1] or not np.all(np.isfinite(arr)): raise ValueError("adjacency must be finite and square")
    if np.any(arr<0) or np.any(arr>1): raise ValueError("weighted adjacency must be in [0,1]")
    return (arr+arr.T)/2

def persistence_diagram(adjacency:np.ndarray)->np.ndarray:
    """Return H1 diagram from a PLV-like similarity matrix."""
    try: from ripser import ripser
    except ImportError as exc: raise RuntimeError("ripser is required for persistent H1") from exc
    a=_validate(adjacency); d=1-a; np.fill_diagonal(d,0); diagrams=ripser(d,distance_matrix=True,maxdim=1)["dgms"]
    return np.asarray(diagrams[1] if len(diagrams)>1 else np.empty((0,2)),float)
def betti_curve(diagram:np.ndarray, filtration:np.ndarray)->np.ndarray:
    d=np.asarray(diagram,float); grid=np.asarray(filtration,float)
    if grid.ndim!=1 or not np.all(np.isfinite(grid)): raise ValueError("filtration must be finite 1D")
    if d.size==0: return np.zeros(grid.shape,int)
    if d.ndim!=2 or d.shape[1]!=2: raise ValueError("diagram must have shape (pairs,2)")
    death=np.where(np.isfinite(d[:,1]),d[:,1],np.inf); return np.sum((grid[None,:]>=d[:,0,None])&(grid[None,:]<death[:,None]),axis=0).astype(int)
def persistence_landscape(diagram:np.ndarray,grid:np.ndarray,n_layers:int=5)->np.ndarray:
    d=np.asarray(diagram,float); x=np.asarray(grid,float)
    if n_layers<1 or x.ndim!=1: raise ValueError("invalid landscape parameters")
    finite=d[np.isfinite(d).all(axis=1)] if d.size else np.empty((0,2)); out=np.zeros((n_layers,x.size))
    if not finite.size:return out
    tents=np.maximum(0,np.minimum(x[None,:]-finite[:,0,None],finite[:,1,None]-x[None,:])); out[:min(n_layers,len(tents))]=np.sort(tents,axis=0)[::-1][:n_layers]; return out
def filtration_sweep(diagram:np.ndarray,thresholds:np.ndarray|None=None)->tuple[np.ndarray,np.ndarray]:
    """Evaluate Betti-1 counts over PLV thresholds in `[0.1, 0.9]`."""
    t=np.linspace(.1,.9,9) if thresholds is None else np.asarray(thresholds,float)
    if t.ndim!=1 or not np.all(np.isfinite(t)) or np.any((t<0)|(t>1)): raise ValueError("thresholds must be finite values in [0,1]")
    d=np.asarray(diagram,float); death=np.where(np.isfinite(d[:,1]),d[:,1],np.inf) if d.size else np.empty(0)
    beta=np.asarray([np.count_nonzero((d[:,0]<=1-value)&(death>1-value)) if d.size else 0 for value in t],int)
    return t,beta
def analyze_adjacency(adjacency:np.ndarray,*,threshold:float=.5,grid:np.ndarray|None=None,n_layers:int=5)->PersistenceResult:
    if not 0<=threshold<=1: raise ValueError("threshold must be in [0,1]")
    diagram=persistence_diagram(adjacency); x=np.linspace(0,1,101) if grid is None else np.asarray(grid,float); curve=betti_curve(diagram,x); cutoff=1-threshold; beta=int(np.count_nonzero((diagram[:,0]<=cutoff)&(diagram[:,1]>cutoff))) if diagram.size else 0
    landscape=persistence_landscape(diagram,x,n_layers); sweep_t,sweep_b=filtration_sweep(diagram); area=float(np.trapezoid(np.sum(landscape,axis=0),x)); return PersistenceResult(diagram,curve,landscape,threshold,sweep_t,sweep_b,area)
def reorder_invariant(adjacency:np.ndarray,order:np.ndarray)->bool:
    a=_validate(adjacency); p=np.asarray(order,int); return np.array_equal(np.sort(p),np.arange(len(a))) and np.allclose(persistence_diagram(a),persistence_diagram(a[np.ix_(p,p)]),equal_nan=True)
