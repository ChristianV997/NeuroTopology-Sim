"""Validation of cohort manifest readiness and refusal rules for cohort execution."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import ExecutionStatus, RefusalReasonCode


def validate_manifest_readiness(
    manifest_path: str | Path,
    *,
    diagnostic_only: bool = False,
    allow_insufficient: bool = False,
    require_complete_provenance: bool = True,
) -> tuple[dict[str, Any], list[str], str, bool]:
    """Validates readiness metadata of a PairedCohortManifest before reading any recordings.

    Refuses execution for:
    - NO_DATA
    - INVALID_INPUT (malformed JSON or corrupted manifest)
    - INSUFFICIENT_PAIRED_SUBJECTS (unless allow_insufficient=True)
    - INCOMPLETE_PROVENANCE (when require_complete_provenance=True)
    - Ambiguous condition labels

    Returns:
        (manifest_dict, refusal_reasons, status_code, is_executable)
    """
    p = Path(manifest_path)
    if not p.is_file():
        return {}, [f"Manifest file not found on disk: {p}"], ExecutionStatus.INVALID_INPUT.value, False

    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        return {}, [f"Malformed JSON in manifest file: {exc}"], ExecutionStatus.INVALID_INPUT.value, False

    if not isinstance(data, dict):
        return {}, ["Malformed manifest: root structure must be a JSON object."], ExecutionStatus.INVALID_INPUT.value, False

    refusal_reasons: list[str] = []
    status = data.get("status")
    status_reason = data.get("status_reason", "")
    paired_records = data.get("paired_records", [])
    ambiguous = data.get("ambiguous_matches", [])
    invalid_files = data.get("invalid_files", [])

    is_all_synthetic = (
        len(paired_records) > 0
        and all(p.get("is_synthetic", False) for p in paired_records)
    )

    suggested_status = (
        ExecutionStatus.SYNTHETIC_DEMO_ONLY.value
        if is_all_synthetic
        else ExecutionStatus.DESCRIPTIVE_READY.value
    )

    # 1. No data
    if status == "no_data" or (len(paired_records) == 0 and data.get("total_recordings", 0) == 0):
        refusal_reasons.append(
            f"Execution refused: status is '{RefusalReasonCode.NO_DATA.value}'. {status_reason}"
        )
        suggested_status = ExecutionStatus.NO_DATA.value

    # 2. Malformed / Invalid Input
    elif status in ("malformed", "malformed_cohort") or "paired_records" not in data:
        refusal_reasons.append(
            f"Execution refused: status is '{RefusalReasonCode.MALFORMED.value}'. {status_reason}"
        )
        suggested_status = ExecutionStatus.INVALID_INPUT.value

    elif invalid_files and not paired_records:
        refusal_reasons.append(
            f"Execution refused: manifest contains {len(invalid_files)} invalid files and no valid pairs."
        )
        suggested_status = ExecutionStatus.INVALID_INPUT.value

    # 3. Ambiguous labels
    elif ambiguous:
        refusal_reasons.append(
            f"Execution refused: manifest contains {len(ambiguous)} ambiguous matches with unresolvable condition labels."
        )
        suggested_status = ExecutionStatus.INVALID_INPUT.value

    # 4. Incomplete provenance
    prov_status = data.get("provenance_status")
    if prov_status == "incomplete_provenance":
        refusal_reasons.append(
            f"Execution refused: manifest declares '{RefusalReasonCode.INCOMPLETE_PROVENANCE.value}'."
        )
        suggested_status = ExecutionStatus.INCOMPLETE_PROVENANCE.value
    elif require_complete_provenance and paired_records:
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
            suggested_status = ExecutionStatus.INCOMPLETE_PROVENANCE.value

    # 5. Insufficient pairs (evaluated for empirical manifests with data)
    if not is_all_synthetic and status != "no_data" and len(paired_records) > 0:
        empirical_pairs = data.get(
            "empirical_paired_count",
            sum(1 for p in paired_records if not p.get("is_synthetic", False)),
        )
        min_pairs = data.get("min_pairs", 2)
        if (status == "insufficient_pairs" or empirical_pairs < min_pairs) and not allow_insufficient:
            refusal_reasons.append(
                f"Execution refused: status is '{RefusalReasonCode.INSUFFICIENT_PAIRS.value}'. Found {empirical_pairs} empirical pairs, but minimum required is {min_pairs}."
            )
            suggested_status = ExecutionStatus.INSUFFICIENT_PAIRED_SUBJECTS.value

    is_executable = (len(refusal_reasons) == 0) or diagnostic_only
    return data, refusal_reasons, suggested_status, is_executable
