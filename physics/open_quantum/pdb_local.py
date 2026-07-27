"""Offline local PDB/TRP centroid parser."""
from __future__ import annotations
from pathlib import Path
import numpy as np
def parse_trp_centroids(path:str|Path,*,coordinate_scale_m:float=1e-10)->np.ndarray:
    """Return TRP residue centroids in metres from a local PDB file."""
    groups:dict[tuple[str,str,int,str],list[list[float]]]={}
    for line in Path(path).read_text(encoding="utf-8",errors="replace").splitlines():
        if not line.startswith(("ATOM","HETATM")) or line[17:20].strip()!="TRP": continue
        try: key=(line[21].strip(),line[22:26].strip(),int(line[22:26]),line[26].strip()); xyz=[float(line[30:38]),float(line[38:46]),float(line[46:54])]
        except (ValueError,IndexError) as exc: raise ValueError("malformed local PDB TRP record") from exc
        groups.setdefault(key,[]).append(xyz)
    if not groups: raise ValueError("no TRP residues found")
    out=np.asarray([np.mean(v,axis=0)*coordinate_scale_m for v in groups.values()],float)
    if not np.all(np.isfinite(out)) or np.any(np.linalg.norm(out,axis=1)>1e-5): raise ValueError("PDB coordinates outside validated bounds")
    return out
def validate_centroids(centroids:np.ndarray)->np.ndarray:
    arr=np.asarray(centroids,float)
    if arr.ndim!=2 or arr.shape[1]!=3 or len(np.unique(arr,axis=0))!=len(arr) or not np.all(np.isfinite(arr)): raise ValueError("centroids must be finite, unique, and shape (N,3)")
    return arr
