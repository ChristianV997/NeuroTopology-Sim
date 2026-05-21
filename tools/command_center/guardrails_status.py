from __future__ import annotations
import argparse, datetime, json
from pathlib import Path

def _read(p: Path):
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text())
    except Exception:
        return None

def build_guardrails_status() -> dict:
    files = [
        Path("outputs/btc_icft/ontology_claim_language_validation.json"),
        Path("outputs/btc_icft/ds005620_generated_language_validation.json"),
        Path("outputs/tol_digest/tol_digest_validation.json"),
        Path("outputs/tol_digest/tol_synthesis_validation.json"),
        Path("outputs/openai_rag/rag_policy_check.json"),
    ]
    warnings=[]; violations=[]; guardrails=[]
    for p in files:
        d = _read(p)
        if d is None:
            warnings.append(f"missing:{p}")
            continue
        ok = d.get("ok", True) if isinstance(d, dict) else True
        guardrails.append({"file": str(p), "ok": bool(ok)})
        if not ok:
            violations.append(str(p))
    return {
        "ok": len(violations) == 0,
        "guardrails": guardrails,
        "violations": violations,
        "warnings": warnings,
        "last_checked": datetime.datetime.utcnow().isoformat() + "Z",
        "safe_to_answer_publicly": len(violations) == 0,
        "safe_to_run_real_data": False,
        "ontology_promotion_allowed": False,
    }

def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument("--out", required=True); a=p.parse_args(argv)
    out=Path(a.out); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(build_guardrails_status(), indent=2, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
