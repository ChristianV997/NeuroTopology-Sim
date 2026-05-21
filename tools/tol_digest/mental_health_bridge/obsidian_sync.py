from __future__ import annotations
import argparse, json
from pathlib import Path

MAP = {
 "mental_flexibility_master_model.md":"Mental_Flexibility_Master_Model.md",
 "disorder_to_dynamics_matrix.json":"Disorder_to_Dynamics_Matrix.md",
 "ml_feature_schema.json":"ML_Feature_Schema.md",
 "intervention_safety_ladder.md":"Intervention_Safety_Ladder.md",
 "clinical_translation_map.md":"Clinical_Translation_Map.md",
 "body_brain_mind_observable_matrix.json":"Body_Brain_Mind_Observable_Matrix.md",
 "funding_and_product_opportunity_map.md":"Funding_and_Product_Opportunity_Map.md",
 "validation_protocols.md":"Validation_Protocols.md",
}

def sync(root: Path, vault: Path, strict: bool=False) -> dict:
    base=vault/"07_ToL"; base.mkdir(parents=True, exist_ok=True); written=[]; missing=[]
    for src,dst in MAP.items():
        sp=root/src; dp=base/dst
        if sp.exists():
            text=sp.read_text(encoding="utf-8")
            if sp.suffix == ".json": text="```json\n"+text+"\n```\n"
        else:
            missing.append(src); text="# "+dst[:-3].replace("_"," ")+"\n\nnot available\n"
        dp.write_text(text if text.endswith("\n") else text+"\n", encoding="utf-8"); written.append(str(dp))
    return {"ok": not(strict and missing), "missing": missing, "written": written}

def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument("--root", required=True); p.add_argument("--vault", required=True); p.add_argument("--out", required=True); p.add_argument("--strict", action="store_true"); a=p.parse_args(argv)
    res=sync(Path(a.root), Path(a.vault), a.strict); out=Path(a.out); out.parent.mkdir(parents=True, exist_ok=True); out.write_text(json.dumps(res, indent=2, sort_keys=True), encoding="utf-8"); print(json.dumps(res, indent=2)); return 0 if res["ok"] else 1
if __name__ == "__main__": raise SystemExit(main())
