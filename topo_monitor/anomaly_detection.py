"""Streaming anomaly and consensus metrics for topology monitoring."""
from __future__ import annotations
from collections import deque
from dataclasses import dataclass
import numpy as np
@dataclass(frozen=True)
class Alert:
    metric:str
    value:float
    baseline:float
    score:float
    severity:str
    index:int
def rolling_alerts(values:list[float]|np.ndarray,*,window:int=20,z_threshold:float=3.0)->list[Alert]:
    x=np.asarray(values,float)
    if x.ndim!=1 or not np.all(np.isfinite(x)) or window<2 or z_threshold<=0: raise ValueError("finite 1D values, window>=2, and positive threshold required")
    out=[]
    for i,v in enumerate(x):
        base=x[max(0,i-window):i]
        if len(base)<window: continue
        mean=float(np.mean(base)); scale=float(np.std(base)); score=0.0 if scale==0 else abs(float(v)-mean)/scale
        if score>=z_threshold: out.append(Alert("beta1_drift",float(v),mean,score,"high",i))
    return out
def consensus_residual(adjacency:np.ndarray,state:np.ndarray)->float:
    """Return ||Lx||/||x|| for a finite symmetric interaction graph."""
    a=np.asarray(adjacency,float); x=np.asarray(state,float)
    if a.ndim!=2 or a.shape[0]!=a.shape[1] or x.shape[0]!=a.shape[0] or not np.all(np.isfinite(a)) or not np.all(np.isfinite(x)): raise ValueError("invalid graph or state")
    lap=np.diag(a.sum(axis=1))-a; return float(np.linalg.norm(lap@x)/(np.linalg.norm(x)+np.finfo(float).eps))
