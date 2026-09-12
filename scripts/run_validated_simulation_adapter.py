"""Run one explicitly declared local deterministic simulation workload."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path: sys.path.insert(0, str(ROOT))

from tools.simulation_adapters.adapter import execute_adapter  # noqa: E402
from tools.simulation_adapters.finite import dumps_finite  # noqa: E402
from tools.simulation_adapters.models import AdapterRequest, ResourceBudget  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workload-id", required=True)
    parser.add_argument("--command", required=True, nargs="+")
    parser.add_argument("--output-root", required=True, type=Path)
    parser.add_argument("--code-commit", required=True)
    parser.add_argument("--seed", required=True, type=int)
    parser.add_argument("--input-identity", required=True)
    parser.add_argument("--provenance", required=True, type=Path)
    parser.add_argument("--configuration", required=True, type=Path)
    parser.add_argument("--evidence-class", required=True)
    parser.add_argument("--allow-command", required=True, nargs="+")
    parser.add_argument("--expected-output", action="append", default=["result.json"])
    parser.add_argument("--completion-manifest", default="completion_manifest.json")
    parser.add_argument("--timeout-s", type=float, default=30.0)
    parser.add_argument("--max-output-bytes", type=int)
    parser.add_argument("--allow-network", action="store_true")
    args = parser.parse_args()
    provenance = json.loads(args.provenance.read_text(encoding="utf-8"))
    configuration = json.loads(args.configuration.read_text(encoding="utf-8"))
    request = AdapterRequest.make(workload_id=args.workload_id, command=args.command, allowed_commands={args.workload_id: args.allow_command}, code_commit=args.code_commit, configuration=configuration, seed=args.seed, input_identity=args.input_identity, provenance=provenance, output_root=args.output_root, evidence_class=args.evidence_class, expected_outputs=tuple(dict.fromkeys(args.expected_output)), completion_manifest=args.completion_manifest, resource_budget=ResourceBudget(timeout_s=args.timeout_s, max_output_bytes=args.max_output_bytes), network_disabled=not args.allow_network)
    result = execute_adapter(request)
    print(dumps_finite(result.report), end="")
    return 0 if result.state.value == "PASS" else 2


if __name__ == "__main__": raise SystemExit(main())
