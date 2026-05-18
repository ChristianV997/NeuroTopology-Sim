from __future__ import annotations
import argparse, json
from pathlib import Path

def main(argv=None):
    p=argparse.ArgumentParser(); p.add_argument("--out", required=True); a=p.parse_args(argv)
    out=Path(a.out); out.mkdir(parents=True, exist_ok=True)
    (out/"frontend_api_contract.md").write_text("# Frontend API Contract\n\nEndpoints: /health /status /artifacts/manifest /rag/status /rag/query /rag/sync-plan /local-ops/status /tol/status /guardrails/status /actions/queue\n\n## TypeScript\n```ts\ninterface RagQueryResponse {answer:string; claim_scope:string; evidence_state:string; source_artifacts:string[]; guardrails_applied:string[]; limitations:string[]}\n```\nPolling: status every 15-30s.\nGuardrail badges: no_ontology_promotion, q_qabs_fdress_candidate_telemetry_only, tol_quarantine_respected.\nClaim scope badge: engineering_runtime_or_research_hypothesis.\n")
    (out/"frontend_env_example.md").write_text("VITE_API_BASE_URL=https://your-api-server.example.com\nDo not put OPENAI_API_KEY in frontend.\nFrontend calls backend only.\nLocal dev: http://localhost:8000\n")
    (out/"replit_integration_guide.md").write_text("# Replit Integration Guide\nConfigure API base URL in Replit env.\nUse backend endpoints only.\nDashboard panels: health, status, artifacts, local ops, ToL, guardrails, actions queue.\nRAG chat: call /rag/query in mock mode by default; show citations/source_artifacts and guardrail chips.\nOffline mode supported via mock payloads.\n")
    return 0
if __name__=="__main__": raise SystemExit(main())
