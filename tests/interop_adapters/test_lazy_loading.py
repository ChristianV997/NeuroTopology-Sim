import pytest
from shared.interop.adapters.mne_adapter import MneFifAdapter
from shared.interop.adapters.edf_adapter import EdfAdapter
from shared.interop.adapters.brainvision_adapter import BrainVisionAdapter
from shared.interop.adapters.probes import probe_nwb, probe_brainflow, probe_lsl
from shared.interop.contracts import AdapterStatus

def test_mne_lazy_capability():
    cap = MneFifAdapter.get_capability()
    # Depending on environment, MNE might be unavailable
    # We just ensure it doesn't crash and returns a valid Capability
    assert cap.adapter_name == "mne_fif"
    assert cap.status in (AdapterStatus.INTEGRATED, AdapterStatus.UNAVAILABLE)

def test_edf_lazy_capability():
    cap = EdfAdapter.get_capability()
    assert cap.adapter_name == "edf"
    assert cap.status in (AdapterStatus.INTEGRATED, AdapterStatus.UNAVAILABLE)

def test_brainvision_lazy_capability():
    cap = BrainVisionAdapter.get_capability()
    assert cap.adapter_name == "brainvision"
    assert cap.status in (AdapterStatus.INTEGRATED, AdapterStatus.UNAVAILABLE)

def test_probes_do_not_crash():
    nwb = probe_nwb()
    assert nwb.adapter_name == "nwb"
    
    bf = probe_brainflow()
    assert bf.adapter_name == "brainflow"
    
    lsl = probe_lsl()
    assert lsl.adapter_name == "lsl"
