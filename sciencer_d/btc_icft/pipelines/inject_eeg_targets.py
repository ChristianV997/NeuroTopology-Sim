from __future__ import annotations
import argparse, csv, subprocess, sys, json
from pathlib import Path
from sciencer_d.btc_icft.labels.eeg_target_injection import load_level_m_features, load_label_alignment, inject_explicit_targets, write_target_injection_outputs
ERR="P9 Level M features and P12 label alignment are required. Run run_eeg_level_m_signal and align_eeg_labels first or use --mock-fixture."

def _mock(out:Path,dataset_id:str,binary:bool):
    m=out/".mock"/"features_m_signal.csv"; l=out/".mock"/"label_alignment.csv"; m.parent.mkdir(parents=True,exist_ok=True)
    cols=["dataset_id","row_id","source_file","window_id","window_start_s","window_end_s","sample_start","sample_end","n_channels","n_samples","sample_rate_hz","spectral_power_proxy","entropy_proxy","lzc_proxy","artifact_score","feature_status"]
    with m.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=cols); w.writeheader();
        for i in range(3): w.writerow({c:"" for c in cols}|{"dataset_id":dataset_id,"row_id":f"r{i}","source_file":"f.edf","window_id":f"w{i}","window_start_s":str(i),"window_end_s":str(i+1),"sample_start":str(i*10),"sample_end":str((i+1)*10),"n_channels":"4","n_samples":"10","sample_rate_hz":"100","spectral_power_proxy":"0.1","entropy_proxy":"0.2","lzc_proxy":"0.3","artifact_score":"0.0","feature_status":"ok"})
    lcols=["dataset_id","row_id","source_file","window_id","window_start_s","window_end_s","sample_start","sample_end","label","y","label_scope","alignment_status","provenance"]
    with l.open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=lcols); w.writeheader();
        w.writerow({"dataset_id":dataset_id,"row_id":"r0","source_file":"f.edf","window_id":"w0","window_start_s":"0","window_end_s":"1","sample_start":"0","sample_end":"10","label":"target","y":"1","label_scope":"window","alignment_status":"aligned","provenance":"p12"})
        if binary: w.writerow({"dataset_id":dataset_id,"row_id":"r1","source_file":"f.edf","window_id":"w1","window_start_s":"1","window_end_s":"2","sample_start":"10","sample_end":"20","label":"control","y":"0","label_scope":"window","alignment_status":"aligned","provenance":"p12"})
    return str(m),str(l)

def run(args):
    if args.mock_fixture: m,l=_mock(Path(args.out),args.dataset_id,args.mock_binary_targets)
    else:
        if not args.m_features or not args.label_alignment: print(ERR); return 1
        m,l=args.m_features,args.label_alignment
    try:
        mr=load_level_m_features(m); lr=load_label_alignment(l)
    except (FileNotFoundError,ValueError) as e: print(str(e)); return 1
    result=inject_explicit_targets(mr,lr,args.dataset_id); out=write_target_injection_outputs(result,args.out)
    print(json.dumps(result.target_injection_report))
    if args.run_p11_smoke:
        if not result.target_injection_report.get("ready_for_target_aware_p11"):
            print("Target-aware P11 requires explicit binary targets. Run with valid label alignment or --mock-binary-targets."); return 1
        if not args.t_features: print("--t-features required with --run-p11-smoke"); return 1
        cmd=[sys.executable,"-m","sciencer_d.btc_icft.pipelines.run_eeg_signal_mt","--m-features",out["features_m_signal_labeled.csv"],"--t-features",args.t_features,"--out",args.p11_out]
        return subprocess.run(cmd).returncode
    return 0

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--dataset-id",default="DS005620"); ap.add_argument("--m-features"); ap.add_argument("--label-alignment"); ap.add_argument("--out",default="outputs/btc_icft/eeg_targets/DS005620"); ap.add_argument("--mock-fixture",action="store_true"); ap.add_argument("--mock-binary-targets",action="store_true"); ap.add_argument("--run-p11-smoke",action="store_true"); ap.add_argument("--t-features"); ap.add_argument("--p11-out",default="outputs/btc_icft/eeg_signal_mt_targeted/DS005620"); return run(ap.parse_args())
if __name__=='__main__': raise SystemExit(main())
