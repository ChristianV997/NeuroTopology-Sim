from __future__ import annotations
import argparse, datetime, json
from pathlib import Path
from tools.command_center.guardrails_status import build_guardrails_status

def _read(path: str):
    p = Path(path)
    if not p.exists():
        return {"status": "not_available", "source": path}
    try:
        return {"status": "available", "source": path, "data": json.loads(p.read_text())}
    except Exception:
        return {"status": "not_available", "source": path}

def build_status() -> dict:
    rag_files=["outputs/openai_rag/rag_policy_check.json","outputs/openai_rag/artifact_manifest.json","outputs/openai_rag/sync_plan.json","outputs/openai_rag/rag_status.json","outputs/openai_rag/query_mock_response.json"]
    local_files=["outputs/local_ops/local_ops_status.json","outputs/local_ops/local_ops_healthcheck.json","outputs/local_agents/local_agent_status.json","outputs/local_agents/local_agent_healthcheck.json"]
    tol_files=["outputs/tol_digest/tol_synthesis_validation.json","outputs/tol_digest/tol_digest_validation.json"]
    action_queue=_read("outputs/local_ops/action_queue.json")
    rag=[_read(x) for x in rag_files]; local=[_read(x) for x in local_files]; tol=[_read(x) for x in tol_files]
    warnings=[f"missing:{x['source']}" for x in rag+local+tol+[action_queue] if x['status']!="available"]
    return {
        "ok": True,
        "generated_at": datetime.datetime.utcnow().isoformat()+"Z",
        "system_status": "degraded" if warnings else "ok",
        "rag_status": rag,
        "local_ops_status": local,
        "tol_status": tol,
        "guardrails_status": build_guardrails_status(),
        "action_queue_status": action_queue,
        "next_action": "run_make_command_center_api_smoke",
        "warnings": warnings,
        "source_files": rag_files+local_files+tol_files+["outputs/local_ops/action_queue.json"],
    }

def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument("--out", required=True); a=p.parse_args(argv)
    out=Path(a.out); out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(build_status(), indent=2, sort_keys=True))
    return 0

if __name__=="__main__":
    raise SystemExit(main())
