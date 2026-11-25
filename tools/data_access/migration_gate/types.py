"""Data models, classification enums, and schemas for data-access migration gating."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

MANIFEST_SCHEMA_VERSION = "NeuroTopology.DataAccessMigrationManifest.v1"
REPORT_SCHEMA_VERSION = "NeuroTopology.DataAccessMigrationGateReport.v1"


class MigrationStatus(str, Enum):
    """The 6 strictly required migration classification states."""

    UNMIGRATED = "unmigrated"
    SAFELY_MIGRATED = "safely migrated"
    REVIEWED_TEMPORARY_EXCEPTION = "reviewed temporary exception"
    UNSAFE_BLOCKED = "unsafe blocked"
    NOT_APPLICABLE = "not applicable"
    UNABLE_TO_ASSESS = "unable to assess"


# Prohibited rules for which ANY exception is unsafe and strictly forbidden
PROHIBITED_EXCEPTION_RULES: frozenset[str] = frozenset(
    {
        # Full-dataset downloads
        "UNAUTHORIZED_OPENNEURO_DOWNLOAD",
        "UNAUTHORIZED_AWS_FULL_TRANSFER",
        "UNAUTHORIZED_SHELL_TRANSFER",
        "UNAUTHORIZED_BOTO3_FULL_OBJECT",
        # Unbounded reads
        "UNBOUNDED_REMOTE_MATERIALIZATION",
        "MISSING_CACHE_BOUND",
        # Missing checksums
        "MISSING_CHECKSUM",
        # Output escapes
        "OUTPUT_ROOT_ESCAPE",
        # Network-enabled defaults
        "NETWORK_ENABLED_BY_DEFAULT",
        # Scanner failures
        "POLICY_READ_FAILURE",
        "POLICY_PARSE_FAILURE",
    }
)

# Prohibited category keywords
PROHIBITED_EXCEPTION_CATEGORIES: frozenset[str] = frozenset(
    {
        "full_dataset_download",
        "unbounded_materialization",
        "path_containment",
        "network_policy",
        "scanner_failure",
    }
)

# Permanent expiration tokens that must be rejected
PERMANENT_EXPIRATION_TOKENS: frozenset[str] = frozenset(
    {
        "permanent",
        "never",
        "none",
        "null",
        "infinite",
        "infinity",
        "unlimited",
        "forever",
        "n/a",
        "na",
        "",
    }
)


def json_safe(data: Any) -> Any:
    """Recursively convert data to strict, finite JSON-compatible structures.

    Rejects float NaN, Inf, and non-finite numbers.
    """
    if data is None or isinstance(data, (bool, str, int)):
        return data
    if isinstance(data, float):
        if not math.isfinite(data):
            raise ValueError(f"Non-finite float value encountered: {data}")
        return data
    if isinstance(data, Enum):
        return data.value
    if isinstance(data, (list, tuple, set, frozenset)):
        return [json_safe(item) for item in data]
    if isinstance(data, Mapping):
        return {str(k): json_safe(v) for k, v in data.items()}
    if hasattr(data, "to_dict") and callable(data.to_dict):
        return json_safe(data.to_dict())
    if hasattr(data, "__dict__"):
        return json_safe(data.__dict__)
    return str(data)


@dataclass(frozen=True)
class MigrationEntry:
    """An exact, tracked item in the migration inventory."""

    file: str
    symbol_or_line: str
    rule: str
    owner: str
    migration_reference: str
    status: MigrationStatus
    severity: str = "error"
    reviewer: str | None = None
    expires_at: str | None = None
    justification: str | None = None
    notes: str | None = None

    def __post_init__(self) -> None:
        # Validate status enum
        if isinstance(self.status, str):
            object.__setattr__(self, "status", MigrationStatus(self.status))

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "symbol_or_line": str(self.symbol_or_line),
            "rule": self.rule,
            "owner": self.owner,
            "migration_reference": self.migration_reference,
            "status": self.status.value,
            "severity": self.severity,
            "reviewer": self.reviewer,
            "expires_at": self.expires_at,
            "justification": self.justification,
            "notes": self.notes,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> MigrationEntry:
        status_val = data.get("status")
        if isinstance(status_val, str):
            status = MigrationStatus(status_val)
        elif isinstance(status_val, MigrationStatus):
            status = status_val
        else:
            raise ValueError(f"Invalid migration status: {status_val}")

        return cls(
            file=str(data.get("file", "")),
            symbol_or_line=str(data.get("symbol_or_line", "")),
            rule=str(data.get("rule", "")),
            owner=str(data.get("owner", "")),
            migration_reference=str(data.get("migration_reference", "")),
            status=status,
            severity=str(data.get("severity", "error")),
            reviewer=data.get("reviewer"),
            expires_at=data.get("expires_at"),
            justification=data.get("justification"),
            notes=data.get("notes"),
        )


@dataclass
class MigrationManifest:
    """Manifest representing the repository's known data-access migration state."""

    schema_version: str = MANIFEST_SCHEMA_VERSION
    as_of_date: str = "1970-01-01"
    entries: list[MigrationEntry] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "as_of_date": self.as_of_date,
            "entries": [entry.to_dict() for entry in self.entries],
            "entry_count": len(self.entries),
            "metadata": dict(self.metadata),
        }

    def to_json(self, *, indent: int = 2) -> str:
        safe_dict = json_safe(self.to_dict())
        return json.dumps(safe_dict, sort_keys=True, indent=indent, allow_nan=False) + "\n"

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> MigrationManifest:
        entries = [MigrationEntry.from_dict(item) for item in data.get("entries", [])]
        return cls(
            schema_version=str(data.get("schema_version", MANIFEST_SCHEMA_VERSION)),
            as_of_date=str(data.get("as_of_date", "1970-01-01")),
            entries=entries,
            metadata=dict(data.get("metadata", {})),
        )

    @classmethod
    def from_file(cls, path: str | Path) -> MigrationManifest:
        text = Path(path).read_text(encoding="utf-8")
        data = json.loads(text)
        return cls.from_dict(data)


@dataclass(frozen=True)
class GateClassification:
    """Evaluation of a specific scanner finding against the migration gate."""

    file: str
    line: int
    rule: str
    severity: str
    category: str
    status: MigrationStatus
    owner: str | None
    migration_reference: str | None
    reason: str
    is_blocker: bool
    is_resolved: bool
    entry: dict[str, Any] | None = None
    source_snippet: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "line": self.line,
            "rule": self.rule,
            "severity": self.severity,
            "category": self.category,
            "status": self.status.value,
            "owner": self.owner,
            "migration_reference": self.migration_reference,
            "reason": self.reason,
            "is_blocker": self.is_blocker,
            "is_resolved": self.is_resolved,
            "entry": self.entry,
            "source_snippet": self.source_snippet,
        }


@dataclass
class GateReport:
    """Final, deterministic gate report containing before/after counts and audit trails."""

    schema_version: str = REPORT_SCHEMA_VERSION
    evaluation_date: str = "1970-01-01"
    repository_root: str = "."
    gate_passed: bool = False
    compliance_claim_allowed: bool = False
    compliance_statement: str = ""
    before_counts: dict[str, Any] = field(default_factory=dict)
    after_counts: dict[str, Any] = field(default_factory=dict)
    classifications: list[GateClassification] = field(default_factory=list)
    stale_exceptions: list[dict[str, Any]] = field(default_factory=list)
    hidden_findings: list[dict[str, Any]] = field(default_factory=list)
    unsafe_approvals: list[dict[str, Any]] = field(default_factory=list)
    fail_closed_reasons: list[str] = field(default_factory=list)
    checksum: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "evaluation_date": self.evaluation_date,
            "repository_root": self.repository_root,
            "gate_passed": self.gate_passed,
            "compliance_claim_allowed": self.compliance_claim_allowed,
            "compliance_statement": self.compliance_statement,
            "before_counts": dict(self.before_counts),
            "after_counts": dict(self.after_counts),
            "classifications": [item.to_dict() for item in self.classifications],
            "stale_exceptions": list(self.stale_exceptions),
            "hidden_findings": list(self.hidden_findings),
            "unsafe_approvals": list(self.unsafe_approvals),
            "fail_closed_reasons": list(self.fail_closed_reasons),
            "checksum": self.checksum,
        }

    def to_json(self, *, indent: int = 2) -> str:
        safe_dict = json_safe(self.to_dict())
        return json.dumps(safe_dict, sort_keys=True, indent=indent, allow_nan=False) + "\n"

    def compute_checksum(self) -> str:
        data = self.to_dict()
        data["checksum"] = ""
        canonical = json.dumps(json_safe(data), sort_keys=True, separators=(",", ":"), allow_nan=False)
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def human_summary(self) -> str:
        status = "GATE_PASSED" if self.gate_passed else "GATE_BLOCKED"
        unmigrated = self.after_counts.get("unmigrated", 0)
        blocked = self.after_counts.get("unsafe_blocked", 0)
        stale = len(self.stale_exceptions)
        hidden = len(self.hidden_findings)
        unsafe = len(self.unsafe_approvals)
        claim_flag = "ALLOWED" if self.compliance_claim_allowed else "PROHIBITED"

        return (
            f"[{status}] total_before={self.before_counts.get('total', 0)} "
            f"unmigrated={unmigrated} unsafe_blocked={blocked} stale={stale} "
            f"hidden={hidden} unsafe_approvals={unsafe} "
            f"compliance_claim={claim_flag}"
        )

    def to_markdown(self) -> str:
        lines: list[str] = [
            "# Data-Access Migration Gate Report",
            "",
            f"- **Schema Version**: `{self.schema_version}`",
            f"- **Evaluation Date**: `{self.evaluation_date}`",
            f"- **Gate Status**: **{'PASS' if self.gate_passed else 'BLOCKED'}**",
            f"- **Repository-Wide Compliance Claim**: **{'ALLOWED' if self.compliance_claim_allowed else 'PROHIBITED'}**",
            f"- **Compliance Statement**: {self.compliance_statement}",
            f"- **Report Checksum (SHA-256)**: `{self.checksum}`",
            "",
            "## Summary Metrics",
            "",
            "| Metric | Count |",
            "| :--- | :--- |",
            f"| **Raw Scanner Findings (Before)** | {self.before_counts.get('total', 0)} |",
            f"| ↳ Critical | {self.before_counts.get('by_severity', {}).get('critical', 0)} |",
            f"| ↳ Error | {self.before_counts.get('by_severity', {}).get('error', 0)} |",
            f"| ↳ Warning | {self.before_counts.get('by_severity', {}).get('warning', 0)} |",
            f"| **Classified Findings (After)** | {len(self.classifications)} |",
            f"| ↳ Safely Migrated | {self.after_counts.get('safely_migrated', 0)} |",
            f"| ↳ Reviewed Temporary Exception | {self.after_counts.get('reviewed_temporary_exception', 0)} |",
            f"| ↳ Unmigrated (Active Debt) | {self.after_counts.get('unmigrated', 0)} |",
            f"| ↳ Unsafe Blocked | {self.after_counts.get('unsafe_blocked', 0)} |",
            f"| ↳ Not Applicable | {self.after_counts.get('not_applicable', 0)} |",
            f"| ↳ Unable to Assess | {self.after_counts.get('unable_to_assess', 0)} |",
            f"| **Hidden/Untracked Findings** | {len(self.hidden_findings)} |",
            f"| **Stale/Expired Exceptions** | {len(self.stale_exceptions)} |",
            f"| **Unsafe Approval Attempts** | {len(self.unsafe_approvals)} |",
            f"| **Total Unresolved Violations** | {self.after_counts.get('unresolved_total', 0)} |",
            "",
        ]

        if self.fail_closed_reasons:
            lines.extend([
                "## Fail-Closed Reasons",
                "",
            ])
            for reason in self.fail_closed_reasons:
                lines.append(f"- ⛔ **FAIL CLOSED**: {reason}")
            lines.append("")

        if self.hidden_findings:
            lines.extend([
                "## Hidden / Untracked Violations",
                "",
                "The following findings were detected by the scanner but omitted from the migration manifest:",
                "",
                "| File | Line | Rule | Severity | Remediation |",
                "| :--- | :--- | :--- | :--- | :--- |",
            ])
            for h in self.hidden_findings:
                lines.append(f"| `{h.get('file')}` | {h.get('line')} | `{h.get('rule')}` | `{h.get('severity')}` | {h.get('remediation', '')} |")
            lines.append("")

        if self.stale_exceptions:
            lines.extend([
                "## Stale / Expired Exceptions",
                "",
                "| File | Rule | Owner | Expiration | Reason |",
                "| :--- | :--- | :--- | :--- | :--- |",
            ])
            for s in self.stale_exceptions:
                lines.append(f"| `{s.get('file')}` | `{s.get('rule')}` | `{s.get('owner')}` | `{s.get('expires_at')}` | {s.get('reason')} |")
            lines.append("")

        if self.unsafe_approvals:
            lines.extend([
                "## Unsafe Approval Attempts",
                "",
                "| File | Rule | Owner | Prohibited Reason |",
                "| :--- | :--- | :--- | :--- |",
            ])
            for u in self.unsafe_approvals:
                lines.append(f"| `{u.get('file')}` | `{u.get('rule')}` | `{u.get('owner')}` | {u.get('reason')} |")
            lines.append("")

        lines.extend([
            "## Itemized Classification Inventory",
            "",
            "| File | Line | Rule | Status | Owner | Reference | Blocker? |",
            "| :--- | :--- | :--- | :--- | :--- | :--- | :--- |",
        ])
        for c in self.classifications:
            blocker_mark = "⛔ YES" if c.is_blocker else "✅ NO"
            ref = c.migration_reference or "-"
            owner = c.owner or "-"
            lines.append(f"| `{c.file}` | {c.line} | `{c.rule}` | `{c.status.value}` | `{owner}` | `{ref}` | {blocker_mark} |")

        lines.append("")
        return "\n".join(lines)
