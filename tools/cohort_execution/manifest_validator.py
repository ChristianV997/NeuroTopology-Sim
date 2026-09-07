"""Validation of cohort manifest readiness and refusal rules."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import RefusalReasonCode


def validate_manifest_readiness(
    manifest_path: str | Path,
    *,
    diagnostic_only: bool = False,
    allow_insufficient: bool = False,
    require_complete_provenance: bool = True,
) -> tuple[dict[str, Any], list[str], bool]:
    """Validates readiness metadata of a PairedCohortManifest before reading any recordings.

    Refuses execution for:
    - no_data
    - malformed
    - insufficient_pairs (unless allow_insufficient=True)
    - ambiguous_labels
    - incomplete_provenance (when require_complete_provenance=True)

    Returns:
        (manifest_dict, refusal_reasons, is_executable)
    """
    p = Path(manifest_path)
    if not p.is_file():
        return {}, [f"Manifest file not found on disk: {p}"], False

    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        return {}, [f"Malformed JSON in manifest file: {exc}"], False

    if not isinstance(data, dict):
        return {}, ["Malformed manifest: root structure must be a JSON object."], False

    refusal_reasons: list[str] = []

    status = data.get("status")
    status_reason = data.get("status_reason", "")
    paired_records = data.get("paired_records", [])
    ambiguous = data.get("ambiguous_matches", [])
    invalid_files = data.get("invalid_files", [])

    # 1. No data
    if status == "no_data" or (len(paired_records) == 0 and data.get("total_recordings", 0) == 0):
        refusal_reasons.append(
            f"Execution refused: status is '{RefusalReasonCode.NO_DATA.value}'. {status_reason}"
        )

    # 2. Malformed
    if status in ("malformed", "malformed_cohort") or "paired_records" not in data:
        refusal_reasons.append(
            f"Execution refused: status is '{RefusalReasonCode.MALFORMED.value}'. {status_reason}"
        )

    if invalid_files and not paired_records:
        refusal_reasons.append(
            f"Execution refused: manifest contains {len(invalid_files)} invalid files and no valid pairs."
        )

    # 3. Insufficient pairs
    empirical_pairs = data.get("empirical_paired_count", 0)
    min_pairs = data.get("min_pairs", 2)
    if status == "insufficient_pairs" and not allow_insufficient:
        refusal_reasons.append(
            f"Execution refused: status is '{RefusalReasonCode.INSUFFICIENT_PAIRS.value}'. Found {empirical_pairs} pairs, but minimum required is {min_pairs}."
        )

    # 4. Ambiguous labels
    if ambiguous:
        refusal_reasons.append(
            f"Execution refused: manifest contains {len(ambiguous)} ambiguous matches with unresolvable condition labels."
        )

    # 5. Incomplete provenance
    prov_status = data.get("provenance_status")
    if prov_status == "incomplete_provenance":
        refusal_reasons.append(
            f"Execution refused: manifest declares '{RefusalReasonCode.INCOMPLETE_PROVENANCE.value}'."
        )
    elif require_complete_provenance and paired_records:
        # Check if paired records have provenance entries
        missing_prov_count = 0
        for pair in paired_records:
            rec_a = pair.get("condition_a_record", {})
            rec_b = pair.get("condition_b_record", {})
            prov_a = rec_a.get("provenance", {})
            prov_b = rec_b.get("provenance", {})
            if not prov_a or not prov_b:
                missing_prov_count += 1
        if missing_prov_count > 0:
            refusal_reasons.append(
                f"Execution refused: {missing_prov_count} paired records have incomplete provenance metadata."
            )

    is_executable = (len(refusal_reasons) == 0) or diagnostic_only
    return data, refusal_reasons, is_executable
