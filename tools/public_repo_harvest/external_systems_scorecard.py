"""Score candidate repositories without inferring license compatibility."""
from __future__ import annotations

import argparse
import re

from .common import read_json, write_json
from .license_scanner import ALLOWED, BLOCK


def license_fields(candidate: dict) -> dict:
    """Use explicit, reviewed license fields; never promote a likely-license hint."""
    detected = candidate.get("detected_license", "unknown")
    if not isinstance(detected, str) or not detected.strip():
        detected = "unknown"
    else:
        detected = detected.strip()
    spdx = candidate.get("license_spdx", detected)
    status = candidate.get("license_status", "unknown")
    compatibility = candidate.get("compatibility_status", "manual_review_required")
    review = candidate.get("review_status", "unreviewed")
    detected_list = candidate.get("detected_licenses", [])
    if not isinstance(detected_list, list) or any(not isinstance(value, str) for value in detected_list):
        conflicting = True
    else:
        normalized = {value.strip() for value in detected_list if value.strip()}
        conflicting = len(normalized) > 1 or bool(normalized and detected not in normalized)
    conflicting = conflicting or candidate.get("conflicting") is True or bool(candidate.get("conflicting_licenses"))
    if not isinstance(spdx, str):
        spdx = "UNKNOWN"
    if (
        detected.casefold() not in {"unknown", "unlicensed"}
        and spdx.casefold() not in {"unknown", "unlicensed"}
        and detected != spdx
    ):
        conflicting = True
    hint = candidate.get("likely_license", "unknown")
    if not isinstance(hint, str) or not re.fullmatch(r"[A-Za-z0-9.+ -]{1,64}", hint):
        hint = "unknown"
    can_copy = (
        isinstance(detected, str)
        and detected in ALLOWED
        and spdx == detected
        and status == "compatible"
        and compatibility == "safe_to_adapt"
        and review == "human_reviewed_compatible"
        and candidate.get("can_copy_code") is True
        and candidate.get("manual_review_required") is False
        and not conflicting
    )
    if conflicting:
        status, compatibility = "needs_manual_review", "blocked_license"
        detected, spdx = "unknown", "UNKNOWN"
    elif detected in {None, "", "unknown", "UNKNOWN", "UNLICENSED"}:
        status, compatibility = "unknown", "blocked_license"
        detected, spdx = "unknown", "UNKNOWN"
        can_copy = False
    elif review == "human_reviewed_incompatible" or detected in BLOCK:
        status, compatibility = "incompatible", "blocked_license"
        can_copy = False
    elif not can_copy:
        status, compatibility = "needs_manual_review", "manual_review_required"
        can_copy = False
    return {
        "license_name": detected,
        "license_spdx": spdx,
        "license_status": status,
        "compatibility_status": compatibility,
        "can_copy_code": can_copy,
        "conflicting": conflicting,
        "license_hint": hint,
    }


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
        "risk_notes": ["license hints are not compatibility decisions", "no direct copy without human review"],
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
