"""
Export DS005620 evidence packet for peer review (P18.2 / O4).

Reads the artifact manifest, execution summary, omega event, and optional
ontology evaluation to produce:
- evidence_packet.json          — structured evidence record
- evidence_packet.md            — human-readable summary
- notion_import_payload.json    — Notion-compatible import payload

Usage:
  python tools/export_ds005620_evidence_packet.py \\
    --manifest outputs/btc_icft/ds005620_real_benchmark_execution_mock/artifact_manifest.json \\
    --out outputs/btc_icft/ds005620_real_benchmark_execution_mock \\
    --ontology-root outputs/btc_icft/ds005620_ontology_evaluation_mock
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# Ensure repo root is on sys.path when running as a script from tools/.
sys.path.insert(0, str(Path(__file__).parent.parent))

from sciencer_d.btc_icft.ontology.artifact_reader import (
    summarize_ontology_for_packet,
)
from tools.research_cycle_bridge.models import BridgeContractError, canonical_hash


_SAFE_CLAIM = (
    "DS005620 evidence packet exported from engineering benchmark artifacts. "
    "Contains only engineering results. Makes no metaphysical, soteriological, "
    "or experiential claims about any subject."
)

_PROMOTION_DECISION = "engineering_runtime_validated_only"

_DEFAULT_ONTOLOGY_ROOT = "outputs/btc_icft/ds005620_ontology_evaluation_mock"
_EMPTY_BYTES_SHA256 = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
_SAFE_MODES = {
    "mock_e2e",
    "real_preflight",
    "real_data",
    "real_benchmark",
    "engineering_only",
    "synthetic_demo",
}

_ONTOLOGY_ENUMS = {
    "max_claim_scope": {
        "engineering_runtime",
        "empirical_marker",
        "empirical_topology",
        "mechanism_candidate",
        "theory_consistency",
        "ontology_candidate",
    },
    "promotion_state": {
        "engineering_validated",
        "pending_review",
        "quarantined",
        "blocked",
        "promoted",
        "not_available",
    },
    "ontology_claim_status": {
        "ontology_quarantined",
        "review_required",
        "blocked",
        "ready_for_review",
        "not_available",
    },
}


def _safe_ontology_summary(summary: dict[str, Any]) -> dict[str, Any]:
    """Keep ontology output to allowlisted states, booleans, and counts."""
    safe: dict[str, Any] = {"ontology_available": summary.get("ontology_available") is True}
    for key, allowed in _ONTOLOGY_ENUMS.items():
        value = summary.get(key)
        safe[key] = value if isinstance(value, str) and value in allowed else "unknown"
    for key in (
        "ontology_promotion",
        "empirical_marker_promotion",
        "empirical_topology_promotion",
        "mechanism_promotion",
        "metaphysical_promotion",
    ):
        safe[key] = summary.get(key) is True
    counts = summary.get("bridge_status_counts")
    safe["bridge_status_count"] = (
        sum(value for value in counts.values() if isinstance(value, int) and value >= 0)
        if isinstance(counts, dict)
        else 0
    )
    safe["blocked_claim_count"] = len(summary.get("blocked_claims", []))
    safe["required_next_evidence_count"] = len(summary.get("required_next_evidence", []))
    safe["safe_claim_available"] = isinstance(summary.get("safe_claim"), str)
    return safe


def _ontology_markdown(summary: dict[str, Any]) -> str:
    lines = [
        "## Ontology Claim Scope",
        "",
        f"- Availability: {summary['ontology_available']}",
        f"- Max claim scope: `{summary['max_claim_scope']}`",
        f"- Promotion state: `{summary['promotion_state']}`",
        f"- Contract status: `{summary['ontology_claim_status']}`",
        f"- Blocked claims counted: {summary['blocked_claim_count']}",
        f"- Bridge statuses counted: {summary['bridge_status_count']}",
        "- Free-text claims, identifiers, and blocker details are omitted.",
    ]
    return "\n".join(lines)


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _unique_json_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            # A JSON key may itself contain a participant identifier.  Keep
            # parser diagnostics structural and value-free.
            raise ValueError("duplicate JSON key")
        result[key] = value
    return result


def _read_metadata_json(path: Path, label: str, errors: list[str]) -> dict[str, Any] | None:
    if not path.is_file():
        errors.append(f"{label}_missing")
        return None
    try:
        value = json.loads(
            path.read_text(encoding="utf-8"), object_pairs_hook=_unique_json_object
        )
    except (OSError, UnicodeError, json.JSONDecodeError, ValueError) as exc:
        errors.append(f"{label}_invalid_json:{type(exc).__name__}")
        return None
    if not isinstance(value, dict):
        errors.append(f"{label}_root_not_object")
        return None
    return value


def _parse_participant_table(
    path: Path,
    parse_errors: list[str],
    validation_errors: list[str],
) -> tuple[list[str], list[str], bool, bool]:
    if not path.is_file():
        parse_errors.append("participants_tsv_missing")
        return [], [], False, False
    participant_ids: list[str] = []
    excluded_ids: list[str] = []
    valid = True
    parsed = True
    try:
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter="\t", strict=True)
            fields = reader.fieldnames or []
            if fields.count("participant_id") != 1:
                validation_errors.append("participants_tsv_missing_or_duplicate_participant_id_header")
                return [], [], True, False
            if len(fields) != len(set(fields)):
                validation_errors.append("participants_tsv_duplicate_header")
                valid = False
            seen: set[str] = set()
            for row_number, row in enumerate(reader, start=2):
                if None in row or any(row.get(field) is None for field in fields):
                    parse_errors.append(f"participants_tsv_malformed_row:{row_number}")
                    parsed = False
                    valid = False
                    continue
                participant_id = row.get("participant_id")
                if (
                    not isinstance(participant_id, str)
                    or not participant_id
                    or participant_id != participant_id.strip()
                ):
                    validation_errors.append(f"participants_tsv_invalid_participant_id:{row_number}")
                    valid = False
                    continue
                if participant_id in seen:
                    validation_errors.append(
                        f"participants_tsv_duplicate_subject:row:{row_number}"
                    )
                    valid = False
                    continue
                seen.add(participant_id)
                participant_ids.append(participant_id)
                if "excluded" in fields:
                    exclusion_value = str(row.get("excluded", "")).strip().casefold()
                    if exclusion_value == "true":
                        excluded_ids.append(participant_id)
                    elif exclusion_value != "false":
                        validation_errors.append(f"participants_tsv_invalid_excluded_flag:{row_number}")
                        valid = False
    except (OSError, UnicodeError, csv.Error) as exc:
        parse_errors.append(f"participants_tsv_invalid:{type(exc).__name__}")
        parsed = False
        valid = False
    return participant_ids, excluded_ids, parsed, valid


def _read_readme_license(
    root: Path,
    parse_errors: list[str],
    validation_errors: list[str],
) -> tuple[str | None, bool]:
    candidates = [
        root / name
        for name in ("README.txt", "README.md", "README")
        if (root / name).is_file()
    ]
    if not candidates:
        parse_errors.append("readme_missing")
        return None, False
    if len(candidates) != 1:
        validation_errors.append("readme_ambiguous_multiple_files")
        return None, True
    try:
        text = candidates[0].read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        parse_errors.append(f"readme_unreadable:{type(exc).__name__}")
        return None, False
    licenses: list[str] = []
    for line in text.splitlines():
        clean = line.strip().strip("*_` ")
        match = re.search(r"(?i)\blicensed under\s+(.+)$", clean)
        if match:
            value = match.group(1).strip().rstrip(".")
            if value:
                licenses.append(value)
        elif re.match(r"(?i)^license\s*:", clean):
            value = clean.split(":", 1)[1].strip().rstrip(".")
            if value:
                licenses.append(value)
    distinct = list(dict.fromkeys(licenses))
    if len(distinct) != 1:
        validation_errors.append("readme_license_missing" if not distinct else "readme_license_ambiguous")
        return None, True
    return distinct[0], True


def _nonnegative_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _validate_task_requirements(
    value: Any,
) -> tuple[list[dict[str, str | None]], list[str]]:
    errors: list[str] = []
    if not isinstance(value, list) or not value:
        return [], ["expected_task_requirements_missing"]
    requirements: list[dict[str, str | None]] = []
    seen: set[tuple[str, str | None, str | None, str | None]] = set()
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            errors.append(f"task_requirement_not_object:{index}")
            continue
        task = item.get("task_label")
        if not isinstance(task, str) or not task or task != task.strip():
            errors.append(f"task_requirement_invalid_task_label:{index}")
            continue
        normalized: dict[str, str | None] = {"task_label": task}
        invalid = False
        for key in ("session_id", "run_id", "subject_id"):
            raw = item.get(key)
            if raw is not None and (not isinstance(raw, str) or not raw or raw != raw.strip()):
                errors.append(f"task_requirement_invalid_{key}:{index}")
                invalid = True
                break
            normalized[key] = raw
        if invalid:
            continue
        identity = (
            task,
            normalized["session_id"],
            normalized["run_id"],
            normalized["subject_id"],
        )
        if identity in seen:
            errors.append(f"task_requirement_duplicate:{index}")
            continue
        seen.add(identity)
        requirements.append(normalized)
    if not requirements and not errors:
        errors.append("expected_task_requirements_missing")
    return requirements, errors


def _validate_preregistered_plan(plan: dict[str, Any] | None, supplied: bool) -> dict[str, Any]:
    synthetic_plan = bool(plan and plan.get("is_synthetic") is True)
    result: dict[str, Any] = {
        "status": "not_supplied" if not supplied else "invalid",
        "plan_integrity_verified": False,
        "authority_asserted": False,
        "synthetic_demo_only": synthetic_plan,
        "registration_reference": None,
        "plan_sha256": None,
        "expected_task_requirements": None,
        "expected_task_set": None,
        "errors": [],
    }
    if not supplied or plan is None:
        return result

    checksum = plan.get("checksum")
    result["plan_sha256"] = checksum if isinstance(checksum, str) else None
    payload = {key: value for key, value in plan.items() if key != "checksum"}
    if not payload:
        result["errors"].append("plan_payload_empty")
        return result
    if checksum == _EMPTY_BYTES_SHA256:
        result["errors"].append("empty_bytes_sha256_is_not_plan_provenance")
        return result
    if not isinstance(checksum, str) or not re.fullmatch(r"[0-9a-f]{64}", checksum):
        result["errors"].append("plan_checksum_missing_or_invalid_format")
        return result
    try:
        computed = canonical_hash(payload)
    except (BridgeContractError, TypeError, ValueError):
        result["errors"].append("plan_not_canonical_finite_json")
        return result
    if checksum != computed:
        result["errors"].append("plan_checksum_mismatch")
        return result
    result["plan_integrity_verified"] = True

    provenance = plan.get("provenance")
    provenance = provenance if isinstance(provenance, dict) else {}
    reference = provenance.get("preregistration_reference")
    result["registration_reference"] = reference if isinstance(reference, str) else None
    result["authority_asserted"] = provenance.get("authoritative_source_verified") is True
    if provenance.get("source_checksum") == _EMPTY_BYTES_SHA256:
        result["errors"].append("empty_bytes_sha256_is_not_plan_provenance")
    if plan.get("schema_version") != "ExperimentPlan.v1":
        result["errors"].append("plan_schema_version_not_ExperimentPlan.v1")
    if not synthetic_plan:
        if str(plan.get("data_source", "")).casefold() != "ds005620":
            result["errors"].append("plan_dataset_not_ds005620")
        if not isinstance(reference, str) or not reference.startswith("https://"):
            result["errors"].append("preregistration_reference_missing_or_not_https")
        if not isinstance(provenance.get("registered_at"), str) or not provenance["registered_at"].strip():
            result["errors"].append("preregistration_registered_at_missing")
        if not result["authority_asserted"]:
            result["errors"].append("authoritative_source_not_asserted_verified")

    variables = plan.get("variables")
    requirements_value = variables.get("expected_task_requirements") if isinstance(variables, dict) else None
    requirements, requirement_errors = _validate_task_requirements(requirements_value)
    result["errors"].extend(requirement_errors)
    if not result["errors"]:
        result["status"] = (
            "synthetic_demo_only"
            if synthetic_plan
            else "declared_protocol_integrity_checked"
        )
        result["expected_task_requirements"] = requirements
        result["expected_task_set"] = sorted(
            {item["task_label"] for item in requirements if item["task_label"] is not None}
        )
    elif requirement_errors and result["plan_integrity_verified"]:
        result["status"] = "requirements_missing_or_invalid"
    else:
        result["status"] = "integrity_verified_only" if result["plan_integrity_verified"] else "invalid"
    return result


def _public_preregistration_summary(preregistration: dict[str, Any]) -> dict[str, Any]:
    """Return only aggregate protocol metadata; never expose row identifiers."""
    requirements = preregistration.get("expected_task_requirements")
    task_count = None
    requirement_count = None
    if isinstance(requirements, list):
        requirement_count = len(requirements)
        task_count = len(
            {
                item.get("task_label")
                for item in requirements
                if isinstance(item, dict) and isinstance(item.get("task_label"), str)
            }
        )
    return {
        "status": preregistration.get("status", "invalid"),
        "plan_integrity_verified": preregistration.get("plan_integrity_verified") is True,
        "authority_asserted": preregistration.get("authority_asserted") is True,
        "synthetic_demo_only": preregistration.get("synthetic_demo_only") is True,
        "registration_reference_supplied": bool(preregistration.get("registration_reference")),
        "expected_task_requirement_count": requirement_count,
        "expected_task_count": task_count,
        "errors": list(preregistration.get("errors", [])),
    }


def _inventory_summary(
    inventory: dict[str, Any] | None,
    supplied: bool,
    preregistration: dict[str, Any],
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "status": "not_supplied" if not supplied else "invalid",
        "observed_task_session_run_coverage_count": 0,
        "inventory_subject_count": 0,
        "missing_task_requirement_count": None,
        "unexpected_task_label_count": 0,
        "unclassified_inventory_records": 0,
        "file_inventory_complete_against_declared_requirements": None,
        "errors": [],
    }
    if not supplied or inventory is None:
        return result
    records = inventory.get("eeg_candidates")
    if not isinstance(records, list):
        result["errors"].append("file_inventory_eeg_candidates_missing_or_invalid")
        return result

    coverage: set[tuple[str, str | None, str | None]] = set()
    subject_ids: set[str] = set()
    observed_tasks: set[str] = set()
    valid_records: list[dict[str, str | None]] = []
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            result["errors"].append(f"file_inventory_record_not_object:{index}")
            continue
        if record.get("is_eeg_candidate") is False:
            continue
        task = record.get("task_label")
        if not isinstance(task, str) or not task or task != task.strip():
            result["unclassified_inventory_records"] += 1
            continue
        current: dict[str, str | None] = {"task_label": task}
        invalid = False
        for key in ("session_id", "run_id", "subject_id"):
            raw = record.get(key)
            if raw is not None and (not isinstance(raw, str) or raw != raw.strip()):
                result["errors"].append(f"file_inventory_invalid_{key}:{index}")
                invalid = True
                break
            current[key] = raw or None
        if invalid:
            continue
        observed_tasks.add(task)
        coverage.add((task, current["session_id"], current["run_id"]))
        if current["subject_id"]:
            subject_ids.add(current["subject_id"])
        valid_records.append(current)

    result["observed_task_session_run_coverage_count"] = len(coverage)
    result["inventory_subject_count"] = len(subject_ids)
    requirements = preregistration.get("expected_task_requirements")
    if preregistration.get("status") not in {
        "declared_protocol_integrity_checked",
        "synthetic_demo_only",
    } or not isinstance(requirements, list):
        result["status"] = "not_evaluable_without_verified_protocol"
        return result

    missing_requirement_count = 0
    for requirement in requirements:
        if not any(
            record["task_label"] == requirement["task_label"]
            and (requirement["session_id"] is None or record["session_id"] == requirement["session_id"])
            and (requirement["run_id"] is None or record["run_id"] == requirement["run_id"])
            and (requirement["subject_id"] is None or record["subject_id"] == requirement["subject_id"])
            for record in valid_records
        ):
            missing_requirement_count += 1
    expected_tasks = set(preregistration.get("expected_task_set") or [])
    unexpected_task_count = len(observed_tasks - expected_tasks)
    result["missing_task_requirement_count"] = missing_requirement_count
    result["unexpected_task_label_count"] = unexpected_task_count
    complete = (
        not result["errors"]
        and result["unclassified_inventory_records"] == 0
        and missing_requirement_count == 0
        and unexpected_task_count == 0
    )
    result["file_inventory_complete_against_declared_requirements"] = complete
    suffix = "_synthetic_demo_only" if preregistration.get("synthetic_demo_only") is True else ""
    result["status"] = (
        ("complete_against_declared_requirements" if complete else "incomplete_against_declared_requirements")
        + suffix
    )
    return result


def _metadata_reconciliation(metadata_root: str | None) -> dict[str, Any]:
    if metadata_root is None:
        plan_details = _validate_preregistered_plan(None, False)
        inventory = _inventory_summary(None, False, plan_details)
        return {
            "metadata_parsed": False,
            "metadata_parse_errors": ["metadata_root_not_supplied"],
            "metadata_validation_errors": [],
            "participants_tsv_count": None,
            "excluded_participant_count": None,
            "bids_subject_count_match": None,
            "nemar_participant_count_match": None,
            "published_counts": {
                "bids_subjects": None,
                "analyzed_participants": None,
                "awakening_trials": None,
                "attempted_awakenings": None,
            },
            "published_count_source_claims_supplied": False,
            "published_count_source_claim_count": None,
            "participant_count_difference": None,
            "cohort_count_consistent": None,
            "cohort_reconciliation_status": "not_evaluated_identity_unverified",
            "analysis_identifier_list_supplied": False,
            "analysis_identifier_count": None,
            "analysis_identifier_count_matches_published_count": None,
            "license_declarations": {
                "dataset_description_supplied": False,
                "readme_supplied": False,
                "nemar_supplied": False,
            },
            "source_metadata": {
                "dataset_description_supplied": False,
                "readme_supplied": False,
                "nemar_metadata_supplied": False,
            },
            "license_declaration_count": 0,
            "license_declarations_consistent": False,
            "license_conflict": False,
            "data_use_ready": False,
            "data_use_readiness_blockers": [
                "metadata_audit_not_authorized_to_grant_data_use",
                "metadata_root_not_supplied",
            ],
            "preregistration": _public_preregistration_summary(plan_details),
            "task_session_run_coverage": inventory,
            "file_inventory_complete_against_declared_requirements": None,
            "expected_task_count": None,
        }

    root = Path(metadata_root)
    parse_errors: list[str] = []
    validation_errors: list[str] = []
    participants_path = root / "participants.tsv"
    participant_ids, excluded_ids, participants_parsed, participants_valid = _parse_participant_table(
        participants_path, parse_errors, validation_errors
    )
    description = _read_metadata_json(root / "dataset_description.json", "dataset_description", parse_errors)
    readme_license, readme_parsed = _read_readme_license(root, parse_errors, validation_errors)
    nemar = _read_metadata_json(root / "nemar_metadata.json", "nemar_metadata", parse_errors)
    published = _read_metadata_json(root / "published_counts.json", "published_counts", parse_errors)

    inventory_path = root / "file_inventory.json"
    inventory_errors: list[str] = []
    inventory = (
        _read_metadata_json(inventory_path, "file_inventory", inventory_errors)
        if inventory_path.exists()
        else None
    )
    plan_path = root / "preregistered_plan.json"
    plan_errors: list[str] = []
    plan = (
        _read_metadata_json(plan_path, "preregistered_plan", plan_errors)
        if plan_path.exists()
        else None
    )
    preregistration = _validate_preregistered_plan(plan, plan_path.exists())
    preregistration["errors"].extend(plan_errors)
    inventory_summary = _inventory_summary(inventory, inventory_path.exists(), preregistration)
    inventory_summary["errors"].extend(inventory_errors)
    if inventory_errors and inventory_path.exists():
        inventory_summary["status"] = "invalid"
        inventory_summary["file_inventory_complete_against_declared_requirements"] = None

    bids_subject_count = _nonnegative_int(published.get("bids_subjects")) if published else None
    analyzed_count = _nonnegative_int(published.get("analyzed_participants")) if published else None
    awakening_trial_count = _nonnegative_int(published.get("awakening_trials")) if published else None
    attempted_awakening_count = (
        _nonnegative_int(published.get("attempted_awakenings")) if published else None
    )
    published_source_claims = published.get("source_claims") if published else None
    if published is not None and "source_claims" in published and not isinstance(published_source_claims, dict):
        validation_errors.append("published_counts_invalid_source_claims")
        published_source_claims = None
    source_claims_supplied = isinstance(published_source_claims, dict)
    source_claim_count = len(published_source_claims) if source_claims_supplied else None
    participants_count = len(participant_ids) if participants_valid else None
    nemar_participant_count = _nonnegative_int(nemar.get("participants")) if nemar else None
    bids_subject_count_match = (
        participants_count == bids_subject_count
        if participants_count is not None and bids_subject_count is not None
        else None
    )
    nemar_participant_count_match = (
        participants_count == nemar_participant_count
        if participants_count is not None and nemar_participant_count is not None
        else None
    )
    participant_difference = (
        participants_count - analyzed_count
        if participants_count is not None and analyzed_count is not None
        else None
    )
    analysis_ids_value = published.get("analyzed_subject_ids") if published else None
    subject_ids_supplied = isinstance(analysis_ids_value, list)
    analysis_identifier_count = len(analysis_ids_value) if subject_ids_supplied else None
    analysis_ids_valid: bool | None = None
    analysis_id_count_matches: bool | None = None
    cohort_count_consistent: bool | None = None
    cohort_status = "not_evaluated_identity_unverified"
    if subject_ids_supplied:
        analysis_ids_valid = all(
            isinstance(item, str) and item and item == item.strip()
            for item in analysis_ids_value
        ) and len(set(analysis_ids_value)) == len(analysis_ids_value)
        if not analysis_ids_valid:
            validation_errors.append("published_counts_invalid_analyzed_subject_ids")
        elif analyzed_count is not None:
            analysis_id_count_matches = analysis_identifier_count == analyzed_count
    if participants_count is not None and analyzed_count is not None:
        cohort_count_consistent = (
            participants_count - len(excluded_ids) == analyzed_count
        )
        if subject_ids_supplied and analysis_ids_valid is False:
            cohort_status = "invalid_analysis_identifier_list_identity_unverified"
            cohort_count_consistent = False
        elif subject_ids_supplied and analysis_id_count_matches is False:
            cohort_status = "identifier_count_mismatch_identity_unverified"
            cohort_count_consistent = False
        elif cohort_count_consistent:
            cohort_status = "count_consistent_identity_unverified"
        else:
            cohort_status = "count_discrepancy_identity_unverified"

    description_license = description.get("License") if description else None
    nemar_license = (nemar.get("license") or nemar.get("License")) if nemar else None
    raw_license_values = [
        value.strip()
        for value in (description_license, readme_license, nemar_license)
        if isinstance(value, str) and value.strip()
    ]
    license_conflict = len({value.casefold() for value in raw_license_values}) > 1
    license_declarations = {
        "dataset_description_supplied": bool(
            isinstance(description_license, str) and description_license.strip()
        ),
        "readme_supplied": bool(readme_license),
        "nemar_supplied": bool(isinstance(nemar_license, str) and nemar_license.strip()),
    }
    license_declarations_consistent = (
        sum(license_declarations.values()) == 3 and not license_conflict
    )
    source_metadata = {
        "dataset_description_supplied": description is not None,
        "readme_supplied": readme_parsed,
        "nemar_metadata_supplied": nemar is not None,
    }

    metadata_parsed = (
        participants_parsed
        and participants_valid
        and description is not None
        and readme_parsed
        and nemar is not None
        and published is not None
    )
    blockers = ["metadata_audit_not_authorized_to_grant_data_use"]
    if not license_declarations_consistent:
        blockers.append("license_declarations_incomplete_or_conflicting")
    if license_conflict:
        blockers.append("license_conflict")
    blockers.append("cohort_identity_not_verified")
    if inventory_summary["file_inventory_complete_against_declared_requirements"] is not True:
        blockers.append("file_inventory_not_complete_against_verified_protocol")

    return {
        "metadata_parsed": metadata_parsed,
        "metadata_parse_errors": parse_errors,
        "metadata_validation_errors": validation_errors,
        "participants_tsv_count": participants_count,
        "excluded_participant_count": len(excluded_ids) if participants_valid else None,
        "bids_subject_count_match": bids_subject_count_match,
        "nemar_participant_count_match": nemar_participant_count_match,
        "published_counts": {
            "bids_subjects": bids_subject_count,
            "analyzed_participants": analyzed_count,
            "awakening_trials": awakening_trial_count,
            "attempted_awakenings": attempted_awakening_count,
        },
        "published_count_source_claims_supplied": source_claims_supplied,
        "published_count_source_claim_count": source_claim_count,
        "participant_count_difference": participant_difference,
        "cohort_count_consistent": cohort_count_consistent,
        "cohort_reconciliation_status": cohort_status,
        "analysis_identifier_list_supplied": subject_ids_supplied,
        "analysis_identifier_count": analysis_identifier_count,
        "analysis_identifier_count_matches_published_count": analysis_id_count_matches,
        "license_declarations": license_declarations,
        "source_metadata": source_metadata,
        "license_declaration_count": sum(license_declarations.values()),
        "license_declarations_consistent": license_declarations_consistent,
        "license_conflict": license_conflict,
        "data_use_ready": False,
        "data_use_readiness_blockers": blockers,
        "preregistration": _public_preregistration_summary(preregistration),
        "task_session_run_coverage": inventory_summary,
        "file_inventory_complete_against_declared_requirements": inventory_summary[
            "file_inventory_complete_against_declared_requirements"
        ],
        "expected_task_count": _public_preregistration_summary(preregistration)[
            "expected_task_count"
        ],
    }


def build_evidence_packet(
    manifest_path: str,
    out_dir: str,
    *,
    ontology_root: str | None = None,
    require_ontology: bool = False,
    metadata_root: str | None = None,
) -> dict[str, str]:
    manifest_p = Path(manifest_path)
    manifest = _load_json(manifest_p)
    root = Path(manifest.get("artifact_root", manifest_p.parent))

    execution = _load_json(root / "ds005620_real_benchmark_execution.json")
    omega = _load_json(root / "omega_event.json")

    benchmark_completed = execution.get("benchmark_completed", False)
    mode_value = execution.get("mode")
    mode = mode_value if isinstance(mode_value, str) and mode_value in _SAFE_MODES else "unknown"
    benchmark_completed = benchmark_completed is True
    p12_ok = execution.get("p12_succeeded") is True
    p13_ok = execution.get("p13_succeeded") is True
    p11_ok = execution.get("p11_succeeded") is True

    omega_invariants = {
        key: omega.get(key) is True
        for key in (
            "labels_inferred",
            "targets_fabricated",
            "source_contracts_modified",
            "legacy_mt_real_modified",
            "contracts_activated_by_executor",
            "p11_promotion_gate_modified",
            "consciousness_claims_made",
        )
    }
    all_invariants_false = all(not v for v in omega_invariants.values())

    # Ontology summary
    _ontology_root = Path(ontology_root) if ontology_root else Path(_DEFAULT_ONTOLOGY_ROOT)
    ontology_summary = _safe_ontology_summary(
        summarize_ontology_for_packet(_ontology_root)
    )
    warnings: list[str] = []
    if not ontology_summary["ontology_available"]:
        if require_ontology:
            raise SystemExit(
                "--require-ontology is set but ontology evaluation is unavailable"
            )
        warnings.append("ontology_evaluation_missing")

    metadata_reconciliation = _metadata_reconciliation(metadata_root)
    if not metadata_reconciliation["metadata_parsed"]:
        warnings.append("ds005620_metadata_not_fully_parsed")
    if metadata_reconciliation["license_conflict"]:
        warnings.append("ds005620_license_conflict_unresolved")
    if metadata_reconciliation["cohort_count_consistent"] is not True:
        warnings.append("ds005620_cohort_count_consistency_unavailable_or_mismatched")

    claim_scope = {
        "engineering_runtime": True,
        "marker_association": ontology_summary.get("empirical_marker_promotion", False),
        "topology_residual": ontology_summary.get("empirical_topology_promotion", False),
        "mechanism_candidate": ontology_summary.get("mechanism_promotion", False),
        "theory_consistency": False,
        "ontology_candidate": False,
    }

    packet = {
        "dataset_id": "DS005620",
        "evidence_type": "engineering_benchmark_execution",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "benchmark_completed": benchmark_completed,
        "mode": mode,
        "stage_outcomes": {
            "p12_succeeded": p12_ok,
            "p13_succeeded": p13_ok,
            "p11_succeeded": p11_ok,
        },
        "omega_invariants": omega_invariants,
        "all_omega_invariants_false": all_invariants_false,
        "promotion_decision": _PROMOTION_DECISION,
        "artifact_count": _nonnegative_int(manifest.get("artifact_count")) or 0,
        "safe_claim": _SAFE_CLAIM,
        "source_manifest_supplied": bool(str(manifest_p)),
        "warnings": warnings,
        "ontology_summary": ontology_summary,
        "metadata_reconciliation": metadata_reconciliation,
        "metadata_is_empirical_evidence": False,
        "participant_eeg_data_downloaded_or_analyzed": False,
        "claim_scope": claim_scope,
    }

    out = Path(out_dir)
    try:
        out.mkdir(parents=True, exist_ok=True)

        packet_path = out / "evidence_packet.json"
        packet_path.write_text(json.dumps(packet, indent=2, allow_nan=False), encoding="utf-8")

    except OSError as exc:
        raise RuntimeError(f"evidence packet write failed: {type(exc).__name__}") from None

    # Markdown contains only the sanitized ontology allowlist, never source text.
    ontology_md = _ontology_markdown(ontology_summary)

    md_lines = [
        "# DS005620 Evidence Packet",
        "",
        f"**Dataset:** DS005620",
        f"**Mode:** {mode}",
        f"**Benchmark completed:** {benchmark_completed}",
        f"**Promotion decision:** `{_PROMOTION_DECISION}`",
        "",
        "## Stage Outcomes",
        "",
        f"- P12 label alignment: {p12_ok}",
        f"- P13 target injection: {p13_ok}",
        f"- P11 M+T benchmark: {p11_ok}",
        "",
        "## Metadata and Provenance Reconciliation",
        "",
        f"- Metadata parsed: {metadata_reconciliation['metadata_parsed']}",
        f"- File inventory complete against verified declared requirements: {metadata_reconciliation['file_inventory_complete_against_declared_requirements']}",
        f"- Aggregate count consistency: {metadata_reconciliation['cohort_count_consistent']}",
        f"- License declarations internally consistent: {metadata_reconciliation['license_declarations_consistent']}",
        f"- License conflict: {metadata_reconciliation['license_conflict']}",
        f"- Data-use ready: {metadata_reconciliation['data_use_ready']}",
        "- This is aggregate metadata consistency only; it does not establish cohort identity or data-use rights.",
        "- Raw participant and excluded identifiers, free-text metadata, and source hashes are not exported.",
        "- Metadata reconciliation is not empirical evidence and does not grant permission to use data.",
        "",
        "## Omega Invariants (all must be false)",
        "",
    ]
    for k, v in omega_invariants.items():
        md_lines.append(f"- `{k}`: {v}")
    md_lines += [
        "",
        ontology_md,
        "",
        "## Safe Claim",
        "",
        _SAFE_CLAIM,
        "",
        "## What This Is Not",
        "",
        (
            "This evidence packet records engineering execution results only. "
            "It makes no assertions about internal states, awareness, or any "
            "metaphysical properties of any biological or computational system."
        ),
        "",
        "---",
        "",
        "_P18.2 / O4 evidence export — no pipeline stages executed during this export._",
    ]
    md_path = out / "evidence_packet.md"

    notion_payload = {
        "title": "DS005620 Evidence Packet",
        "properties": {
            "Dataset": "DS005620",
            "Mode": mode,
            "Benchmark Completed": benchmark_completed,
            "Promotion Decision": _PROMOTION_DECISION,
            "All Omega Invariants False": all_invariants_false,
            "P12 Succeeded": p12_ok,
            "P13 Succeeded": p13_ok,
            "P11 Succeeded": p11_ok,
            "Ontology Claim Scope": ontology_summary.get("max_claim_scope", "engineering_runtime"),
            "Ontology Promotion State": ontology_summary.get("promotion_state", "engineering_validated"),
            "Ontology Status": ontology_summary.get("ontology_claim_status", "ontology_quarantined"),
            "Ontology Next Evidence Items": ontology_summary["required_next_evidence_count"],
            "Bridge Status Count": ontology_summary["bridge_status_count"],
        },
        "ontology_claim_scope": ontology_summary.get("max_claim_scope", "engineering_runtime"),
        "ontology_promotion_state": ontology_summary.get("promotion_state", "engineering_validated"),
        "ontology_status": ontology_summary.get("ontology_claim_status", "ontology_quarantined"),
        "ontology_next_evidence_count": ontology_summary["required_next_evidence_count"],
        "bridge_status_count": ontology_summary["bridge_status_count"],
        "metadata_reconciliation": metadata_reconciliation,
        "metadata_is_empirical_evidence": False,
        "participant_eeg_data_downloaded_or_analyzed": False,
        "content_md": "\n".join(md_lines),
    }
    notion_path = out / "notion_import_payload.json"
    try:
        md_path.write_text("\n".join(md_lines), encoding="utf-8")
        notion_path.write_text(json.dumps(notion_payload, indent=2, allow_nan=False), encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"evidence packet write failed: {type(exc).__name__}") from None

    return {
        "evidence_packet.json": packet_path.name,
        "evidence_packet.md": md_path.name,
        "notion_import_payload.json": notion_path.name,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Export DS005620 evidence packet (P18.2 / O4)")
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--out", default=None)
    parser.add_argument(
        "--ontology-root",
        default=_DEFAULT_ONTOLOGY_ROOT,
        help="Path to ontology evaluation output directory",
    )
    parser.add_argument(
        "--require-ontology",
        action="store_true",
        default=False,
        help="Exit nonzero if ontology evaluation is absent",
    )
    parser.add_argument(
        "--metadata-root",
        default=None,
        help="Directory with metadata-only reconciliation fixtures; EEG files are never opened",
    )
    args = parser.parse_args(argv)

    out_dir = args.out or str(Path(args.manifest).parent)
    try:
        artifacts = build_evidence_packet(
            args.manifest,
            out_dir,
            ontology_root=args.ontology_root,
            require_ontology=args.require_ontology,
            metadata_root=args.metadata_root,
        )
    except SystemExit as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"evidence packet export failed: {type(exc).__name__}", file=sys.stderr)
        return 2
    for name, path in artifacts.items():
        print(f"{name}: written")
    return 0


if __name__ == "__main__":
    sys.exit(main())
