from __future__ import annotations
import argparse, json
from pathlib import Path
from tools.command_center.schemas import with_base
from tools.command_center.guardrails_status import build_guardrails_status

def build_payloads():
    return {
        "health.json": {"ok": True, "service": "command_center"},
        "status.json": with_base({"ok": True, "system_status": "mock_ready"}),
        "artifact_manifest.json": with_base({"ok": True, "artifacts": []}),
        "rag_status.json": with_base({"ok": True, "mode": "mock"}),
        "rag_query_response.json": {
            "answer": "Mock response from indexed project artifacts.",
            "claim_scope": "engineering_runtime_or_research_hypothesis",
            "evidence_state": "artifact_retrieval_only",
            "citations": [],
            "source_artifacts": [],
            "guardrails_applied": ["no_ontology_promotion", "q_qabs_fdress_candidate_telemetry_only", "tol_quarantine_respected"],
            "limitations": ["This response is based on indexed artifacts, not real-data execution."],
        },
        "local_ops_status.json": with_base({"ok": True, "status": "not_available", "note": "No local ops outputs detected."}),
        "tol_status.json": with_base({"ok": True, "status": "not_available", "note": "No ToL outputs detected."}),
        "guardrails_status.json": build_guardrails_status(),
        "action_queue.json": with_base({"ok": True, "items": [], "status": "not_available"}),
    }

def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument("--out", required=True); a=p.parse_args(argv)
    out=Path(a.out); out.mkdir(parents=True, exist_ok=True)
    for name,payload in build_payloads().items():
        (out/name).write_text(json.dumps(payload, indent=2, sort_keys=True))
    return 0
if __name__=="__main__": raise SystemExit(main())
