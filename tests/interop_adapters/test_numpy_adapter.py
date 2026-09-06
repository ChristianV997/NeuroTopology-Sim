import tempfile
import numpy as np
from pathlib import Path

from shared.interop.adapters.numpy_adapter import NumpyAdapter
from shared.interop.contracts import AdapterStatus

def test_numpy_capability():
    cap = NumpyAdapter.get_capability()
    assert cap.adapter_name == "numpy"
    assert cap.status == AdapterStatus.INTEGRATED
    assert cap.availability is True

def test_numpy_adapter_npy():
    with tempfile.NamedTemporaryFile(suffix=".npy", delete=False) as f:
        path = Path(f.name)
    try:
        # Create dummy data: 3 channels, 100 samples
        data = np.random.randn(3, 100)
        np.save(path, data)
        
        with NumpyAdapter(path, sample_rate_hz=250.0) as adapter:
            chunks = list(adapter.iter_chunks(chunk_size=30))
            
            assert len(chunks) == 4 # 30, 30, 30, 10
            
            # Check first chunk
            assert chunks[0].data.shape == (3, 30)
            assert chunks[0].sample_rate_hz == 250.0
            assert chunks[0].start_sample == 0
            
            # Check last chunk
            assert chunks[3].data.shape == (3, 10)
            assert chunks[3].start_sample == 90
            
        import gc
        gc.collect()
            
    finally:
        path.unlink(missing_ok=True)
