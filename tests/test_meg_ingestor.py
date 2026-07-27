import numpy as np
from scripts.run_meg_falsification import run_meg_falsification
from sim.pitnn.meg_ingestor import iter_rg_fields, sensor_coordinates, synthetic_meg_256

def test_sensor_geometry_and_streaming_rg(tmp_path):
    source=tmp_path/"meg.npy"; np.save(source,synthetic_meg_256(512,seed=2))
    fields=list(iter_rg_fields(source,block_size=4,chunk_samples=128))
    assert sensor_coordinates().shape==(256,3)
    assert sum(field.shape[0] for field in fields)==512
    assert all(field.shape[1:]==(64,3) for field in fields)

def test_meg_falsification_guardrail(tmp_path):
    source=tmp_path/"meg.npy"; np.save(source,synthetic_meg_256(512,seed=3))
    report=run_meg_falsification(source,sample_rate_hz=1000.0,block_size=8,chunk_samples=128,output_dir=tmp_path)
    assert report["channels"]==256 and report["coarse_sites"]==32
    assert report["verdict"]=="NOT_SUPPORTED" and report["bayes_factor"]<=100.0
    assert (tmp_path/"meg_falsification_report.json").is_file()
