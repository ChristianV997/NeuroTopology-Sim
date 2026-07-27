"""Geometric spatial phase topology; graph beta1 is intentionally separate."""
from __future__ import annotations
import numpy as np
from scipy.spatial import Delaunay
def spatial_winding_charge(phases:np.ndarray,coordinates:np.ndarray)->float:
    """Return winding charge on a phase grid with matching `(H,W,2)` coordinates."""
    theta=np.asarray(phases,float); coords=np.asarray(coordinates,float)
    if theta.ndim!=2 or coords.shape!=theta.shape+(2,) or not np.all(np.isfinite(theta)) or not np.all(np.isfinite(coords)): raise ValueError("phases and coordinates must have shapes (H,W) and (H,W,2)")
    if np.any(np.linalg.norm(coords,axis=-1)==0): pass
    wrap=lambda x:(x+np.pi)%(2*np.pi)-np.pi
    local=(wrap(theta[1:,:-1]-theta[:-1,:-1])+wrap(theta[1:,1:]-theta[1:,:-1])+wrap(theta[:-1,1:]-theta[1:,1:])+wrap(theta[:-1,:-1]-theta[:-1,1:]))/(2*np.pi)
    return float(np.rint(np.sum(local)))
def complex_phase_grid(real:np.ndarray,imag:np.ndarray)->np.ndarray:
    """Return finite phase from complex field components without angle interpolation."""
    a,b=np.asarray(real,float),np.asarray(imag,float)
    if a.shape!=b.shape or a.ndim!=2 or not np.all(np.isfinite(a)) or not np.all(np.isfinite(b)): raise ValueError("real/imag must be finite same-shaped 2D arrays")
    return np.angle(a+1j*b)

def sensor_spatial_charge(phases:np.ndarray,coordinates:np.ndarray)->float:
    """Estimate vortex charge from phases on finite `(N,3)` sensor coordinates via Delaunay triangles."""
    theta=np.asarray(phases,float); xyz=np.asarray(coordinates,float)
    if theta.ndim!=1 or xyz.ndim!=2 or xyz.shape!=(theta.size,3): raise ValueError("phases must be (N,) and coordinates (N,3)")
    valid=np.isfinite(theta)&np.all(np.isfinite(xyz),axis=1)
    if np.count_nonzero(valid)<3: raise ValueError("at least three finite montage sensors are required")
    points=xyz[valid]; centered=points-points.mean(axis=0); _,_,vh=np.linalg.svd(centered,full_matrices=False); planar=centered@vh[:2].T; simplices=Delaunay(planar).simplices; phase=theta[valid]; wrap=lambda value:(value+np.pi)%(2*np.pi)-np.pi
    total=0.0
    for tri in simplices:
        values=phase[tri]; total+=(wrap(values[1]-values[0])+wrap(values[2]-values[1])+wrap(values[0]-values[2]))/(2*np.pi)
    return float(np.rint(total))
