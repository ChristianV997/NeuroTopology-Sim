"""Run streaming 256-channel MEG/fMRI falsification without network access."""
from __future__ import annotations
import argparse,json,sys
from pathlib import Path
import numpy as np
_ROOT=Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path: sys.path.insert(0,str(_ROOT))
from sim.pitnn.api_bridge import export_falsification_payload
from sim.pitnn.bayesian_falsification import compare_models
from sim.pitnn.meg_ingestor import iter_rg_fields, synthetic_meg_256
from sim.pitnn.mumax3_macro_tda import invert_macro_signal
from sim.pitnn.topological_invariants import TopologicalInvariantTracker

def run_meg_falsification(input_file: str|Path|None=None, sample_rate_hz: float=1000.0, block_size:int=4, chunk_samples:int=256, output_dir:str|Path="artifacts/pitnn/dsim_export", seed:int=0)->dict:
    """Stream local 256-channel data; synthetic fixtures never assert evidence."""
    if sample_rate_hz<=0: raise ValueError("sample_rate_hz must be positive")
    destination=Path(output_dir); destination.mkdir(parents=True,exist_ok=True)
    if input_file is None:
        source_kind="synthetic_demo"; source=destination/"meg_synthetic_256.npy"; np.save(source,synthetic_meg_256(seed=seed))
    else: source_kind="empirical_local"; source=Path(input_file)
    q_values=[]; beta_values=[]; trace=[]; frames=0
    for field in iter_rg_fields(source,block_size,chunk_samples):
        tracker=TopologicalInvariantTracker(field.shape[1])
        for frame in field:
            audit=tracker.audit_snapshot(frame); q_values.append(audit["topological_charge"]); beta_values.append(audit["beta1_loops"])
            if len(trace)<4096: trace.append({"time_s":frames/sample_rate_hz,"winding_number":audit["winding_number"],"topological_charge":audit["topological_charge"],"beta1_loops":audit["beta1_loops"]})
            frames+=1
    q=np.asarray(q_values,dtype=float)
    inversion={**invert_macro_signal(q,sample_rate_hz),"q_emp_mean":float(q.mean()),"beta1_mean":float(np.mean(beta_values))}
    comparison=compare_models(q,inversion)
    report={"schema":"PITNN.HighDensityMEGFalsification.v1","source_kind":source_kind,"input_file":str(source),"channels":256,"block_size":block_size,"coarse_sites":256//block_size,"chunk_samples":chunk_samples,"frames":frames,"topology_trace":trace,"mean_q":float(q.mean()),"mean_beta1":float(np.mean(beta_values)),"comparison":comparison,"bayes_factor":float(comparison["bayes_factor"]),"delta_aicc":float(comparison["classical_wilson_cowan"]["aicc"]-comparison["pitnn"]["aicc"]),"verdict":comparison["verdict"],"scientific_note":"Streaming RG result; PASS is emitted only by the unmodified K>100 gate."}
    (destination/"meg_falsification_report.json").write_text(json.dumps(report,indent=2,sort_keys=True),encoding="utf-8")
    return report

def main()->int:
    p=argparse.ArgumentParser(description=__doc__); p.add_argument("--input-file",type=Path);p.add_argument("--sample-rate-hz",type=float,default=1000.0);p.add_argument("--block-size",type=int,default=4);p.add_argument("--chunk-samples",type=int,default=256);p.add_argument("--output-dir",type=Path,default=Path("artifacts/pitnn/dsim_export"));p.add_argument("--seed",type=int,default=0);a=p.parse_args();r=run_meg_falsification(**vars(a));print(json.dumps({"K":r["bayes_factor"],"verdict":r["verdict"],"frames":r["frames"]},sort_keys=True));return 0
if __name__=="__main__":raise SystemExit(main())
