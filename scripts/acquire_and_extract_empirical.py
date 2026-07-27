"""Extract a local ds006623 BOLD pair into bounded-memory 256-node arrays."""
from __future__ import annotations
import argparse
import gzip
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any
import numpy as np

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path: sys.path.insert(0, str(_ROOT))
CANDIDATE_ASSESSMENT: dict[str, dict[str, Any]] = {
 "ds006623":{"modality":"fMRI BOLD","selection":"selected","reason":"3D voxel lattice supports native spatial aggregation to 256 nodes; graded propofol is a stringent contrast.","bias_control":"Selected by modality/density/condition criteria before fitting; no outcome metrics are inspected."},
 "ds005620":{"modality":"EEG","selection":"rejected_for_256_node_runner","reason":"Local BIDS headers report 65 channels, below the current 256-node contract.","bias_control":"High temporal sampling does not compensate for missing spatial nodes."},
 "ds003969":{"modality":"EEG","selection":"not_selected","reason":"Contemplative contrast is hypothesis-adjacent; reserve as preregistered replication.","bias_control":"Avoid choosing a condition aligned with the exceptional-point narrative."}}

def _tr_seconds(image: Any) -> float:
    """Return the BOLD repetition time in seconds."""
    zooms=tuple(float(x) for x in image.header.get_zooms())
    if len(zooms)<4 or not np.isfinite(zooms[3]) or zooms[3]<=0: raise ValueError("NIfTI header lacks a positive TR")
    return zooms[3]

def extract_bold_to_dense(source: str|Path, destination: str|Path, *, target_nodes: int=256) -> dict[str, Any]:
    """Stream a 4D BOLD NIfTI into `(time,256)` NPY, using spatial block means.

    Input scanner amplitudes remain in native arbitrary units. `.nii.gz` data is
    decompressed once to a temporary disk file, then read through a memmapped
    nibabel proxy; RAM does not scale with all time points.
    """
    try: import nibabel as nib
    except ImportError as exc: raise RuntimeError("nibabel is required for NIfTI extraction") from exc
    input_path, output_path=Path(source),Path(destination)
    if not input_path.is_file(): raise FileNotFoundError(f"BOLD input does not exist: {input_path}")
    temporary_nii: Path|None=None
    try:
        if input_path.name.endswith(".nii.gz"):
            handle=tempfile.NamedTemporaryFile(prefix="pitnn_bold_",suffix=".nii",delete=False); temporary_nii=Path(handle.name)
            with handle, gzip.open(input_path,"rb") as compressed: shutil.copyfileobj(compressed,handle,length=4*1024*1024)
            image=nib.load(str(temporary_nii),mmap=True)
        else: image=nib.load(str(input_path),mmap=True)
        if len(image.shape)!=4: raise ValueError(f"expected 4D BOLD image, received shape {image.shape}")
        nx,ny,nz,n_time=(int(x) for x in image.shape); tr=_tr_seconds(image)
        first=np.asarray(image.dataobj[...,0],dtype=np.float32); mask=np.isfinite(first)&(np.abs(first)>0)
        if int(mask.sum())<target_nodes: raise ValueError(f"only {int(mask.sum())} active voxels; need at least {target_nodes}")
        active_mask=mask.ravel(); groups=np.array_split(np.arange(int(active_mask.sum())),target_nodes)
        output_path.parent.mkdir(parents=True,exist_ok=True)
        if output_path.exists(): output_path.unlink()
        dense=np.lib.format.open_memmap(output_path,mode="w+",dtype=np.float32,shape=(n_time,target_nodes))
        for frame in range(n_time):
            values=np.asarray(image.dataobj[...,frame],dtype=np.float32).ravel()[active_mask]
            if not np.all(np.isfinite(values)): raise ValueError(f"non-finite BOLD values at frame {frame}")
            dense[frame]=np.fromiter((float(values[group].mean()) for group in groups),dtype=np.float32,count=target_nodes)
        dense.flush()
        return {"input_file":str(input_path.resolve()),"output_file":str(output_path.resolve()),"input_shape":[nx,ny,nz,n_time],"output_shape":[n_time,target_nodes],"active_voxels":int(mask.sum()),"tr_s":tr,"sample_rate_hz":1.0/tr,"aggregation":"contiguous_active_voxel_block_mean","target_nodes":target_nodes}
    finally:
        if temporary_nii is not None and temporary_nii.exists(): os.unlink(temporary_nii)

def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument("--condition-a-bold",type=Path);parser.add_argument("--condition-b-bold",type=Path);parser.add_argument("--output-dir",type=Path,default=_ROOT/"data"/"empirical");parser.add_argument("--evaluate-only",action="store_true");args=parser.parse_args()
    report: dict[str,Any]={"schema":"PITNN.EmpiricalDatasetSelection.v1","candidates":CANDIDATE_ASSESSMENT,"selected_dataset":"ds006623"}
    if not args.evaluate_only:
        if args.condition_a_bold is None or args.condition_b_bold is None: parser.error("--condition-a-bold and --condition-b-bold are required unless --evaluate-only is set")
        report["condition_a"]=extract_bold_to_dense(args.condition_a_bold,args.output_dir/"condition_A_dense.npy");report["condition_b"]=extract_bold_to_dense(args.condition_b_bold,args.output_dir/"condition_B_dense.npy")
        if not np.isclose(report["condition_a"]["sample_rate_hz"],report["condition_b"]["sample_rate_hz"],rtol=1e-6): raise ValueError("conditions have different TR; resampling must be explicit")
    print(json.dumps(report,indent=2,sort_keys=True));return 0
if __name__=="__main__": raise SystemExit(main())
