"""Classification engine pairing scanner findings with migration tracking entries."""

from __future__ import annotations

import datetime
from typing import Any, Iterable, Mapping, Sequence

from .types import (
    GateClassification,
    MigrationEntry,
    MigrationManifest,
    MigrationStatus,
)
from .validator import (
    EntryValidationResult,
    is_prohibited_exception_rule,
    is_stale_expiration,
    is_wildcard_string,
    validate_migration_entry,
)


def _matches_location(finding_line: int, symbol_or_line: str) -> bool:
    """Check if finding line matches the entry's line number or symbol."""
    sym_clean = str(symbol_or_line).strip()
    if sym_clean.isdigit():
        return int(sym_clean) == finding_line
    # If it is a symbol name, we match by file and rule (line level may shift during edits)
    return True


class MigrationClassifier:
    """Classifies scanner findings against an authoritative migration manifest."""

    def __init__(
        self,
        manifest: MigrationManifest,
        *,
        current_date: datetime.date | str | None = None,
    ) -> None:
        self.manifest = manifest
        if current_date is None:
            self.current_date = datetime.date.today()
        elif isinstance(current_date, datetime.date):
            self.current_date = current_date
        else:
            self.current_date = datetime.date.fromisoformat(str(current_date).strip())

        # Build index: (file, rule) -> list[MigrationEntry]
        self._index: dict[tuple[str, str], list[MigrationEntry]] = {}
        for entry in manifest.entries:
            key = (entry.file.strip(), entry.rule.strip())
            self._index.setdefault(key, []).append(entry)

    def _find_matching_entry(self, finding: Mapping[str, Any]) -> MigrationEntry | None:
        file_val = str(finding.get("file", "")).strip()
        rule_val = str(finding.get("rule", "")).strip()
        line_val = int(finding.get("line", 1))

        candidates = self._index.get((file_val, rule_val), [])
        if not candidates:
            # Also try matching with normalized forward-slashes
            norm_file = file_val.replace("\\", "/")
            for (f, r), entries in self._index.items():
                if f.replace("\\", "/") == norm_file and r == rule_val:
                    candidates = entries
                    break

        if not candidates:
            return None

        # Prioritize exact line number match if available
        for c in candidates:
            if str(c.symbol_or_line).strip().isdigit() and int(c.symbol_or_line) == line_val:
                return c

        # Otherwise return the first candidate matching the file and rule
        return candidates[0]

    def classify_finding(self, finding: Mapping[str, Any]) -> tuple[GateClassification, dict[str, Any] | None, dict[str, Any] | None, dict[str, Any] | None]:
        """Classify a single scanner finding against the manifest.

        Returns:
            (classification, hidden_finding_dict_or_None, stale_dict_or_None, unsafe_dict_or_None)
        """
        file_val = str(finding.get("file", "")).strip()
        line_val = int(finding.get("line", 1))
        rule_val = str(finding.get("rule", "")).strip()
        severity_val = str(finding.get("severity", "error")).strip()
        category_val = str(finding.get("category", "unknown")).strip()
        source_val = finding.get("source")
        remediation_val = str(finding.get("remediation", ""))

        entry = self._find_matching_entry(finding)

        # 1. Hidden / Untracked finding: not in manifest
        if entry is None:
            hidden_info = {
                "file": file_val,
                "line": line_val,
                "rule": rule_val,
                "severity": severity_val,
                "category": category_val,
                "remediation": remediation_val,
                "reason": "Violation detected by scanner but omitted from migration manifest (untracked debt).",
            }
            classification = GateClassification(
                file=file_val,
                line=line_val,
                rule=rule_val,
                severity=severity_val,
                category=category_val,
                status=MigrationStatus.UNSAFE_BLOCKED,
                owner=None,
                migration_reference=None,
                reason="Untracked finding: violation exists in codebase but is not registered in migration manifest.",
                is_blocker=True,
                is_resolved=False,
                entry=None,
                source_snippet=source_val,
            )
            return classification, hidden_info, None, None

        # 2. Validate the manifest entry
        val_res: EntryValidationResult = validate_migration_entry(entry, current_date=self.current_date)

        stale_info: dict[str, Any] | None = None
        unsafe_info: dict[str, Any] | None = None

        if val_res.is_prohibited_exception or val_res.is_permanent or val_res.is_wildcard:
            unsafe_info = {
                "file": entry.file,
                "symbol_or_line": entry.symbol_or_line,
                "rule": entry.rule,
                "owner": entry.owner,
                "reason": "; ".join(val_res.errors),
            }

        if val_res.is_stale:
            stale_info = {
                "file": entry.file,
                "rule": entry.rule,
                "owner": entry.owner,
                "expires_at": entry.expires_at,
                "reason": f"Exception expired on {entry.expires_at}.",
            }

        # 3. Check for false migration claim: entry says safely migrated, but finding still exists!
        if entry.status == MigrationStatus.SAFELY_MIGRATED:
            reason = (
                f"Manifest claims finding is 'safely migrated' under {entry.migration_reference}, "
                f"but scanner still detected an active violation at line {line_val}."
            )
            classification = GateClassification(
                file=file_val,
                line=line_val,
                rule=rule_val,
                severity=severity_val,
                category=category_val,
                status=MigrationStatus.UNSAFE_BLOCKED,
                owner=entry.owner,
                migration_reference=entry.migration_reference,
                reason=reason,
                is_blocker=True,
                is_resolved=False,
                entry=entry.to_dict(),
                source_snippet=source_val,
            )
            return classification, None, None, {"file": entry.file, "rule": entry.rule, "owner": entry.owner, "reason": reason}

        # 4. Handle validation failures
        if not val_res.is_valid:
            reason = f"Entry validation failed: {'; '.join(val_res.errors)}"
            classification = GateClassification(
                file=file_val,
                line=line_val,
                rule=rule_val,
                severity=severity_val,
                category=category_val,
                status=val_res.status,
                owner=entry.owner,
                migration_reference=entry.migration_reference,
                reason=reason,
                is_blocker=True,
                is_resolved=False,
                entry=entry.to_dict(),
                source_snippet=source_val,
            )
            return classification, None, stale_info, unsafe_info

        # 5. Handle regular valid statuses
        if entry.status == MigrationStatus.REVIEWED_TEMPORARY_EXCEPTION:
            reason = f"Active reviewed temporary exception approved by {entry.reviewer} until {entry.expires_at}: {entry.justification}"
            classification = GateClassification(
                file=file_val,
                line=line_val,
                rule=rule_val,
                severity=severity_val,
                category=category_val,
                status=MigrationStatus.REVIEWED_TEMPORARY_EXCEPTION,
                owner=entry.owner,
                migration_reference=entry.migration_reference,
                reason=reason,
                is_blocker=False,
                is_resolved=False,
                entry=entry.to_dict(),
                source_snippet=source_val,
            )
            return classification, None, None, None

        if entry.status == MigrationStatus.UNMIGRATED:
            reason = f"Tracked legacy violation awaiting migration under {entry.migration_reference} (owner: {entry.owner})."
            classification = GateClassification(
                file=file_val,
                line=line_val,
                rule=rule_val,
                severity=severity_val,
                category=category_val,
                status=MigrationStatus.UNMIGRATED,
                owner=entry.owner,
                migration_reference=entry.migration_reference,
                reason=reason,
                is_blocker=False,  # Not an immediate fail-closed blocker, but active debt that prohibits compliance claim
                is_resolved=False,
                entry=entry.to_dict(),
                source_snippet=source_val,
            )
            return classification, None, None, None

        if entry.status == MigrationStatus.NOT_APPLICABLE:
            reason = f"Marked not applicable with justification: {entry.justification} ({entry.migration_reference})"
            classification = GateClassification(
                file=file_val,
                line=line_val,
                rule=rule_val,
                severity=severity_val,
                category=category_val,
                status=MigrationStatus.NOT_APPLICABLE,
                owner=entry.owner,
                migration_reference=entry.migration_reference,
                reason=reason,
                is_blocker=False,
                is_resolved=True,
                entry=entry.to_dict(),
                source_snippet=source_val,
            )
            return classification, None, None, None

        # Fallback
        classification = GateClassification(
            file=file_val,
            line=line_val,
            rule=rule_val,
            severity=severity_val,
            category=category_val,
            status=entry.status,
            owner=entry.owner,
            migration_reference=entry.migration_reference,
            reason=f"Status: {entry.status.value}",
            is_blocker=entry.status in (MigrationStatus.UNSAFE_BLOCKED, MigrationStatus.UNABLE_TO_ASSESS),
            is_resolved=entry.status == MigrationStatus.SAFELY_MIGRATED,
            entry=entry.to_dict(),
            source_snippet=source_val,
        )
        return classification, None, None, None
