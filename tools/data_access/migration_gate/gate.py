"""Authoritative Data-Access Migration Gate orchestrator."""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from .classifier import MigrationClassifier
from .types import (
    GateClassification,
    GateReport,
    MigrationEntry,
    MigrationManifest,
    MigrationStatus,
    json_safe,
)
from .validator import (
    is_prohibited_exception_rule,
    is_stale_expiration,
    validate_migration_entry,
)


def _load_scanner_findings(scanner_input: Any) -> tuple[list[dict[str, Any]], str, list[str]]:
    """Extract finding dicts, repository root, and any load errors from various input forms."""
    errors: list[str] = []
    root = "."

    if scanner_input is None:
        return [], root, ["No scanner findings provided."]

    # If it's a Path or string pointing to a file
    if isinstance(scanner_input, (str, Path)):
        p = Path(scanner_input)
        if p.is_file():
            try:
                text = p.read_text(encoding="utf-8")
                data = json.loads(text)
                return _load_scanner_findings(data)
            except Exception as exc:
                return [], root, [f"Failed to read/parse scanner findings file '{p}': {exc}"]
        elif isinstance(scanner_input, str) and scanner_input.strip().startswith("{"):
            try:
                data = json.loads(scanner_input)
                return _load_scanner_findings(data)
            except Exception as exc:
                return [], root, [f"Failed to parse scanner JSON string: {exc}"]
        else:
            return [], root, [f"Scanner input path not found: '{p}'"]

    # If it's a PolicyReport object
    if hasattr(scanner_input, "findings") and hasattr(scanner_input, "repository_root"):
        root = str(getattr(scanner_input, "repository_root", "."))
        raw_findings = getattr(scanner_input, "findings", [])
        findings_list = [
            f.to_dict() if hasattr(f, "to_dict") and callable(f.to_dict) else dict(f)
            for f in raw_findings
        ]
        return findings_list, root, []

    # If it's a dict representing PolicyReport or finding collection
    if isinstance(scanner_input, Mapping):
        root = str(scanner_input.get("repository_root", "."))
        if "findings" in scanner_input:
            findings_data = scanner_input["findings"]
            if isinstance(findings_data, Sequence):
                return [dict(item) for item in findings_data], root, []
        return [], root, ["Scanner report dict missing 'findings' key."]

    # If it's directly a list of findings
    if isinstance(scanner_input, Sequence):
        findings_list = []
        for item in scanner_input:
            if hasattr(item, "to_dict") and callable(item.to_dict):
                findings_list.append(item.to_dict())
            elif isinstance(item, Mapping):
                findings_list.append(dict(item))
            else:
                errors.append(f"Invalid finding item type: {type(item)}")
        return findings_list, root, errors

    return [], root, [f"Unsupported scanner input type: {type(scanner_input)}"]


def _load_manifest(manifest_input: Any) -> tuple[MigrationManifest | None, list[str]]:
    """Load and parse MigrationManifest from various input types."""
    if manifest_input is None:
        return None, ["No migration manifest provided."]

    if isinstance(manifest_input, MigrationManifest):
        return manifest_input, []

    if isinstance(manifest_input, (str, Path)):
        p = Path(manifest_input)
        if p.is_file():
            try:
                return MigrationManifest.from_file(p), []
            except Exception as exc:
                return None, [f"Failed to read/parse manifest file '{p}': {exc}"]
        elif isinstance(manifest_input, str) and manifest_input.strip().startswith("{"):
            try:
                data = json.loads(manifest_input)
                return MigrationManifest.from_dict(data), []
            except Exception as exc:
                return None, [f"Failed to parse manifest JSON string: {exc}"]
        else:
            return None, [f"Manifest input path not found: '{p}'"]

    if isinstance(manifest_input, Mapping):
        try:
            return MigrationManifest.from_dict(manifest_input), []
        except Exception as exc:
            return None, [f"Failed to convert mapping to MigrationManifest: {exc}"]

    return None, [f"Unsupported manifest input type: {type(manifest_input)}"]


class DataAccessMigrationGate:
    """Evaluates data-access migration progress, enforces safety rules, and fails closed."""

    def __init__(self, repository_root: str | Path = ".") -> None:
        self.repository_root = str(repository_root)

    def evaluate(
        self,
        scanner_input: Any,
        manifest_input: Any,
        *,
        current_date: datetime.date | str | None = None,
        strict: bool = False,
    ) -> GateReport:
        """Run the migration gate evaluation.

        Parameters:
            scanner_input: PolicyReport, findings list, JSON file path, or dict.
            manifest_input: MigrationManifest, JSON file path, or dict.
            current_date: Optional evaluation date override (ISO string or date).
            strict: If True, gate fails when ANY unmigrated or temporary exceptions exist.
        """
        fail_closed_reasons: list[str] = []

        # Parse evaluation date
        if current_date is None:
            eval_date = datetime.date.today()
        elif isinstance(current_date, datetime.date):
            eval_date = current_date
        else:
            try:
                eval_date = datetime.date.fromisoformat(str(current_date).strip())
            except ValueError:
                eval_date = datetime.date.today()
                fail_closed_reasons.append(f"Invalid evaluation date format '{current_date}'.")

        eval_date_str = eval_date.isoformat()

        # Load scanner findings
        raw_findings, detected_root, scanner_errors = _load_scanner_findings(scanner_input)
        if scanner_errors:
            fail_closed_reasons.extend(scanner_errors)

        # Load manifest
        manifest, manifest_errors = _load_manifest(manifest_input)
        if manifest_errors:
            fail_closed_reasons.extend(manifest_errors)

        # If we failed to load either essential input, return fail-closed report immediately
        if manifest is None:
            return GateReport(
                evaluation_date=eval_date_str,
                repository_root=self.repository_root,
                gate_passed=False,
                compliance_claim_allowed=False,
                compliance_statement="CRITICAL: Migration manifest could not be loaded; gate failed closed. Compliance claim PROHIBITED.",
                fail_closed_reasons=fail_closed_reasons,
                checksum="",
            )

        # Compute Before Counts (Raw Scanner Findings)
        before_counts: dict[str, Any] = {
            "total": len(raw_findings),
            "by_severity": {"critical": 0, "error": 0, "warning": 0},
            "by_rule": {},
            "by_category": {},
        }
        for f in raw_findings:
            sev = str(f.get("severity", "error")).lower()
            before_counts["by_severity"][sev] = before_counts["by_severity"].get(sev, 0) + 1
            rule = str(f.get("rule", "unknown"))
            before_counts["by_rule"][rule] = before_counts["by_rule"].get(rule, 0) + 1
            cat = str(f.get("category", "unknown"))
            before_counts["by_category"][cat] = before_counts["by_category"].get(cat, 0) + 1

        # Classify findings
        classifier = MigrationClassifier(manifest, current_date=eval_date)
        classifications: list[GateClassification] = []
        hidden_findings: list[dict[str, Any]] = []
        stale_exceptions: list[dict[str, Any]] = []
        unsafe_approvals: list[dict[str, Any]] = []

        # Keep track of which manifest entries were matched
        matched_entries: set[tuple[str, str]] = set()

        for finding in raw_findings:
            c, hidden_info, stale_info, unsafe_info = classifier.classify_finding(finding)
            classifications.append(c)

            if hidden_info:
                hidden_findings.append(hidden_info)
            if stale_info:
                stale_exceptions.append(stale_info)
            if unsafe_info:
                unsafe_approvals.append(unsafe_info)

            if c.entry:
                matched_entries.add((c.entry.get("file", "").strip(), c.entry.get("rule", "").strip()))

        # Also inspect all manifest entries for stale/unsafe exceptions not triggered by scanner findings
        for entry in manifest.entries:
            key = (entry.file.strip(), entry.rule.strip())
            entry_val = validate_migration_entry(entry, current_date=eval_date)

            if entry_val.is_prohibited_exception or entry_val.is_permanent or entry_val.is_wildcard:
                u_item = {
                    "file": entry.file,
                    "symbol_or_line": entry.symbol_or_line,
                    "rule": entry.rule,
                    "owner": entry.owner,
                    "reason": "; ".join(entry_val.errors),
                }
                if u_item not in unsafe_approvals:
                    unsafe_approvals.append(u_item)

            if entry_val.is_stale:
                s_item = {
                    "file": entry.file,
                    "rule": entry.rule,
                    "owner": entry.owner,
                    "expires_at": entry.expires_at,
                    "reason": f"Exception expired on {entry.expires_at}.",
                }
                if s_item not in stale_exceptions:
                    stale_exceptions.append(s_item)

            # Entries marked SAFELY_MIGRATED that scanner did NOT flag -> verified safe!
            if key not in matched_entries and entry.status == MigrationStatus.SAFELY_MIGRATED:
                classifications.append(
                    GateClassification(
                        file=entry.file,
                        line=int(entry.symbol_or_line) if str(entry.symbol_or_line).isdigit() else 1,
                        rule=entry.rule,
                        severity=entry.severity,
                        category="migrated",
                        status=MigrationStatus.SAFELY_MIGRATED,
                        owner=entry.owner,
                        migration_reference=entry.migration_reference,
                        reason=f"Verified safely migrated under {entry.migration_reference}.",
                        is_blocker=False,
                        is_resolved=True,
                        entry=entry.to_dict(),
                    )
                )

            # Entries marked NOT_APPLICABLE not flagged by scanner
            elif key not in matched_entries and entry.status == MigrationStatus.NOT_APPLICABLE:
                classifications.append(
                    GateClassification(
                        file=entry.file,
                        line=int(entry.symbol_or_line) if str(entry.symbol_or_line).isdigit() else 1,
                        rule=entry.rule,
                        severity=entry.severity,
                        category="not_applicable",
                        status=MigrationStatus.NOT_APPLICABLE,
                        owner=entry.owner,
                        migration_reference=entry.migration_reference,
                        reason=f"Verified not applicable: {entry.justification}.",
                        is_blocker=False,
                        is_resolved=True,
                        entry=entry.to_dict(),
                    )
                )

            # Invalid or malformed entries that were not matched by scanner findings
            elif key not in matched_entries and not entry_val.is_valid:
                classifications.append(
                    GateClassification(
                        file=entry.file or "<missing>",
                        line=int(entry.symbol_or_line) if str(entry.symbol_or_line).isdigit() else 1,
                        rule=entry.rule or "<missing>",
                        severity=entry.severity,
                        category="manifest_validation_failure",
                        status=entry_val.status,
                        owner=entry.owner or None,
                        migration_reference=entry.migration_reference or None,
                        reason=f"Manifest entry validation failed: {'; '.join(entry_val.errors)}",
                        is_blocker=True,
                        is_resolved=False,
                        entry=entry.to_dict(),
                    )
                )

        # Compute After Counts (Post-Classification)
        after_counts: dict[str, int] = {
            "safely_migrated": 0,
            "reviewed_temporary_exception": 0,
            "unmigrated": 0,
            "unsafe_blocked": 0,
            "not_applicable": 0,
            "unable_to_assess": 0,
        }
        for c in classifications:
            after_counts[c.status.value.replace(" ", "_")] = after_counts.get(c.status.value.replace(" ", "_"), 0) + 1

        unresolved_total = (
            after_counts["unmigrated"]
            + after_counts["reviewed_temporary_exception"]
            + after_counts["unsafe_blocked"]
            + after_counts["unable_to_assess"]
        )
        resolved_total = after_counts["safely_migrated"] + after_counts["not_applicable"]
        after_counts["unresolved_total"] = unresolved_total
        after_counts["resolved_total"] = resolved_total

        # Collect fail-closed reasons
        if hidden_findings:
            fail_closed_reasons.append(f"{len(hidden_findings)} hidden/untracked finding(s) detected.")
        if stale_exceptions:
            fail_closed_reasons.append(f"{len(stale_exceptions)} stale/expired exception(s) detected.")
        if unsafe_approvals:
            fail_closed_reasons.append(f"{len(unsafe_approvals)} unsafe exception approval attempt(s) detected.")
        if after_counts["unsafe_blocked"] > 0:
            fail_closed_reasons.append(f"{after_counts['unsafe_blocked']} item(s) classified as unsafe blocked.")
        if after_counts["unable_to_assess"] > 0:
            fail_closed_reasons.append(f"{after_counts['unable_to_assess']} item(s) classified as unable to assess.")
        if strict and unresolved_total > 0:
            fail_closed_reasons.append(f"Strict mode enabled: {unresolved_total} unresolved violation(s) remain.")

        # Determine gate pass / fail
        # Gate passes in non-strict mode when all active items are properly tracked, no hidden findings,
        # no stale exceptions, no unsafe approvals, and no unsafe_blocked items.
        # In strict mode, gate additionally requires 0 unmigrated and 0 temporary exceptions.
        gate_passed = len(fail_closed_reasons) == 0

        # Enforce Rule 10: NEVER claim repository-wide compliance while unresolved findings remain
        compliance_claim_allowed = (
            len(fail_closed_reasons) == 0
            and unresolved_total == 0
            and len(hidden_findings) == 0
            and len(stale_exceptions) == 0
            and len(unsafe_approvals) == 0
            and after_counts["unsafe_blocked"] == 0
            and after_counts["unable_to_assess"] == 0
            and after_counts["unmigrated"] == 0
            and after_counts["reviewed_temporary_exception"] == 0
        )

        if compliance_claim_allowed:
            compliance_statement = (
                "All tracked data-access violations have been safely migrated or verified non-applicable. "
                "Zero unresolved violations remain; repository-wide data-access compliance claim is PERMITTED."
            )
        else:
            compliance_statement = (
                f"Repository has {unresolved_total} unresolved data-access violation(s) "
                f"(unmigrated={after_counts['unmigrated']}, "
                f"temporary_exceptions={after_counts['reviewed_temporary_exception']}, "
                f"unsafe_blocked={after_counts['unsafe_blocked']}, "
                f"hidden={len(hidden_findings)}). "
                "Repository-wide compliance claim is PROHIBITED."
            )

        report = GateReport(
            evaluation_date=eval_date_str,
            repository_root=self.repository_root,
            gate_passed=gate_passed,
            compliance_claim_allowed=compliance_claim_allowed,
            compliance_statement=compliance_statement,
            before_counts=before_counts,
            after_counts=after_counts,
            classifications=classifications,
            stale_exceptions=stale_exceptions,
            hidden_findings=hidden_findings,
            unsafe_approvals=unsafe_approvals,
            fail_closed_reasons=fail_closed_reasons,
        )
        report.checksum = report.compute_checksum()
        return report
