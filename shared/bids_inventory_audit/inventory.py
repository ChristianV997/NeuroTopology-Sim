"""Aggregate-only audit of caller-supplied participant-table text and path strings.

This module does not discover or read participant files from disk. It does parse
participants-table text and relative-path strings explicitly supplied by the caller.
Subject and task labels are compared transiently in memory but are omitted from public results,
findings, and errors. It reports structure and aggregate gaps, not which labels match a finding.

Expected tasks are never inferred from observed files. Without a declared set, the audit
reports that expectation is undeclared and performs no completeness claim.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Iterable, Mapping, Optional

from .findings import make_finding, sort_findings
from .license import license_report
from .paths import _parse_bids_relpath
from .schema import (
    ANALYSIS_DECLARED_INCONSISTENT,
    ANALYSIS_DECLARED_UNVERIFIED,
    ANALYSIS_NOT_ESTABLISHED,
    COHORT_IDENTITY,
    EVIDENCE_CLASS,
    PAYLOAD_ACCESS,
    REGISTRATION_STATUS,
    SCHEMA,
    SCOPE,
    STATUS,
    SUBJECT_RE,
    TASK_LABEL_RE,
    external_registration_block,
)
from .tsv import _parse_participants_tsv

_COHORT_STATEMENT = (
    "This inventory reports aggregate participant and file counts. It does not establish which subjects "
    "any analysis or publication used, so it is not a cohort identification."
)
_TASK_PRESENCE_STATEMENT = (
    "Aggregate file-level task presence is not analysis or completion evidence. A listed task shows only "
    "that matching path strings were supplied."
)
_ANALYSIS_STATEMENT = (
    "A declared analysis record is caller-supplied and unverified. It is reported only as aggregate counts, "
    "never as established, and checked only for internal count consistency."
)
_ANALYSIS_KEYS = frozenset({"analyzed_n", "excluded_subjects"})


def _malformed_reason(record: Any) -> Optional[str]:
    if not isinstance(record, Mapping):
        return "analysis record must be a mapping"
    if set(record) != _ANALYSIS_KEYS:
        return "analysis record must contain exactly analyzed_n and excluded_subjects"
    analyzed_n = record["analyzed_n"]
    if isinstance(analyzed_n, bool) or not isinstance(analyzed_n, int) or analyzed_n < 0:
        return "analyzed_n must be a non-negative integer"
    excluded = record["excluded_subjects"]
    if not isinstance(excluded, (list, tuple)):
        return "excluded_subjects must be a list"
    if not all(isinstance(subject, str) and SUBJECT_RE.fullmatch(subject) for subject in excluded):
        return "excluded_subjects must contain subject labels of the form sub-<label>"
    if len(set(excluded)) != len(excluded):
        return "excluded_subjects must not repeat a subject"
    return None


def _analysis_block(record: Any, participants: Optional[set[str]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Report declared analysis fields as aggregate-only and unverified."""
    findings: list[dict[str, Any]] = []
    block: dict[str, Any] = {
        "record_declared": record is not None,
        "record_status": "NOT_DECLARED",
        "status": ANALYSIS_NOT_ESTABLISHED,
        "analyzed_n": None,
        "excluded_subjects_n": None,
        "count_check": "NOT_PERFORMED",
        "authoritative": False,
        "statement": _ANALYSIS_STATEMENT,
    }
    if record is None:
        findings.append(make_finding(
            "ANALYSIS_RECORD_NOT_DECLARED", "warning",
            "no analysis record was declared; analyzed N and exclusions are not established"))
        return block, findings

    try:
        reason = _malformed_reason(record)
    except Exception:
        reason = "analysis record could not be read"
    if reason is not None:
        block["record_status"] = "MALFORMED"
        findings.append(make_finding("ANALYSIS_RECORD_MALFORMED", "error", reason))
        return block, findings

    try:
        analyzed_n = record["analyzed_n"]
        excluded = set(record["excluded_subjects"])
    except Exception:
        block["record_status"] = "MALFORMED"
        findings.append(make_finding(
            "ANALYSIS_RECORD_MALFORMED", "error",
            "analysis record could not be read; supplied values were omitted"))
        return block, findings
    block.update(record_status="DECLARED", status=ANALYSIS_DECLARED_UNVERIFIED,
                 analyzed_n=analyzed_n, excluded_subjects_n=len(excluded))

    if participants is None:
        findings.append(make_finding(
            "ANALYSIS_COUNT_UNCHECKED", "warning",
            "no participants table; the declared analyzed N cannot be checked"))
        return block, findings

    unknown_count = len(excluded - participants)
    if unknown_count:
        findings.append(make_finding(
            "EXCLUSION_NOT_IN_PARTICIPANTS", "error",
            "one or more declared exclusions are absent from the participants table",
            affected_count=unknown_count))
    expected = len(participants) - len(excluded)
    if unknown_count or analyzed_n != expected:
        block["count_check"] = "FAILED"
        if not unknown_count:
            findings.append(make_finding(
                "ANALYSIS_COUNT_MISMATCH", "error",
                f"declared analyzed N {analyzed_n} differs from {expected}, the participants less declared exclusions"))
    else:
        block["count_check"] = "CONSISTENT"

    if block["count_check"] == "FAILED":
        # An inconsistent declaration reports no number, so no count can be quoted from it.
        block.update(status=ANALYSIS_DECLARED_INCONSISTENT, analyzed_n=None, excluded_subjects_n=None)
    return block, findings


def audit_inventory(
    *,
    participants_tsv: Optional[str],
    file_paths: Iterable[Any],
    expected_tasks: Optional[Iterable[Any]] = None,
    readme_text: Optional[str] = None,
    nemar_metadata: Optional[Mapping[str, Any]] = None,
    dataset_description: Optional[Mapping[str, Any]] = None,
    catalog_metadata: Optional[Mapping[str, Any]] = None,
    analysis_record: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []

    participants: Optional[set[str]] = None
    tsv_summary: Optional[dict[str, int]] = None
    if participants_tsv is None:
        findings.append(make_finding(
            "PARTICIPANTS_NOT_PROVIDED", "error",
            "no participants table; subject cross-checks were not performed"))
    else:
        tsv, labels = _parse_participants_tsv(participants_tsv)
        findings.extend(tsv.findings)
        participants = set(labels)
        tsv_summary = {
            "accepted_rows": tsv.accepted_rows,
            "rejected_rows": tsv.rejected_rows,
            "blank_lines": tsv.blank_lines,
        }

    # Listing strings are caller-supplied and never dereferenced. Avoid echoing them in findings.
    listing_readable = True
    try:
        listed = list(file_paths)
    except Exception:
        listed = []
        listing_readable = False
        findings.append(make_finding(
            "FILE_LISTING_UNREADABLE", "error",
            "the supplied path listing could not be consumed; path counts and cross-checks are unavailable"))

    subject_files = []
    non_subject = 0
    invalid_entries = 0
    for raw in listed:
        parsed = _parse_bids_relpath(raw)
        if not parsed.valid:
            invalid_entries += 1
        elif parsed.is_subject_file:
            subject_files.append(parsed)
        else:
            non_subject += 1
    if invalid_entries:
        findings.append(make_finding(
            "UNPARSEABLE_PATH", "error", "one or more supplied path entries were rejected",
            affected_count=invalid_entries))

    relpath_counts = Counter(raw for raw in listed if isinstance(raw, str))
    duplicate_path_groups = sum(count > 1 for count in relpath_counts.values())
    if duplicate_path_groups:
        findings.append(make_finding(
            "DUPLICATE_FILE", "error", "repeated relative paths were found",
            affected_count=duplicate_path_groups))

    by_signature: dict[tuple[Any, ...], set[str]] = defaultdict(set)
    for parsed in subject_files:
        by_signature[parsed.signature()].add(parsed.relpath)
    duplicate_signature_groups = sum(len(relpaths) > 1 for relpaths in by_signature.values())
    if duplicate_signature_groups:
        findings.append(make_finding(
            "DUPLICATE_ENTITY_SIGNATURE", "error",
            "different supplied paths claim the same BIDS entity signature",
            affected_count=duplicate_signature_groups))

    file_subjects = {parsed.subject for parsed in subject_files if parsed.subject}

    if participants is None:
        universe_source = "none"
        cross_check = "NOT_PERFORMED"
        file_only_count: Optional[int] = None
        without_files_count: Optional[int] = None
    elif not listing_readable:
        universe_source = "participants"
        cross_check = "NOT_PERFORMED"
        file_only_count = None
        without_files_count = None
    else:
        universe_source = "participants"
        cross_check = "PERFORMED"
        file_only = file_subjects - participants
        without_files = participants - file_subjects
        file_only_count = len(file_only)
        without_files_count = len(without_files)
        if file_only:
            findings.append(make_finding(
                "FILE_SUBJECT_NOT_IN_PARTICIPANTS", "error",
                "one or more supplied subject-path labels are absent from the participants table",
                affected_count=len(file_only)))
        if without_files:
            findings.append(make_finding(
                "PARTICIPANT_WITHOUT_FILES", "warning",
                "one or more participants have no valid subject file in the supplied listing",
                affected_count=len(without_files)))

    task_subjects: dict[str, set[str]] = defaultdict(set)
    for parsed in subject_files:
        if parsed.task and parsed.subject:
            task_subjects[parsed.task].add(parsed.subject)
    observed_tasks = sorted(task_subjects) if listing_readable else None

    expected: Optional[list[str]] = None
    if expected_tasks is None:
        findings.append(make_finding(
            "EXPECTED_TASKS_NOT_DECLARED", "error",
            "no expected task set was declared; the audit makes no task-completeness claim"))
    else:
        try:
            declared = list(expected_tasks)
        except Exception:
            declared = None
            findings.append(make_finding(
                "EXPECTED_TASKS_UNREADABLE", "error",
                "the declared task iterable could not be consumed; no task values were retained"))
        if declared is not None:
            valid_declared = [task for task in declared if isinstance(task, str) and TASK_LABEL_RE.fullmatch(task)]
            invalid_count = len(declared) - len(valid_declared)
            if invalid_count:
                findings.append(make_finding(
                    "EXPECTED_TASK_INVALID", "error", "one or more task labels were rejected",
                    affected_count=invalid_count))
            expected = sorted(set(valid_declared))
            if listing_readable:
                for task in expected:
                    present_count = len(task_subjects.get(task, set()))
                    if participants is None:
                        if present_count == 0:
                            findings.append(make_finding(
                                "TASK_ABSENT_IN_LISTING", "error",
                                "a declared task appears in no listed file; per-subject coverage not assessed"))
                        continue
                    missing_count = len(participants) - len(participants & task_subjects.get(task, set()))
                    if missing_count == len(participants) and participants:
                        findings.append(make_finding(
                            "TASK_ABSENT_FOR_ALL_SUBJECTS", "error",
                            "a declared task has no file for any participant",
                            affected_count=missing_count))
                    elif missing_count:
                        findings.append(make_finding(
                            "MISSING_TASK_FOR_SUBJECT", "warning",
                            "a declared task is missing for one or more participants",
                            affected_count=missing_count))
                for task in observed_tasks or []:
                    if task not in expected:
                        findings.append(make_finding(
                            "UNEXPECTED_TASK", "warning",
                            "an observed task is outside the declared set"))

    analysis, analysis_findings = _analysis_block(analysis_record, participants)
    findings.extend(analysis_findings)

    license_state = license_report(readme_text, nemar_metadata,
                                   dataset_description=dataset_description,
                                   catalog_metadata=catalog_metadata)
    findings.extend(license_state["findings"])

    findings = sort_findings(findings)
    severity_counts = Counter(f["severity"] for f in findings)
    observed_task_set = set(task_subjects) if listing_readable else None
    expected_task_set = set(expected) if expected is not None else None
    if observed_task_set is None or expected_task_set is None:
        expected_with_files_count = None
        expected_without_files_count = None
        unexpected_observed_count = None
    else:
        expected_with_files_count = len(expected_task_set & observed_task_set)
        expected_without_files_count = len(expected_task_set - observed_task_set)
        unexpected_observed_count = len(observed_task_set - expected_task_set)

    if participants is None or observed_task_set is None or expected_task_set is None:
        missing_for_any_participants_count = None
        missing_for_all_participants_count = None
    else:
        missing_counts = [
            len(participants - task_subjects.get(task, set()))
            for task in expected_task_set
        ]
        missing_for_any_participants_count = sum(count > 0 for count in missing_counts)
        missing_for_all_participants_count = sum(
            bool(participants) and count == len(participants) for count in missing_counts
        )
    return {
        "schema": SCHEMA,
        "scope": SCOPE,
        "status": STATUS,
        "evidence_class": EVIDENCE_CLASS,
        "registration_status": REGISTRATION_STATUS,
        "external_registration": external_registration_block(),
        "payload_access": PAYLOAD_ACCESS,
        "cohort_identity": COHORT_IDENTITY,
        "cohort_statement": _COHORT_STATEMENT,
        "authoritative_manifest": False,
        "download_authorized": False,
        "analysis_authorized": False,
        "scientific_pass": False,
        "participants": {
            "table": tsv_summary,
            "subject_count": len(participants) if participants is not None else None,
            "universe_source": universe_source,
            "cross_check": cross_check,
            "file_subject_count": len(file_subjects) if listing_readable else None,
            "file_only_subject_count": file_only_count,
            "participants_without_files_count": without_files_count,
        },
        "entries": {
            "listed": len(listed) if listing_readable else None,
            "subject_entries_valid": len(subject_files) if listing_readable else None,
            "non_subject_entries": non_subject if listing_readable else None,
            "invalid_entries": invalid_entries if listing_readable else None,
        },
        "tasks": {
            "expected_declared": expected_tasks is not None,
            "expected_count": len(expected) if expected is not None else None,
            "observed_count": len(task_subjects) if listing_readable else None,
            "coverage": {
                "expected_tasks_with_files_count": expected_with_files_count,
                "expected_tasks_without_files_count": expected_without_files_count,
                "expected_tasks_missing_for_any_participants_count": missing_for_any_participants_count,
                "expected_tasks_missing_for_all_participants_count": missing_for_all_participants_count,
                "unexpected_observed_tasks_count": unexpected_observed_count,
            } if listing_readable else None,
            "presence_statement": _TASK_PRESENCE_STATEMENT,
            "completion_evidence": False,
        },
        "analysis": analysis,
        "license": license_state,
        "findings": findings,
        "severity_counts": {key: severity_counts.get(key, 0) for key in ("error", "warning", "info")},
    }
