from __future__ import annotations
import argparse, datetime, hashlib, json, mimetypes
from pathlib import Path

def _sha(path: Path) -> str:
    h=hashlib.sha256(); h.update(path.read_bytes()); return h.hexdigest()

def _excluded(path: str, excludes: list[str]) -> bool:
    p = Path(path)
    return any(p.match(e) or e in path for e in excludes)

def build_manifest(config_path: str) -> list[dict]:
    cfg = json.loads(Path(config_path).read_text())
    recs=[]
    for g in cfg["groups"]:
      for pat in g["patterns"]:
        matches=list(Path('.').glob(pat))
        if not matches: matches=[Path(pat)]
        for m in matches:
          rel=str(m).replace('\\','/')
          ex=_excluded(rel,cfg.get("exclude_patterns",[]))
          exists=m.exists()
          quarantine = rel.endswith("quarantine_report.md")
          allowed = exists and (not ex) and (quarantine or "inputs/tol/" not in rel)
          recs.append({"artifact_id": hashlib.sha256(rel.encode()).hexdigest()[:16], "path": rel, "group": g["name"], "exists": exists, "size_bytes": m.stat().st_size if exists else 0, "sha256": _sha(m) if exists and m.is_file() else "", "content_type": mimetypes.guess_type(rel)[0] or "text/plain", "claim_scope": "quarantine_context" if quarantine else g.get("claim_scope","hypothesis"), "allowed_for_rag": allowed, "quarantine_required": quarantine, "reason": "excluded" if ex else ("missing" if not exists else "allowed"), "last_modified": datetime.datetime.utcfromtimestamp(m.stat().st_mtime).isoformat()+"Z" if exists else None})
    return recs

def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument('--config',required=True); p.add_argument('--out',required=True); a=p.parse_args(argv)
    out=Path(a.out); out.mkdir(parents=True,exist_ok=True)
    recs=build_manifest(a.config)
    (out/'artifact_manifest.json').write_text(json.dumps({"generated_at": datetime.datetime.utcnow().isoformat()+"Z", "artifacts": recs}, indent=2))
    md=["# OpenAI RAG Artifact Manifest", "", f"Total: {len(recs)}"]+[f"- `{r['path']}` | allowed={r['allowed_for_rag']} | reason={r['reason']}" for r in recs]
    (out/'artifact_manifest.md').write_text('\n'.join(md))
    return 0
if __name__=='__main__': raise SystemExit(main())
