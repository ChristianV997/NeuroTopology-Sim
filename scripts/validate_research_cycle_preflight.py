"""Run the research-cycle preflight and emit one machine-readable report.

Consumes the real, canonical, already-merged
``tools/research_plan_quality`` rubric, ``tools/research_claim_gate``
gate, ``tools/simulation_artifacts`` extractor, and
``tools/data_access/policy_enforcement`` policy as read-only
dependencies -- this script does not modify or duplicate any of them,
and performs no network access, no dataset download, and no simulation
execution of its own.

Usage
-----
Run the preflight against one declared request::

    python -m scripts.validate_research_cycle_preflight \\
        --request path/to/request.json --output-dir artifacts/research_cycle_preflight

Or run this suite's own fixture battery as a self-check (no --request)::

    python -m scripts.validate_research_cycle_preflight --output-dir artifacts/research_cycle_preflight
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from tools.research_cycle_preflight.compose import run_preflight  # noqa: E402

_FIXTURES_DIR = _REPO_ROOT / "tests" / "research_cycle_preflight" / "fixtures"
_PRIOR_RUNS_DIR = _FIXTURES_DIR / "prior_runs"


def _resolve_prior_run_dir(request: dict[str, Any]) -> dict[str, Any]:
    """This suite's own fixtures store ``prior_run_dir`` as a bare
    directory name under ``fixtures/prior_runs/`` so the fixtures stay
    portable; resolve that to a real path before running. A caller's
    own ``--request`` file is expected to already carry a real path and
    is passed through unchanged.
    """
    if "prior_run_dir" in request:
        request = dict(request)
        request["prior_run_dir"] = str(_PRIOR_RUNS_DIR / request["prior_run_dir"])
    return request


def _finite_json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"


def _self_check_report(*, now: str | None) -> dict[str, Any]:
    generated_at = now if now is not None else datetime.now(timezone.utc).isoformat()
    cases = []
    for path in sorted(_FIXTURES_DIR.glob("*.json")):
        request = _resolve_prior_run_dir(json.loads(path.read_text(encoding="utf-8")))
        result = run_preflight(request, now=generated_at)
        cases.append(
            {
                "fixture": path.stem,
                "operational_readiness": result["operational_readiness"],
                "scientific_admissibility": result["scientific_admissibility"],
                "cleared_for_execution": result["cleared_for_execution"],
                "operational_blockers": result["operational_blockers"],
            }
        )
    report: dict[str, Any] = {
        "schema_version": "NeuroTopology.ResearchCyclePreflightSelfCheck.v1",
        "evidence_class": "research_cycle_preflight_self_check",
        "generated_at": generated_at,
        "case_count": len(cases),
        "cases": cases,
    }
    canonical = json.dumps(report, sort_keys=True, allow_nan=False)
    report["report_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output-dir", required=True, type=Path, help="Directory to write the preflight report into.")
    parser.add_argument("--now", default=None, help="ISO-8601 timestamp to stamp the report with (default: current UTC time).")
    parser.add_argument(
        "--request", default=None, type=Path,
        help="Path to a single JSON preflight request (plan/claim/prior_run_dir/data_access_request). "
        "If omitted, runs this suite's own fixture battery as a self-check.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    if args.request is not None:
        request = json.loads(args.request.read_text(encoding="utf-8"))
        report = run_preflight(request, now=args.now)
        (args.output_dir / "research_cycle_preflight_report.json").write_text(_finite_json(report), encoding="utf-8")
        print(
            f"cleared_for_execution={report['cleared_for_execution']} "
            f"operational_readiness={report['operational_readiness']} "
            f"scientific_admissibility={report['scientific_admissibility']}"
        )
        for blocker in report["operational_blockers"]:
            print(f"  blocker: {blocker}")
        return 0 if report["cleared_for_execution"] else 1

    report = _self_check_report(now=args.now)
    (args.output_dir / "research_cycle_preflight_self_check.json").write_text(_finite_json(report), encoding="utf-8")
    print(f"self_check_cases={report['case_count']}")
    for case in report["cases"]:
        print(f"  {case['fixture']}: cleared_for_execution={case['cleared_for_execution']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
