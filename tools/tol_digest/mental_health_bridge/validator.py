from __future__ import annotations
import argparse, json, re
from pathlib import Path
from .generator import REQUIRED_OUTPUTS

FORBIDDEN = {
    "diagnosis claim": [r"\bdiagnoses\b", r"\bdiagnose depression\b", r"\bdiagnostic product\b"],
    "intervention efficacy/cure claim": [r"\bsystem treats\b", r"\btreat depression\b", r"\bis a treatment\b", r"\bprovides treatment\b", r"\bcures\b", r"\bcurative\b"],
    "AI therapist framing": [r"\bAI therapist\b"],
    "clinician replacement": [r"\breplaces clinician\b", r"\breplace clinicians\b"],
    "trauma deletion": [r"trauma deletion"],
    "instant arhat": [r"instant arhat"],
    "mechanical enlightenment": [r"mechanical enlightenment"],
    "Q proves": [r"\bQ proves\b", r"\bQabs proves\b", r"\bfdress proves\b", r"Qabs proves liberation"],
    "enlightenment detector": [r"enlightenment detector"],
    "soul metric": [r"soul metric"],
}
ALLOW_CONTEXT = ["does not", "must not", "prohibit", "forbidden", "blocked", "no ", "without making", "allowed = false", "allowed=false"]

def _text_files(root: Path):
    for p in root.rglob("*") if root.exists() else []:
        if p.name == "mental_health_bridge_validation.json":
            continue
        if p.is_file() and p.suffix.lower() in {".md", ".json", ".txt"}:
            yield p

def _line_allowed(line: str) -> bool:
    l=line.lower()
    if l.startswith("trauma deletion;"):
        return True
    return any(a in l for a in ALLOW_CONTEXT)

def validate(root: Path) -> dict:
    errors=[]; warnings=[]; checked=[]
    for name in REQUIRED_OUTPUTS:
        if not (root/name).exists(): errors.append(f"missing:{name}")
    for p in _text_files(root):
        checked.append(str(p))
        for i,line in enumerate(p.read_text(encoding="utf-8").splitlines(),1):
            for cat, pats in FORBIDDEN.items():
                if any(re.search(pat,line,re.I) for pat in pats) and not _line_allowed(line):
                    errors.append(f"{cat}:{p.name}:{i}")
    ml=root/"ml_feature_schema.json"
    if ml.exists():
        try:
            data=json.loads(ml.read_text(encoding="utf-8"))
            for idx,row in enumerate(data):
                if "privacy_risk" not in row: errors.append(f"ml_feature_schema missing privacy_risk at {idx}")
                if "allowed_mode" not in row: errors.append(f"ml_feature_schema missing allowed_mode at {idx}")
        except Exception as e: errors.append(f"ml_feature_schema invalid:{e}")
    dm=root/"disorder_to_dynamics_matrix.json"
    if dm.exists():
        txt=dm.read_text(encoding="utf-8").lower()
        if "candidate mapping" not in txt and "research hypothesis" not in txt: errors.append("disorder matrix lacks candidate mapping/research hypothesis")
    ladder=root/"intervention_safety_ladder.md"
    if ladder.exists() and "Emergency boundary" not in ladder.read_text(encoding="utf-8"): errors.append("intervention ladder missing emergency boundary")
    clinical=root/"clinical_translation_map.md"
    if clinical.exists():
        t=clinical.read_text(encoding="utf-8").lower()
        for term in ["research mode","wellness mode","clinician-support candidate mode","medical device / samd candidate mode","regulatory boundary"]:
            if term not in t: errors.append(f"clinical modes not separated:{term}")
    protocols=root/"validation_protocols.md"
    if protocols.exists() and "falsifiers" not in protocols.read_text(encoding="utf-8").lower(): errors.append("validation protocols missing falsifiers")
    report=root/"mental_health_bridge_report.md"
    if report.exists() and "guardrails" not in report.read_text(encoding="utf-8").lower(): errors.append("report missing guardrails")
    return {"ok": not errors, "errors": errors, "warnings": warnings, "checked_files": checked}

def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument("--root", required=True); p.add_argument("--json-out", required=True); a=p.parse_args(argv)
    try:
        res=validate(Path(a.root)); out=Path(a.json_out); out.parent.mkdir(parents=True, exist_ok=True); out.write_text(json.dumps(res, indent=2, sort_keys=True), encoding="utf-8"); print(json.dumps(res, indent=2)); return 0 if res["ok"] else 1
    except Exception as e:
        res={"ok": False, "errors": [f"internal/config error:{e}"], "warnings": [], "checked_files": []}; Path(a.json_out).parent.mkdir(parents=True, exist_ok=True); Path(a.json_out).write_text(json.dumps(res, indent=2), encoding="utf-8"); print(json.dumps(res, indent=2)); return 2
if __name__ == "__main__": raise SystemExit(main())
