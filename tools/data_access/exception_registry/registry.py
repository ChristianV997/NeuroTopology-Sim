"""Reviewed Exception Registry and Audit Engine.

Manages loading, validation, indexing, and tamper-evident audit reporting
for all data-access exceptions.

CRITICAL INVARIANTS:
1. The registry is kept strictly separate from the policy scanner.
2. It NEVER suppresses scanner findings.
3. It NEVER declares repository compliance merely because exceptions exist.
4. Expired, malformed, or unsafe exceptions fail closed.
"""
from __future__ import annotations

import datetime
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from tools.data_access.exception_registry.models import (
    EXCEPTION_REGISTRY_SCHEMA,
    ExceptionMatchResult,
    ExceptionRecordStatus,
    ExceptionValidationResult,
    RegistryAuditReport,
    ReviewedExceptionRecord,
    canonical_hash,
    finite_value,
)
from tools.data_access.exception_registry.validator import validate_exception_record

logger = logging.getLogger(__name__)


class ExceptionRegistry:
    """Registry managing strict, expiring reviewed data-access exceptions."""

    def __init__(self, exceptions_dir: Optional[Path | str] = None) -> None:
        self.exceptions_dir = Path(exceptions_dir).resolve() if exceptions_dir else None
        self._records_by_id: Dict[str, ReviewedExceptionRecord] = {}
        self._validation_by_id: Dict[str, ExceptionValidationResult] = {}
        # Maps (normalized_file, rule) -> list of ReviewedExceptionRecord
        self._index: Dict[Tuple[str, str], List[ReviewedExceptionRecord]] = {}

    def clear(self) -> None:
        """Clear loaded records."""
        self._records_by_id.clear()
        self._validation_by_id.clear()
        self._index.clear()

    def register_record(
        self,
        record: ReviewedExceptionRecord,
        as_of_date: Optional[str | datetime.date] = None,
    ) -> ExceptionValidationResult:
        """Validate and index an individual exception record.

        Records that fail validation (expired, unsafe, malformed, etc.) are recorded
        in the validation audit but are NOT registered as active match candidates.
        """
        val_result = validate_exception_record(record, as_of_date=as_of_date)
        self._records_by_id[record.exception_id] = record
        self._validation_by_id[record.exception_id] = val_result

        if val_result.is_valid and val_result.status == ExceptionRecordStatus.ACTIVE.value:
            norm_file = record.exact_file.replace("\\", "/").strip()
            norm_rule = record.rule_identifier.strip()
            key = (norm_file, norm_rule)
            if key not in self._index:
                self._index[key] = []
            self._index[key].append(record)

        return val_result

    def load_from_directory(
        self,
        directory: Optional[Path | str] = None,
        as_of_date: Optional[str | datetime.date] = None,
    ) -> RegistryAuditReport:
        """Load, validate, and index all exception files in a directory."""
        self.clear()
        target_dir = Path(directory).resolve() if directory else self.exceptions_dir
        if not target_dir or not target_dir.is_dir():
            now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
            eval_date_str = str(as_of_date or datetime.datetime.now(datetime.timezone.utc).date())
            report = RegistryAuditReport(
                schema_version=EXCEPTION_REGISTRY_SCHEMA,
                generated_at=now_iso,
                evaluation_as_of_date=eval_date_str,
                total_records=0,
                valid_active_count=0,
                expired_count=0,
                rejected_count=0,
                all_exceptions_valid_and_active=True,
                repository_compliant=False,
                compliance_declaration="NON_COMPLIANT_WITH_EXCEPTIONS",
                findings_suppressed_count=0,
                records=[],
                validation_results=[],
            )
            report.to_dict()
            return report

        # Discover all .json, .yaml, .yml files
        exception_files = sorted(
            [p for p in target_dir.glob("*") if p.is_file() and p.suffix.lower() in {".json", ".yaml", ".yml"}]
        )

        for ef in exception_files:
            try:
                content = ef.read_text(encoding="utf-8")
                if ef.suffix.lower() == ".json":
                    data = json.loads(content)
                else:
                    # Simple YAML-safe parser or PyYAML if present
                    try:
                        import yaml
                        data = yaml.safe_load(content)
                    except ImportError:
                        data = json.loads(content)

                if isinstance(data, dict):
                    rec = ReviewedExceptionRecord.from_dict(data)
                    self.register_record(rec, as_of_date=as_of_date)
                elif isinstance(data, list):
                    for item in data:
                        if isinstance(item, dict):
                            rec = ReviewedExceptionRecord.from_dict(item)
                            self.register_record(rec, as_of_date=as_of_date)
            except Exception as exc:
                # Malformed file - register an invalid entry that fails closed
                malformed_id = f"malformed-{ef.name}"
                malformed_rec = ReviewedExceptionRecord(
                    schema_version="invalid_schema",
                    exception_id=malformed_id,
                    exact_file=ef.name,
                    rule_identifier="unparseable",
                    owner="unknown",
                    justification="File parse failed",
                    migration_issue="#0",
                    created_date="1970-01-01",
                    expiry_date="1970-01-01",
                    reviewer="none",
                    permitted_behavior=[],
                    prohibited_behavior=[],
                    status=ExceptionRecordStatus.MALFORMED.value,
                    rejection_reasons=[f"File parsing error: {exc}"],
                )
                self.register_record(malformed_rec, as_of_date=as_of_date)

        return self.generate_audit_report(as_of_date=as_of_date)

    def match_finding(
        self,
        file: str,
        line: Optional[int],
        symbol: Optional[str],
        rule: str,
        as_of_date: Optional[str | datetime.date] = None,
    ) -> ExceptionMatchResult:
        """Evaluate if an exact policy finding matches an active, valid exception.

        FAIL-CLOSED:
        Returns matched=True ONLY if a valid, unexpired exception explicitly
        covers the exact file, exact rule, and exact line/symbol.
        """
        norm_file = file.replace("\\", "/").strip()
        norm_rule = rule.strip()
        key = (norm_file, norm_rule)

        candidates = self._index.get(key, [])
        for rec in candidates:
            val = self._validation_by_id.get(rec.exception_id)
            if not val or not val.is_valid or val.status != ExceptionRecordStatus.ACTIVE.value:
                continue

            # Check line or symbol match
            matched_location = False
            if rec.exact_line is not None and line is not None and rec.exact_line == line:
                matched_location = True
            elif rec.exact_symbol and symbol and rec.exact_symbol == symbol:
                matched_location = True

            if matched_location:
                return ExceptionMatchResult(
                    matched=True,
                    exception_id=rec.exception_id,
                    rule_identifier=rec.rule_identifier,
                    owner=rec.owner,
                    reviewer=rec.reviewer,
                    migration_issue=rec.migration_issue,
                    expiry_date=rec.expiry_date,
                    is_active=True,
                    status=rec.status,
                    notes=(
                        f"Matched active exception {rec.exception_id} owned by {rec.owner} "
                        f"(expires {rec.expiry_date}; migration: {rec.migration_issue})"
                    ),
                )

        return ExceptionMatchResult(
            matched=False,
            is_active=False,
            status="UNEXCEPTED",
            notes="No active, valid exception matches this finding.",
        )

    def generate_audit_report(self, as_of_date: Optional[str | datetime.date] = None) -> RegistryAuditReport:
        """Produce a comprehensive, tamper-evident audit report.

        INVARIANT: `repository_compliant` is ALWAYS False! Exceptions track debt,
        they do NOT confer compliance.
        """
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        eval_date_str = str(as_of_date or datetime.datetime.now(datetime.timezone.utc).date())

        total = len(self._records_by_id)
        valid_active = sum(1 for v in self._validation_by_id.values() if v.is_valid and v.status == ExceptionRecordStatus.ACTIVE.value)
        expired = sum(1 for v in self._validation_by_id.values() if v.status == ExceptionRecordStatus.EXPIRED.value)
        rejected = total - valid_active

        all_valid = (total > 0 and valid_active == total)

        records_list = [r.to_dict() for r in self._records_by_id.values()]
        val_list = [v.to_dict() for v in self._validation_by_id.values()]

        # Sort deterministically
        records_list.sort(key=lambda x: x.get("exception_id", ""))
        val_list.sort(key=lambda x: x.get("exception_id", ""))

        report = RegistryAuditReport(
            schema_version=EXCEPTION_REGISTRY_SCHEMA,
            generated_at=now_iso,
            evaluation_as_of_date=eval_date_str,
            total_records=total,
            valid_active_count=valid_active,
            expired_count=expired,
            rejected_count=rejected,
            all_exceptions_valid_and_active=all_valid,
            repository_compliant=False,  # STRICT INVARIANT: never True due to exceptions!
            compliance_declaration="NON_COMPLIANT_WITH_EXCEPTIONS",
            findings_suppressed_count=0,  # Registry does NOT suppress findings
            records=records_list,
            validation_results=val_list,
        )
        report.to_dict()
        return report

    def to_markdown(self, report: RegistryAuditReport) -> str:
        """Render markdown audit table."""
        lines = [
            f"# Data-Access Reviewed Exceptions Audit",
            f"",
            f"- **Schema**: `{report.schema_version}`",
            f"- **Evaluation Date**: `{report.evaluation_as_of_date}`",
            f"- **Total Exception Records**: `{report.total_records}`",
            f"- **Valid & Active**: `{report.valid_active_count}`",
            f"- **Expired**: `{report.expired_count}`",
            f"- **Rejected / Malformed / Unsafe**: `{report.rejected_count}`",
            f"- **Repository Compliance**: `{'COMPLIANT' if report.repository_compliant else 'NON-COMPLIANT (Debt Tracked)'}`",
            f"- **Findings Suppressed**: `{report.findings_suppressed_count}` (Policy: Zero Suppression)",
            f"- **Audit Integrity SHA-256**: `{report.checksum}`",
            f"",
            f"## Exception Records Inventory",
            f"",
        ]

        if not report.records:
            lines.append("No exception records found.")
            return "\n".join(lines)

        lines.extend([
            "| ID | File | Line/Symbol | Rule | Owner | Reviewer | Expiry | Status | Migration Issue |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
        ])

        for r in report.records:
            loc = str(r.get("exact_line") or r.get("exact_symbol") or "n/a")
            lines.append(
                f"| `{r.get('exception_id')}` | `{r.get('exact_file')}` | `{loc}` | "
                f"`{r.get('rule_identifier')}` | `{r.get('owner')}` | `{r.get('reviewer')}` | "
                f"`{r.get('expiry_date')}` | **`{r.get('status')}`** | `{r.get('migration_issue')}` |"
            )

        if report.rejected_count > 0:
            lines.append("")
            lines.append("## Rejections & Fail-Closed Alerts")
            lines.append("")
            for val in report.validation_results:
                if not val.get("is_valid"):
                    eid = val.get("exception_id")
                    msgs = "; ".join(val.get("rejection_messages", []))
                    lines.append(f"- :x: **`{eid}`** [{val.get('status')}]: {msgs}")

        return "\n".join(lines)
