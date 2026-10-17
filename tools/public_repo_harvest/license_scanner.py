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
    """Preserve license evidence and block copy unless compatibility was reviewed.

    A detected license identifier is evidence of a label, not a legal
    compatibility decision. Human-reviewed compatibility requires all explicit
    fields; likely-license metadata alone remains unknown and blocked.
    """
    if not isinstance(candidate, dict):
        raise ValueError("license candidate must be an object")
    hint = candidate.get("likely_license", "unknown")
    if not isinstance(hint, str) or not re.fullmatch(r"[A-Za-z0-9.+ -]{1,64}", hint):
        hint = "unknown"
    evidence = candidate.get("detected_licenses", [])
    invalid_evidence = not isinstance(evidence, list) or any(not isinstance(item, str) for item in evidence)
    if invalid_evidence:
        evidence = []
    else:
        evidence = list(evidence)
    for key in ("detected_license", "license_spdx"):
        value = candidate.get(key)
        if value is not None and not isinstance(value, str):
            invalid_evidence = True
        elif isinstance(value, str) and value.strip():
            if re.fullmatch(r"[A-Za-z0-9.+ -]{1,128}", value.strip()):
                evidence.append(value.strip())
            else:
                invalid_evidence = True
    if any(not re.fullmatch(r"[A-Za-z0-9.+ -]{1,128}", item.strip()) for item in evidence):
        invalid_evidence = True
    detected = sorted(
        {
            item.strip()
            for item in evidence
            if re.fullmatch(r"[A-Za-z0-9.+ -]{1,128}", item.strip())
            and item.strip().upper() not in {"UNKNOWN", "UNLICENSED", "NOASSERTION"}
        },
        key=lambda item: (item.casefold(), item),
    )
    conflict = (
        invalid_evidence
        or bool(candidate.get("conflicting", False))
        or bool(candidate.get("conflicting_licenses"))
        or len(detected) > 1
    )
    review_status = candidate.get("review_status", "unreviewed")
    if not isinstance(review_status, str) or review_status not in {"unreviewed", "human_reviewed_compatible", "human_reviewed_incompatible"}:
        review_status = "unreviewed"
    reviewed_compatible = (
        len(detected) == 1
        and detected[0] in ALLOWED
        and candidate.get("license_status") == "compatible"
        and candidate.get("compatibility_status") == "safe_to_adapt"
        and review_status == "human_reviewed_compatible"
        and candidate.get("can_copy_code") is True
        and candidate.get("manual_review_required") is False
        and not conflict
    )

    if conflict:
        license_status = "needs_manual_review"
        compatibility_status = "blocked_license"
        rationale = "Conflicting license identifiers are blocked pending human resolution."
    elif not detected:
        license_status = "unknown"
        compatibility_status = "blocked_license"
        rationale = "No source-derived license identifier was supplied; metadata hints are not evidence."
    elif reviewed_compatible:
        license_status = "compatible"
        compatibility_status = "safe_to_adapt"
        rationale = "Explicit human-reviewed compatibility record accepted; preserve attribution and notices."
    elif detected[0] in BLOCK:
        license_status = "incompatible"
        compatibility_status = "blocked_license"
        rationale = "This license class remains blocked for direct reuse."
    else:
        license_status = "needs_manual_review"
        compatibility_status = "manual_review_required"
        rationale = "A license identifier was supplied, but its presence alone does not establish compatibility."

    return {
        "repo": candidate.get("repo", ""),
        "detected_license": detected[0] if len(detected) == 1 and not conflict else "unknown",
        "detected_licenses": detected,
        "license_hint": hint,
        "license_spdx": detected[0] if len(detected) == 1 and not conflict else "UNKNOWN",
        "license_status": license_status,
        "compatibility_status": compatibility_status,
        "can_copy_code": reviewed_compatible,
        "can_copy_docs": False,
        "can_adapt_patterns": True,
        "attribution_required": True,
        "notice_required": True,
        "manual_review_required": not reviewed_compatible,
        "review_status": review_status,
        "conflicting": conflict,
        "decision_rationale": rationale,
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
