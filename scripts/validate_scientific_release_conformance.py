"""Run the scientific-release conformance fixture battery and emit one
machine-readable report.

Consumes the real, canonical, already-merged
``tools/research_claim_gate/gate.py`` and
``tools/simulation_artifacts/extractor.py`` as read-only dependencies --
this script does not modify or duplicate either implementation, and
performs no network access, no dataset download, and no simulation
execution of its own. Every fixture is local, synthetic, and
deterministic.

Usage
-----
    python -m scripts.validate_scientific_release_conformance --output-dir artifacts/scientific_release_conformance
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

from tools.research_claim_gate.gate import evaluate_claim  # noqa: E402
from tools.simulation_artifacts.extractor import extract_run  # noqa: E402

_FIXTURES_DIR = _REPO_ROOT / "tests" / "release_readiness" / "scientific_conformance" / "fixtures"
_SIMULATION_RUNS_DIR = _FIXTURES_DIR / "simulation_runs"
_BASELINE_FIXTURE = "accepted_baseline"

_DECISION_BUCKET = {
    "CLAIM_REQUIRES_REVIEW": "REVIEW_REQUIRED",
    "CLAIM_DOWNGRADED": "DOWNGRADED",
    "CLAIM_REJECTED": "BLOCKED",
    "CLAIM_INCOMPLETE": "INCOMPLETE",
    "CLAIM_SYNTHETIC_ONLY": "BLOCKED",
    "CLAIM_PROVENANCE_INVALID": "BLOCKED",
    "CLAIM_NOT_COMPARABLE": "BLOCKED",
}

_ARTIFACT_INCOMPLETE_STATUSES = {"INCOMPLETE", "PARTIAL", "FAILED", "CONFLICTING", "BLOCKED"}


def _run_claim_gate_cases() -> list[dict[str, Any]]:
    cases = []
    for path in sorted(_FIXTURES_DIR.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        result = evaluate_claim(raw)
        cases.append(
            {
                "fixture": path.stem,
                "is_adversarial": path.stem != _BASELINE_FIXTURE,
                "decision": result.decision,
                "bucket": _DECISION_BUCKET.get(result.decision),
                "reason_codes": list(result.reason_codes),
                "scientific_pass": result.scientific_pass,
                "formal_bayes_factor": result.formal_bayes_factor,
                "network_access_performed": result.network_access_performed,
            }
        )
    return cases


def _run_simulation_artifact_cases() -> list[dict[str, Any]]:
    cases = []
    if not _SIMULATION_RUNS_DIR.is_dir():
        return cases
    for run_dir in sorted(p for p in _SIMULATION_RUNS_DIR.iterdir() if p.is_dir()):
        report = extract_run(run_dir)
        cases.append(
            {
                "fixture": run_dir.name,
                "is_adversarial": run_dir.name != "complete_run",
                "status": report["status"],
                "read_only": report["read_only"],
                "solver_executed": report["solver_executed"],
                "heavy_runtime_imported": report["heavy_runtime_imported"],
                "evidence_class": report["evidence"]["evidence_class"],
                "synthetic": report["evidence"]["synthetic"],
            }
        )
    return cases


def _finite_json(value: Any) -> str:
    return json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n"


def build_report(*, now: str | None = None) -> dict[str, Any]:
    generated_at = now if now is not None else datetime.now(timezone.utc).isoformat()

    claim_gate_cases = _run_claim_gate_cases()
    simulation_artifact_cases = _run_simulation_artifact_cases()

    adversarial_claims = [c for c in claim_gate_cases if c["is_adversarial"]]
    adversarial_runs = [c for c in simulation_artifact_cases if c["is_adversarial"]]

    all_adversarial_claims_rejected = all(c["decision"] != "CLAIM_ADMISSIBLE" for c in adversarial_claims)
    all_adversarial_claims_bucketed = all(c["bucket"] in {"BLOCKED", "INCOMPLETE", "DOWNGRADED", "REVIEW_REQUIRED"} for c in adversarial_claims)
    all_adversarial_runs_incomplete = all(c["status"] in _ARTIFACT_INCOMPLETE_STATUSES for c in adversarial_runs)
    no_scientific_pass_anywhere = all(c["scientific_pass"] is False for c in claim_gate_cases)
    no_formal_bayes_factor_anywhere = all(c["formal_bayes_factor"] is None for c in claim_gate_cases)
    no_network_access_performed = all(c["network_access_performed"] is False for c in claim_gate_cases)
    baseline_case = next((c for c in claim_gate_cases if c["fixture"] == _BASELINE_FIXTURE), None)
    baseline_admitted = baseline_case is not None and baseline_case["decision"] == "CLAIM_ADMISSIBLE"

    conformant = (
        all_adversarial_claims_rejected
        and all_adversarial_claims_bucketed
        and all_adversarial_runs_incomplete
        and no_scientific_pass_anywhere
        and no_formal_bayes_factor_anywhere
        and no_network_access_performed
        and baseline_admitted
    )

    report: dict[str, Any] = {
        "schema_version": "NeuroTopology.ScientificReleaseConformance.v1",
        "evidence_class": "scientific_release_conformance",
        "generated_at": generated_at,
        "conformant": conformant,
        "invariants": {
            "all_adversarial_claims_rejected": all_adversarial_claims_rejected,
            "all_adversarial_claims_bucketed": all_adversarial_claims_bucketed,
            "all_adversarial_simulation_runs_incomplete": all_adversarial_runs_incomplete,
            "no_scientific_pass_anywhere": no_scientific_pass_anywhere,
            "no_formal_bayes_factor_anywhere": no_formal_bayes_factor_anywhere,
            "no_network_access_performed": no_network_access_performed,
            "accepted_baseline_admitted": baseline_admitted,
        },
        "claim_gate_cases": claim_gate_cases,
        "simulation_artifact_cases": simulation_artifact_cases,
        "summary": {
            "claim_gate_cases_total": len(claim_gate_cases),
            "claim_gate_adversarial_total": len(adversarial_claims),
            "simulation_artifact_cases_total": len(simulation_artifact_cases),
            "simulation_artifact_adversarial_total": len(adversarial_runs),
        },
        "note": "This report describes engineering-level conformance of the claim gate and simulation-artifact extractor against adversarial fixtures. It is not itself a scientific finding and never certifies scientific truth.",
    }
    canonical = json.dumps(report, sort_keys=True, allow_nan=False)
    report["report_sha256"] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return report


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output-dir", required=True, type=Path, help="Directory to write the conformance report into.")
    parser.add_argument("--now", default=None, help="ISO-8601 timestamp to stamp the report with (default: current UTC time).")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    report = build_report(now=args.now)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "scientific_release_conformance_report.json").write_text(_finite_json(report), encoding="utf-8")

    print(f"conformant={report['conformant']} claim_gate_cases={report['summary']['claim_gate_cases_total']} simulation_cases={report['summary']['simulation_artifact_cases_total']}")
    for name, value in report["invariants"].items():
        print(f"  {name}: {value}")

    return 0 if report["conformant"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
