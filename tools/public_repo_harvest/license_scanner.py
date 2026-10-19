"""Conservative license-record classifier for public repository candidates.

This module does not fetch repositories or inspect license files. A candidate's
``likely_license`` is only a hint; it is never promoted to detected or compatible.
"""
from __future__ import annotations

import argparse
import re

from .common import read_json, write_json

ALLOWED = {"MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "ISC"}
MANUAL = {"MPL-2.0", "LGPL", "EPL", "custom"}
BLOCK = {"GPL", "AGPL", "unknown", "proprietary", "no-license", "UNLICENSED"}


def rec(candidate: dict) -> dict:
    """Normalize candidate declarations without promoting them to review facts.

    This scanner only receives caller-provided metadata; it does not inspect a
    source repository or authenticate a human review. Its output therefore keeps
    those values under ``caller_assertions`` and never authorizes direct reuse.
    """
    if not isinstance(candidate, dict):
        raise ValueError("license candidate must be an object")
    invalid_fields: set[str] = set()
    hint = candidate.get("likely_license", "unknown")
    if not isinstance(hint, str) or not re.fullmatch(r"[A-Za-z0-9.+ -]{1,64}", hint):
        hint = "unknown"
        if "likely_license" in candidate:
            invalid_fields.add("likely_license")
    raw_evidence = candidate.get("detected_licenses", [])
    invalid_evidence = (
        not isinstance(raw_evidence, list)
        or len(raw_evidence) > 64
        or any(not isinstance(item, str) or len(item) > 128 for item in raw_evidence)
    )
    if invalid_evidence:
        invalid_fields.add("detected_licenses")
    evidence = list(raw_evidence) if not invalid_evidence else []
    for key in ("detected_license", "license_spdx"):
        value = candidate.get(key)
        if value is not None and not isinstance(value, str):
            invalid_evidence = True
            invalid_fields.add(key)
        elif isinstance(value, str) and value.strip():
            if re.fullmatch(r"[A-Za-z0-9.+ -]{1,128}", value.strip()):
                evidence.append(value.strip())
            else:
                invalid_evidence = True
                invalid_fields.add(key)
    if any(not re.fullmatch(r"[A-Za-z0-9.+ -]{1,128}", item.strip()) for item in evidence):
        invalid_evidence = True
        invalid_fields.add("detected_licenses")
    detected = sorted(
        {
            item.strip()
            for item in evidence
            if re.fullmatch(r"[A-Za-z0-9.+ -]{1,128}", item.strip())
            and item.strip().upper() not in {"UNKNOWN", "UNLICENSED", "NOASSERTION"}
        },
        key=lambda item: (item.casefold(), item),
    )
    raw_conflicts = candidate.get("conflicting_licenses", [])
    if (
        not isinstance(raw_conflicts, list)
        or len(raw_conflicts) > 64
        or any(not isinstance(item, str) or len(item) > 128 for item in raw_conflicts)
    ):
        invalid_evidence = True
        invalid_fields.add("conflicting_licenses")
        raw_conflicts = []
    raw_conflicting = candidate.get("conflicting", False)
    if not isinstance(raw_conflicting, bool):
        invalid_evidence = True
        invalid_fields.add("conflicting")
        raw_conflicting = True
    conflict = (
        invalid_evidence
        or raw_conflicting
        or bool(raw_conflicts)
        or len(detected) > 1
    )
    asserted_review = candidate.get("review_status")
    asserted_license_status = candidate.get("license_status")
    asserted_compatibility = candidate.get("compatibility_status")
    asserted_copy_code = candidate.get("can_copy_code")
    asserted_copy_docs = candidate.get("can_copy_docs")
    asserted_manual_review = candidate.get("manual_review_required")
    for key, value in (
        ("license_status", asserted_license_status),
        ("compatibility_status", asserted_compatibility),
        ("review_status", asserted_review),
    ):
        if value is not None and (not isinstance(value, str) or len(value) > 128):
            invalid_evidence = True
            invalid_fields.add(key)
    for key, value in (
        ("can_copy_code", asserted_copy_code),
        ("can_copy_docs", asserted_copy_docs),
        ("manual_review_required", asserted_manual_review),
    ):
        if value is not None and not isinstance(value, bool):
            invalid_evidence = True
            invalid_fields.add(key)
    conflict = conflict or invalid_evidence
    restricted = any(
        label.upper() in BLOCK
        or label.upper().startswith(("GPL-", "AGPL-", "LGPL-"))
        for label in detected
    )
    reasons = ["caller_assertions_are_not_review_evidence"]
    if not detected:
        reasons.append("license_label_missing_or_unknown")
    if conflict:
        reasons.append("contradictory_or_malformed_caller_license_metadata")
    if restricted:
        reasons.append("caller_asserted_restricted_license")
    caller_assertions = {
        "likely_license": hint,
        "license_labels": detected,
        "conflicting_licenses": sorted(set(raw_conflicts), key=lambda item: (item.casefold(), item)),
        "license_status": (
            asserted_license_status
            if isinstance(asserted_license_status, str) and len(asserted_license_status) <= 128
            else None
        ),
        "compatibility_status": (
            asserted_compatibility
            if isinstance(asserted_compatibility, str) and len(asserted_compatibility) <= 128
            else None
        ),
        "review_status": (
            asserted_review
            if isinstance(asserted_review, str) and len(asserted_review) <= 128
            else None
        ),
        "can_copy_code": asserted_copy_code if isinstance(asserted_copy_code, bool) else None,
        "can_copy_docs": asserted_copy_docs if isinstance(asserted_copy_docs, bool) else None,
        "manual_review_required": asserted_manual_review if isinstance(asserted_manual_review, bool) else None,
        "invalid_assertion_fields": sorted(invalid_fields),
    }

    return {
        "repo": candidate.get("repo", ""),
        "caller_asserted_license_labels": detected,
        "license_evidence_status": "caller_supplied_unverified",
        "license_spdx": "UNKNOWN",
        "license_status": "unknown",
        "compatibility_status": (
            "blocked_license" if conflict or restricted or not detected else "manual_review_required"
        ),
        "can_copy_code": False,
        "can_copy_docs": False,
        "can_adapt_patterns": False,
        "attribution_required": True,
        "notice_required": True,
        "manual_review_required": True,
        "review_status": "unreviewed",
        "conflicting": conflict,
        "caller_assertions": caller_assertions,
        "decision_rationale": (
            "No authenticated source-license review evidence is available in this offline scanner; "
            "caller declarations remain unverified."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    candidates = read_json(args.candidates)["candidates"]
    write_json(args.out, {"license_matrix": [rec(item) for item in candidates]})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
