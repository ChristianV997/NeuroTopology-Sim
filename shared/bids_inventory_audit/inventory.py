"""Synthetic-only inventory audit of a participants table and a file listing.

The caller supplies text, strings, and mappings. Nothing here opens a file, so the audit
cannot inspect participant data. It reports structure and gaps. It does not establish which
subjects any analysis or publication used.

Expected tasks are never inferred from observed files. Without a declared set, the audit
reports that expectation is undeclared and performs no completeness claim.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any, Iterable, Mapping, Optional

from .findings import make_finding, sort_findings
from .license import license_report
from .paths import parse_bids_relpath
from .schema import (
    COHORT_IDENTITY,
    EVIDENCE_CLASS,
    REGISTRATION_STATUS,
    SCHEMA,
    SCOPE,
    STATUS,
    TASK_LABEL_RE,
)
from .tsv import parse_participants_tsv

_COHORT_STATEMENT = (
    "This inventory lists participants and files. It does not establish which subjects any analysis "
    "or publication used, so it is not a cohort identification."
)


def audit_inventory(
    *,
    participants_tsv: Optional[str],
    file_paths: Iterable[Any],
    expected_tasks: Optional[Iterable[Any]] = None,
    readme_text: Optional[str] = None,
    nemar_metadata: Optional[Mapping[str, Any]] = None,
) -> dict[str, Any]:
    findings: list[dict[str, Any]] = []

    # Participants table: strict parse, with rejected rows reported rather than dropped.
    participants: Optional[set[str]] = None
    tsv_summary: Optional[dict[str, Any]] = None
    if participants_tsv is None:
        findings.append(make_finding(
            "PARTICIPANTS_NOT_PROVIDED", "error",
            "no participants table; subject cross-checks were not performed"))
    else:
        tsv = parse_participants_tsv(participants_tsv)
        findings.extend(tsv.findings)
        participants = set(tsv.participants)
        tsv_summary = {"accepted_rows": tsv.accepted_rows, "rejected_rows": tsv.rejected_rows,
                       "blank_lines": tsv.blank_lines}

    # File listing: classify each path. Invalid paths are reported and excluded.
    listed = list(file_paths)
    subject_files = []
    non_subject = 0
    for raw in listed:
        parsed = parse_bids_relpath(raw)
        if not parsed.valid:
            findings.append(make_finding(
                "UNPARSEABLE_PATH", "error", ", ".join(parsed.problems) or "invalid path",
                path=parsed.relpath or "<non-text path>"))
        elif parsed.is_subject_file:
            subject_files.append(parsed)
        else:
            non_subject += 1

    relpath_counts = Counter(raw for raw in listed if isinstance(raw, str))
    for relpath, count in sorted(relpath_counts.items()):
        if count > 1:
            findings.append(make_finding("DUPLICATE_FILE", "error",
                                         f"listed {count} times", path=relpath))

    by_signature: dict[tuple[Any, ...], list[str]] = defaultdict(list)
    for parsed in subject_files:
        by_signature[parsed.signature()].append(parsed.relpath)
    for signature, relpaths in sorted(by_signature.items(), key=lambda item: str(item[0])):
        distinct = sorted(set(relpaths))
        if len(distinct) > 1:
            findings.append(make_finding(
                "DUPLICATE_ENTITY_SIGNATURE", "error",
                f"{len(distinct)} different paths claim the same BIDS entities",
                subject=signature[0], path=distinct[0]))

    file_subjects = sorted({parsed.subject for parsed in subject_files if parsed.subject})

    # Subject cross-checks: only when a participants table exists.
    if participants is None:
        subject_universe: Optional[list[str]] = None
        universe_source = "none"
        cross_check = "NOT_PERFORMED"
        file_only: list[str] = []
        without_files: list[str] = []
    else:
        subject_universe = sorted(participants)
        universe_source = "participants"
        cross_check = "PERFORMED"
        file_subject_set = set(file_subjects)
        file_only = [s for s in file_subjects if s not in participants]
        without_files = [s for s in subject_universe if s not in file_subject_set]
        for subject in file_only:
            findings.append(make_finding(
                "FILE_SUBJECT_NOT_IN_PARTICIPANTS", "error",
                "files exist for a subject absent from the participants table", subject=subject))
        for subject in without_files:
            findings.append(make_finding(
                "PARTICIPANT_WITHOUT_FILES", "warning",
                "participant has no valid subject file in the listing", subject=subject))

    # Tasks: only against a caller-declared expectation. Observation never defines it.
    observed_tasks = sorted({parsed.task for parsed in subject_files if parsed.task})
    coverage: dict[str, set[str]] = defaultdict(set)
    for parsed in subject_files:
        if parsed.task and parsed.subject:
            coverage[parsed.subject].add(parsed.task)

    expected: Optional[list[str]] = None
    if expected_tasks is None:
        findings.append(make_finding(
            "EXPECTED_TASKS_NOT_DECLARED", "error",
            "no expected task set was declared; the audit makes no task-completeness claim"))
    else:
        declared = list(expected_tasks)
        invalid = [t for t in declared if not (isinstance(t, str) and TASK_LABEL_RE.fullmatch(t))]
        for label in invalid:
            findings.append(make_finding("EXPECTED_TASK_INVALID", "error",
                                         "task label must be alphanumeric", path=str(label)))
        expected = sorted({t for t in declared if isinstance(t, str) and TASK_LABEL_RE.fullmatch(t)})
        for task in expected:
            if subject_universe is None:
                # No participants table: the subject universe is unknown, so per-subject gaps
                # cannot be assessed. Only the absence of a declared task from the whole listing
                # is reported, and that does not depend on inferring subjects.
                if not any(task in tasks for tasks in coverage.values()):
                    findings.append(make_finding(
                        "TASK_ABSENT_IN_LISTING", "error",
                        f"declared task {task!r} appears in no listed file; per-subject coverage not assessed",
                        task=task))
                continue
            missing = [s for s in subject_universe if task not in coverage.get(s, set())]
            if subject_universe and len(missing) == len(subject_universe):
                findings.append(make_finding(
                    "TASK_ABSENT_FOR_ALL_SUBJECTS", "error",
                    f"declared task {task!r} has no file for any participant", task=task))
            else:
                for subject in missing:
                    findings.append(make_finding(
                        "MISSING_TASK_FOR_SUBJECT", "warning",
                        f"declared task {task!r} has no file for this participant", subject=subject, task=task))
        for task in observed_tasks:
            if task not in expected:
                findings.append(make_finding(
                    "UNEXPECTED_TASK", "warning",
                    "observed task is outside the declared set", task=task))

    # License evidence: recorded, never resolved here.
    license_state = license_report(readme_text, nemar_metadata)
    findings.extend(license_state["findings"])

    findings = sort_findings(findings)
    severity_counts = Counter(f["severity"] for f in findings)
    return {
        "schema": SCHEMA,
        "scope": SCOPE,
        "status": STATUS,
        "evidence_class": EVIDENCE_CLASS,
        "registration_status": REGISTRATION_STATUS,
        "cohort_identity": COHORT_IDENTITY,
        "cohort_statement": _COHORT_STATEMENT,
        "authoritative_manifest": False,
        "download_authorized": False,
        "analysis_authorized": False,
        "scientific_pass": False,
        "participants": {
            "table": tsv_summary,
            "subjects": subject_universe,
            "universe_source": universe_source,
            "cross_check": cross_check,
            "file_subjects": file_subjects,
            "file_only_subjects": file_only,
            "participants_without_files": without_files,
        },
        "entries": {
            # Counts are per listed entry. A path listed twice is counted twice; DUPLICATE_FILE reports it.
            "listed": len(listed),
            "subject_entries_valid": len(subject_files),
            "non_subject_entries": non_subject,
            "invalid_entries": len(listed) - len(subject_files) - non_subject,
        },
        "tasks": {
            "expected_declared": expected_tasks is not None,
            "expected": expected,
            "observed": observed_tasks,
            "coverage": {subject: sorted(tasks) for subject, tasks in sorted(coverage.items())},
        },
        "license": license_state,
        "findings": findings,
        "severity_counts": {key: severity_counts.get(key, 0) for key in ("error", "warning", "info")},
    }
