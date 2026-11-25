"""Legacy Acquisition Caller Detector and Migration Reporter.

Scans the repository for legacy, unconstrained, or unapproved data acquisition
patterns (such as full-object downloads, raw requests/urllib calls without byte ranges,
unbudgeted local disk writes, or missing license gates) and generates structured
RFC 8259 finite reports and migration guidance.
"""
from __future__ import annotations

import datetime
import os
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Sequence

from tools.data_access.approved_adapter.models import canonical_hash, finite_value

LEGACY_REPORTER_SCHEMA = "LegacyAcquisitionAuditReport.v1"

# Patterns indicating unconstrained or legacy download/acquisition calls
SUSPICIOUS_PATTERNS = [
    (
        r"urllib\.request\.urlretrieve\s*\(",
        "UNCONSTRAINED_URLRETRIEVE",
        "Direct urllib.request.urlretrieve downloads full object without byte bounding, checksums, or cache budget.",
    ),
    (
        r"urllib\.request\.urlopen\s*\(",
        "RAW_URLOPEN_CALL",
        "Raw urllib.request.urlopen without manifest-first planning or chunk bounding.",
    ),
    (
        r"requests\.get\s*\([^)]*stream\s*=\s*True",
        "STREAMING_REQUEST_UNBOUNDED",
        "Streaming requests.get may lack byte-range bounding, eviction guarantees, or license validation.",
    ),
    (
        r"s3\.download_file\s*\(",
        "RAW_S3_FULL_OBJECT",
        "Direct boto3 S3 object download without chunk range or budget eviction controls.",
    ),
    (
        r"s3_client\.get_object\s*\(",
        "RAW_S3_GET_OBJECT",
        "Direct S3 get_object call without approved adapter lease or cache management.",
    ),
    (
        r"openneuro\.download\s*\(",
        "LEGACY_OPENNEURO_SDK",
        "Legacy OpenNeuro SDK download invocation; should use BoundedAcquisitionRequest with explicit byte ranges.",
    ),
]

DEFAULT_EXCLUDES = [
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".pytest_cache",
    "tools/data_access/approved_adapter",
    "tools/data_access/chunk_cache",
    "tests/data_access/approved_adapter",
    "tests/data_access/chunk_cache",
    "tests/fixtures",
]


class LegacyCallerScanner:
    """Scans codebases for unapproved data-acquisition patterns."""

    def __init__(
        self,
        repo_root: str | Path,
        excludes: Optional[Sequence[str]] = None,
    ) -> None:
        self.repo_root = Path(repo_root).resolve()
        self.excludes = list(excludes or DEFAULT_EXCLUDES)

    def _is_excluded(self, path: Path) -> bool:
        rel = str(path.relative_to(self.repo_root)).replace("\\", "/")
        for excl in self.excludes:
            excl_norm = excl.replace("\\", "/").strip("/")
            if rel == excl_norm or rel.startswith(f"{excl_norm}/"):
                return True
        return False

    def scan(self) -> Dict[str, Any]:
        """Perform scan and return structured audit report dictionary."""
        findings: List[Dict[str, Any]] = []

        # Walk Python files
        for root, dirs, files in os.walk(self.repo_root):
            root_path = Path(root)
            if self._is_excluded(root_path):
                # Prune excluded directory descent
                dirs[:] = []
                continue

            # Remove excluded dirs from traversal
            dirs[:] = [d for d in dirs if not self._is_excluded(root_path / d)]

            for file_name in files:
                if not file_name.endswith(".py"):
                    continue
                file_path = root_path / file_name
                if self._is_excluded(file_path):
                    continue

                rel_file_str = str(file_path.relative_to(self.repo_root)).replace("\\", "/")

                try:
                    content = file_path.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue

                lines = content.splitlines()
                for line_idx, line in enumerate(lines, start=1):
                    line_stripped = line.strip()
                    if line_stripped.startswith("#"):
                        continue

                    for regex_pattern, risk_code, description in SUSPICIOUS_PATTERNS:
                        if re.search(regex_pattern, line):
                            findings.append({
                                "file_path": rel_file_str,
                                "line_number": line_idx,
                                "risk_code": risk_code,
                                "description": description,
                                "matched_snippet": line_stripped[:120],
                                "recommended_migration": (
                                    f"Replace with ApprovedAcquisitionAdapter.acquire(BoundedAcquisitionRequest(...)) "
                                    f"with explicit byte_range, license_state, and declared_consumers."
                                ),
                            })

        # Special known legacy files check
        known_legacy_paths = [
            "dataset_acquisition/download_eeg.py",
            "scripts/fetch_real_datasets.py",
            "scripts/download_sample_data.py",
        ]
        for legacy_rel in known_legacy_paths:
            lp = self.repo_root / legacy_rel
            if lp.is_file() and not any(f["file_path"] == legacy_rel for f in findings):
                findings.append({
                    "file_path": legacy_rel,
                    "line_number": 1,
                    "risk_code": "LEGACY_DATASET_ACQUISITION_FILE",
                    "description": "Known unapproved legacy dataset downloader script.",
                    "matched_snippet": f"File exists: {legacy_rel}",
                    "recommended_migration": (
                        "Migrate pipeline to plan_bounded_acquisition.py CLI or ApprovedAcquisitionAdapter."
                    ),
                })

        # Sort findings deterministically
        findings.sort(key=lambda x: (x["file_path"], x["line_number"], x["risk_code"]))

        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        report_data = {
            "schema_version": LEGACY_REPORTER_SCHEMA,
            "generated_at": now_iso,
            "repo_root": str(self.repo_root),
            "total_findings": len(findings),
            "findings": findings,
        }

        report_hash = canonical_hash(finite_value(report_data))
        report_data["checksum"] = report_hash
        return report_data

    def to_markdown(self, report: Dict[str, Any]) -> str:
        """Render markdown audit table."""
        lines = [
            f"# Legacy Acquisition Callers Audit Report",
            f"",
            f"- **Schema**: `{report.get('schema_version')}`",
            f"- **Generated At**: `{report.get('generated_at')}`",
            f"- **Total Findings**: `{report.get('total_findings')}`",
            f"- **Integrity SHA-256**: `{report.get('checksum')}`",
            f"",
            f"## Detected Legacy Patterns",
            f"",
        ]

        if not report.get("findings"):
            lines.append("No unapproved legacy acquisition callers detected in the scanned paths.")
            return "\n".join(lines)

        lines.extend([
            "| File | Line | Risk Code | Matched Snippet | Recommended Migration |",
            "| --- | --- | --- | --- | --- |",
        ])

        for f in report["findings"]:
            file_p = f["file_path"]
            line_no = f["line_number"]
            risk = f["risk_code"]
            snippet = f["matched_snippet"].replace("|", "\\|")
            migr = f["recommended_migration"].replace("|", "\\|")
            lines.append(f"| `{file_p}` | {line_no} | `{risk}` | `{snippet}` | {migr} |")

        return "\n".join(lines)


def scan_legacy_callers(
    repo_root: str | Path,
    excludes: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Scan the repository for legacy acquisition callers and return a structured report."""
    scanner = LegacyCallerScanner(repo_root=repo_root, excludes=excludes)
    return scanner.scan()
