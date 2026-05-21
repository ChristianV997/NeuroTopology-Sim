from __future__ import annotations
import argparse, json
from pathlib import Path


def build_openapi():
    paths = {}
    req = ["/health", "/status", "/artifacts/manifest", "/rag/status", "/rag/query", "/rag/sync-plan", "/local-ops/status", "/tol/status", "/guardrails/status", "/actions/queue"]
    for p in req:
        method = "post" if p in {"/rag/query", "/rag/sync-plan"} else "get"
        op = {
            "responses": {
                "200": {
                    "description": "OK",
                    "content": {
                        "application/json": {
                            "schema": {
                                "type": "object",
                                "properties": {
                                    "claim_scope": {"type": "string"},
                                    "evidence_state": {"type": "string"},
                                    "source_artifacts": {"type": "array", "items": {"type": "string"}},
                                },
                            }
                        }
                    },
                }
            }
        }
        if p == "/rag/query":
            op["requestBody"] = {
                "required": True,
                "content": {
                    "application/json": {
                        "schema": {
                            "type": "object",
                            "required": ["query", "mode"],
                            "properties": {
                                "query": {"type": "string"},
                                "mode": {"type": "string", "enum": ["mock", "dry_run", "live"]},
                            },
                        }
                    }
                },
            }
        paths[p] = {method: op}
    return {"openapi": "3.1.0", "info": {"title": "ScienceR-Dsim Command Center API", "version": "1.0.0"}, "paths": paths}


def main(argv=None):
    p = argparse.ArgumentParser(); p.add_argument("--out", required=True); a = p.parse_args(argv)
    out = Path(a.out); out.parent.mkdir(parents=True, exist_ok=True)
    spec = build_openapi()
    out.write_text(json.dumps(spec, indent=2, sort_keys=True))
    Path("docs/command_center_api_openapi_schema.yaml").write_text(json.dumps(spec, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
