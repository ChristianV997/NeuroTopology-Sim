"""Offline MNE/MNE-BIDS streaming loader with checksum metadata."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator
import hashlib
import numpy as np
@dataclass(frozen=True)
class EEGMetadata:
    sfreq_hz:float; channel_names:tuple[str,...]; montage_coordinates:np.ndarray|None; source:str; sha256:str
def _checksum(path:Path)->str:
    h=hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda:f.read(1024*1024),b""): h.update(block)
    return h.hexdigest()
class StreamingEEG:
    def __init__(self,raw:object,metadata:EEGMetadata): self.raw,self.metadata=raw,metadata
    def iter_chunks(self,chunk_samples:int=4096,*,picks:list[int]|None=None)->Iterator[np.ndarray]:
        if chunk_samples<1: raise ValueError("chunk_samples must be positive")
        for start in range(0,int(self.raw.n_times),chunk_samples):
            x=np.asarray(self.raw.get_data(start=start,stop=min(int(self.raw.n_times),start+chunk_samples),picks=picks),float)
            if x.ndim!=2 or not np.all(np.isfinite(x)): raise ValueError("invalid non-finite EEG chunk")
            yield x
def read_local_raw(path:str|Path,*,preload:bool=False)->StreamingEEG:
    try: import mne
    except ImportError as exc: raise RuntimeError("mne is required") from exc
    p=Path(path)
    if not p.is_file(): raise FileNotFoundError(str(p))
    readers={".vhdr":mne.io.read_raw_brainvision,".edf":mne.io.read_raw_edf,".fif":mne.io.read_raw_fif}
    if p.suffix.lower() not in readers: raise ValueError("supported formats: .vhdr, .edf, .fif")
    raw=readers[p.suffix.lower()](str(p),preload=preload,verbose="ERROR"); montage=None
    # BrainVision headers frequently omit electrode locations.  Bind only
    # matching 10-20 names and leave unmatched channels (e.g. status) NaN.
    if raw.get_montage() is None:
        for standard in ("standard_1005", "standard_1020"):
            try:
                candidate=mne.channels.make_standard_montage(standard); raw.set_montage(candidate,on_missing="ignore",verbose="ERROR")
                if raw.get_montage() is not None: break
            except Exception: continue
    try:
        pos=raw.get_montage().get_positions()["ch_pos"] if raw.get_montage() else {}; montage=np.asarray([pos.get(name,[np.nan]*3) for name in raw.ch_names],float) if pos else None
    except Exception: montage=None
    return StreamingEEG(raw,EEGMetadata(float(raw.info["sfreq"]),tuple(raw.ch_names),montage,str(p.resolve()),_checksum(p)))
def read_bids_raw(root:str|Path,*,subject:str,task:str,run:str|None=None,session:str|None=None,datatype:str="eeg",preload:bool=False)->StreamingEEG:
    try: from mne_bids import BIDSPath,read_raw_bids
    except ImportError as exc: raise RuntimeError("mne-bids is required") from exc
    bp=BIDSPath(root=str(Path(root).resolve()),subject=subject,task=task,run=run,session=session,datatype=datatype); raw=read_raw_bids(bp,verbose="ERROR");
    if preload: raw.load_data()
    return StreamingEEG(raw,EEGMetadata(float(raw.info["sfreq"]),tuple(raw.ch_names),None,str(bp),"bids-source-checksum-unavailable"))
def validate_band_nyquist(metadata:EEGMetadata,high_hz:float)->None:
    if high_hz<=0 or metadata.sfreq_hz/2<high_hz: raise ValueError(f"Nyquist {metadata.sfreq_hz/2:g} Hz below {high_hz:g} Hz")
