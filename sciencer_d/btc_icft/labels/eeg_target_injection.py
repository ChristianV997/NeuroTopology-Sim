from __future__ import annotations

import csv
import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

_BANNED_PHRASES = (
    "proves consciousness", "consciousness proven", "soul proven", "afterlife proven",
    "liberation detected", "ontology solved", "ultimate reality", "q equals self",
    "q equals soul", "q_abs equals suffering", "f_dress equals karma",
    "sedated implies no_experience", "unresponsive implies unconscious",
)
_JOIN_KEYS = ("dataset_id","row_id","source_file","window_id","window_start_s","window_end_s","sample_start","sample_end")
_M_REQUIRED = {"dataset_id","row_id","source_file","window_id","window_start_s","window_end_s","sample_start","sample_end","n_channels","n_samples","sample_rate_hz","spectral_power_proxy","entropy_proxy","lzc_proxy","artifact_score","feature_status"}
_L_REQUIRED = {"dataset_id","row_id","source_file","window_id","window_start_s","window_end_s","sample_start","sample_end","label","y","label_scope","alignment_status","provenance"}
_ERR = "P9 Level M features and P12 label alignment are required. Run run_eeg_level_m_signal and align_eeg_labels first or use --mock-fixture."

@dataclass
class EEGTargetInjectionRow:
    dataset_id: str; row_id: str; source_file: str; window_id: str
    window_start_s: float; window_end_s: float; sample_start: int; sample_end: int
    y: int | None; label: str | None; target_status: str; provenance: str; warnings: list[str]=field(default_factory=list)

@dataclass
class EEGTargetInjectionResult:
    dataset_id: str; n_m_rows: int; n_label_rows: int; n_labeled_rows: int; n_unlabeled_rows: int; n_rejected_labels: int
    explicit_targets_available: bool; binary_targets_available: bool; class_counts: dict
    labeled_m_rows: list[dict]; target_rows: list[dict]; rejected_rows: list[dict]
    target_injection_report: dict; omega_event: dict; safe_claim: str; forbidden_claims: list[str]; warnings: list[str]

def _validate_safe_text(text:str)->None:
    low=text.lower()
    for p in _BANNED_PHRASES:
        if p in low: raise ValueError(f"Banned phrase detected: {p}")

def _load_csv(path:str, required:set[str], kind:str)->list[dict]:
    p=Path(path)
    if not p.exists(): raise FileNotFoundError(_ERR)
    with p.open("r", newline="", encoding="utf-8") as f:
        r=csv.DictReader(f); rows=list(r); cols=set(r.fieldnames or [])
    miss=sorted(required-cols)
    if miss: raise ValueError(f"{kind} missing required columns: {miss}")
    return rows

def load_level_m_features(path:str)->list[dict]: return _load_csv(path,_M_REQUIRED,"features_m_signal.csv")
def load_label_alignment(path:str)->list[dict]: return _load_csv(path,_L_REQUIRED,"label_alignment.csv")

def _key(r:dict)->tuple: return tuple(str(r.get(k,"")) for k in _JOIN_KEYS)

def _parse_y(v:str)->int|None:
    if v in ("",None): return None
    try:
        y=int(float(v)); return y if y in (0,1) else None
    except Exception: return None

def inject_explicit_targets(m_rows:list[dict], label_rows:list[dict], dataset_id:str)->EEGTargetInjectionResult:
    m_index={_key(r):r for r in m_rows}
    target_rows=[]; rejected=[]; warnings=[]
    label_groups={}
    for lr in label_rows: label_groups.setdefault(_key(lr),[]).append(lr)
    selected={}
    for k, rows in label_groups.items():
        in_m=k in m_index
        aligned=[r for r in rows if r.get("alignment_status")=="aligned"]
        for r in rows:
            if not in_m: rejected.append({**r,"target_status":"rejected_no_matching_m_row"}); continue
            if r.get("alignment_status")!="aligned": rejected.append({**r,"target_status":"rejected_non_aligned_label"})
        if not in_m or not aligned: continue
        valid=[]
        for r in aligned:
            yraw=r.get("y","")
            if yraw in ("",None): rejected.append({**r,"target_status":"rejected_missing_y"}); continue
            y=_parse_y(yraw)
            if y is None: rejected.append({**r,"target_status":"rejected_invalid_y"}); continue
            valid.append((y,r.get("label") or None,r))
        if not valid: continue
        uniq={(y,l) for y,l,_ in valid}
        if len(uniq)>1:
            for _,_,r in valid: rejected.append({**r,"target_status":"rejected_conflicting_target"})
            continue
        if len(valid)>1: warnings.append(f"duplicate_identical_aligned_label:{k}")
        selected[k]=valid[0]
    labeled=[]; c0=c1=0
    for m in m_rows:
        k=_key(m)
        if k in selected:
            y,l,src=selected[k]
            c1+=1 if y==1 else 0; c0+=1 if y==0 else 0
            row={**m,"y":str(y),"label":l or "","target_status":"labeled_explicit_target","target_provenance":src.get("provenance","explicit_p12")}
            tr=EEGTargetInjectionRow(str(m.get("dataset_id","")),str(m.get("row_id","")),str(m.get("source_file","")),str(m.get("window_id","")),float(m.get("window_start_s",0) or 0),float(m.get("window_end_s",0) or 0),int(float(m.get("sample_start",0) or 0)),int(float(m.get("sample_end",0) or 0)),y,l,"labeled_explicit_target",src.get("provenance","explicit_p12"),[])
        else:
            row={**m,"y":"","label":"","target_status":"unlabeled_no_explicit_target","target_provenance":""}
            tr=EEGTargetInjectionRow(str(m.get("dataset_id","")),str(m.get("row_id","")),str(m.get("source_file","")),str(m.get("window_id","")),float(m.get("window_start_s",0) or 0),float(m.get("window_end_s",0) or 0),int(float(m.get("sample_start",0) or 0)),int(float(m.get("sample_end",0) or 0)),None,None,"unlabeled_no_explicit_target","",[])
        labeled.append(row); target_rows.append(asdict(tr))
    res=EEGTargetInjectionResult(dataset_id,len(m_rows),len(label_rows),c0+c1,len(m_rows)-(c0+c1),len(rejected),(c0+c1)>0,c0>0 and c1>0,{"0":c0,"1":c1},labeled,target_rows,rejected,{}, {},"Explicit P12 label targets were injected into Level M signal features for future target-aware signal-level residual testing.",["No consciousness proof.","No self or soul claim.","No liberation or enlightenment claim.","No afterlife claim.","No ontology proof.","No label inference.","No target fabrication.","No sedated/no_experience shortcut.","No unresponsive/unconscious shortcut."],warnings)
    res.target_injection_report=build_target_injection_report(res); res.omega_event=build_target_injection_omega_event(res)
    return res

def build_target_injection_report(result:EEGTargetInjectionResult)->dict:
    status_counts={}
    for r in result.target_rows+result.rejected_rows:
        s=r.get("target_status","unknown"); status_counts[s]=status_counts.get(s,0)+1
    return {"dataset_id":result.dataset_id,"n_m_rows":result.n_m_rows,"n_label_rows":result.n_label_rows,"n_labeled_rows":result.n_labeled_rows,"n_unlabeled_rows":result.n_unlabeled_rows,"n_rejected_labels":result.n_rejected_labels,"explicit_targets_available":result.explicit_targets_available,"binary_targets_available":result.binary_targets_available,"class_counts":result.class_counts,"status_counts":status_counts,"ready_for_target_aware_p11":result.binary_targets_available and result.n_labeled_rows>=2 and result.class_counts.get('0',0)>0 and result.class_counts.get('1',0)>0,"warnings":result.warnings}

def build_target_injection_omega_event(result:EEGTargetInjectionResult)->dict:
    ev={"stage":"btc_icft_p13_eeg_target_injection","dataset_id":result.dataset_id,"safe_claim":result.safe_claim,"forbidden_claims":result.forbidden_claims,"target_injection_report":result.target_injection_report}
    _validate_safe_text(json.dumps(ev))
    return ev

def write_target_injection_outputs(result:EEGTargetInjectionResult, out_dir:str)->dict[str,str]:
    out=Path(out_dir); out.mkdir(parents=True, exist_ok=True); files={}
    mcols=list(result.labeled_m_rows[0].keys()) if result.labeled_m_rows else []
    p=out/"features_m_signal_labeled.csv"
    with p.open("w",newline="",encoding="utf-8") as f: w=csv.DictWriter(f,fieldnames=mcols); w.writeheader(); w.writerows(result.labeled_m_rows)
    files[p.name]=str(p)
    cols=["dataset_id","row_id","source_file","window_id","window_start_s","window_end_s","sample_start","sample_end","y","label","target_status","provenance","warnings"]
    p=out/"target_injection_rows.csv"
    with p.open("w",newline="",encoding="utf-8") as f: w=csv.DictWriter(f,fieldnames=cols); w.writeheader(); w.writerows(result.target_rows)
    files[p.name]=str(p)
    for name,data in [("target_injection_report.json",result.target_injection_report),("rejected_targets.json",{"rejected_rows":result.rejected_rows}),("omega_event.json",result.omega_event)]:
        p=out/name; p.write_text(json.dumps(data,indent=2),encoding="utf-8"); files[name]=str(p)
    report=("# EEG Target Injection for Signal-Level Benchmarking\n\n"
            "## Stage\nP13 target-aware rerun plumbing\n\n## Dataset\n"+result.dataset_id+
            "\n\n## Input Level M features\nfeatures_m_signal.csv\n\n## Input label alignment\nlabel_alignment.csv\n\n"
            f"## Labeled rows\n{result.n_labeled_rows}\n\n## Rejected labels\n{result.n_rejected_labels}\n\n"
            f"## Target availability\nexplicit_targets_available={result.explicit_targets_available}, binary_targets_available={result.binary_targets_available}\n\n"
            f"## Safe claim\n{result.safe_claim}\n\n## Forbidden claims\n"+"\n".join(f"- {x}" for x in result.forbidden_claims)+
            "\n\n## Next required step\nIf ready_for_target_aware_p11 is true, run P11 using features_m_signal_labeled.csv as --m-features.\n")
    _validate_safe_text(report)
    p=out/"report.md"; p.write_text(report,encoding="utf-8"); files[p.name]=str(p)
    return files
