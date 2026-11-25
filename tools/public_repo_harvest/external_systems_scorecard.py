"""Score candidate repositories without inferring license compatibility."""
from __future__ import annotations

import argparse
from .common import read_json, write_json
from .license_scanner import rec as normalize_license_assertions


def license_fields(candidate: dict) -> dict:
    """Normalize caller claims without treating them as a trusted review record."""
    normalized = normalize_license_assertions(candidate)
    normalized.pop("repo", None)
    return normalized


def scorecard_record(candidate: dict, index: int) -> dict:
    license_data = license_fields(candidate)
    return {
        "id": f"score_{index:03d}",
        "repo_full_name": candidate["repo"],
        "repo_url": f"https://github.com/{candidate['repo']}",
        "source_domain": candidate["domain"],
        **license_data,
        "useful_for_subsystems": ["research_fabric"],
        "reusable_patterns": ["architecture"],
        "copied_artifacts": [],
        "pattern_only_artifacts": ["contracts"],
        "risk_notes": [
            "license hints are not compatibility decisions",
            "no direct copy without authenticated license review evidence",
        ],
        "attribution_required": True,
        "integration_priority": "P1" if candidate["total_priority_score"] > 120 else "P2",
        "claim_scope": "artifact_pattern",
        "evidence_state": "fixture",
        "guardrails": ["no_live_api_default"],
        "next_actions": ["review adapter blueprint"],
        "system_capability": "public_repo_pattern_source",
        "score": candidate["total_priority_score"],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    candidates = read_json(args.candidates)["candidates"]
    rows = [scorecard_record(row, index) for index, row in enumerate(candidates, 1)]
    write_json(args.out, {"external_systems_scorecard": rows})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
