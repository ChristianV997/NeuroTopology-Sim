"""Validator for Batch-2 pipeline artifact packs and reports."""
from __future__ import annotations

import argparse
from collections import Counter
import json
import math
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.parse import urlparse

from .budgets import budget_result_is_consistent
from .schema import (
    EVIDENCE_CLASS,
    FORBIDDEN_PHRASES,
    REQUIRED_OUTPUT_FILES,
    SCHEMA_VERSION,
    TARGET_NAMES,
    TargetStatus,
)

# Remote hosts forbidden in synthetic local performance evidence.
# Checked via parsed hostnames (exact / DNS-suffix), not raw substring scans.
_REMOTE_HOST_EXACT = frozenset(
    {
        "openneuro.org",
        "www.openneuro.org",
        "amazonaws.com",
        "dandiarchive.org",
        "www.dandiarchive.org",
        "api.dandiarchive.org",
    }
)
_REMOTE_HOST_SUFFIXES = (
    ".openneuro.org",
    ".amazonaws.com",
    ".dandiarchive.org",
)
_URL_TOKEN = re.compile(r"(?:[a-z][a-z0-9+.-]*://|//)[^\s<>\"']+", re.IGNORECASE)
_HOSTISH = re.compile(
    r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}$",
    re.IGNORECASE,
)
_HOST_PATH_TOKEN = re.compile(
    r"(?<![a-z0-9._/-])"
    r"((?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,})"
    r"(?::[0-9]{1,5})?(?:/[^\s<>\"']*|\?[^\s<>\"']*)",
    re.IGNORECASE,
)


def _hostname_is_remote(host: str | None) -> bool:
    if not host:
        return False
    host = host.lower().rstrip(".")
    if host in _REMOTE_HOST_EXACT:
        return True
    return any(host.endswith(suffix) for suffix in _REMOTE_HOST_SUFFIXES)


def _string_references_remote_host(value: str) -> bool:
    """Return True iff ``value`` names a forbidden remote host (URL or bare host)."""
    text = value.strip()
    if not text:
        return False
    # Find URLs anywhere in prose, trimming punctuation commonly adjacent to links.
    for match in _URL_TOKEN.finditer(text):
        candidate = match.group(0).rstrip(".,;:!?)]}")
        try:
            hostname = urlparse(candidate).hostname
        except ValueError:
            continue
        if _hostname_is_remote(hostname):
            return True
    # Also recognize the common scheme-less ``host/path`` form in prose.
    # Requiring a path/query avoids treating an ordinary bare-host mention as
    # a URL; the slash boundary avoids matching host-like text inside a URL path.
    for match in _HOST_PATH_TOKEN.finditer(text):
        if _hostname_is_remote(match.group(1)):
            return True
    # Bare hostname tokens only (avoids incomplete substring matches inside prose).
    if _HOSTISH.match(text):
        return _hostname_is_remote(text)
    return False


def _iter_strings(obj: Any) -> Iterable[str]:
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for key, value in obj.items():
            if isinstance(key, str):
                yield key
            yield from _iter_strings(value)
    elif isinstance(obj, list):
        for item in obj:
            yield from _iter_strings(item)


def _scan_remote_hosts(report: Dict[str, Any], violations: List[str]) -> None:
    for value in _iter_strings(report):
        if _string_references_remote_host(value):
            violations.append("remote_data_reference")
            return


def _finite(obj: Any, path: str, violations: List[str]) -> None:
    if isinstance(obj, float):
        if not math.isfinite(obj):
            violations.append(f"non_finite:{path}")
    elif isinstance(obj, dict):
        for key, value in obj.items():
            _finite(value, f"{path}.{key}", violations)
    elif isinstance(obj, list):
        for index, value in enumerate(obj):
            _finite(value, f"{path}[{index}]", violations)


def _scan_forbidden(text: str, violations: List[str], label: str) -> None:
    lowered = text.lower()
    for phrase in FORBIDDEN_PHRASES:
        if phrase in lowered:
            violations.append(f"forbidden:{label}:{phrase}")


def _aggregate_complete_boolean(values: List[Optional[bool]]) -> Optional[bool]:
    if any(value is False for value in values):
        return False
    if values and all(value is True for value in values):
        return True
    return None


def validate_report(report: Dict[str, Any]) -> Dict[str, Any]:
    violations: List[str] = []
    if not isinstance(report, dict):
        return {
            "ok": False,
            "violations": ["invalid_report_type"],
            "evidence_class": EVIDENCE_CLASS,
            "schema": SCHEMA_VERSION,
        }
    if report.get("schema") != SCHEMA_VERSION and report.get("schema_version") != SCHEMA_VERSION:
        violations.append("schema_mismatch")
    if report.get("evidence_class") != EVIDENCE_CLASS:
        violations.append("evidence_class_mismatch")
    if report.get("synthetic") is not True:
        violations.append("synthetic_flag_missing")
    config = report.get("config")
    if not isinstance(config, dict):
        violations.append("invalid_config")
        config = {}
    max_workers = config.get("max_workers")
    if type(max_workers) is not int or max_workers != 1:
        violations.append("unbounded_workers")
    results = report.get("results")
    if not isinstance(results, list):
        violations.append("invalid_results")
        results = []
    if not results:
        violations.append("empty_results")
    target_names: List[Any] = []
    status_counts: Counter[str] = Counter()
    checksum_matches: List[Optional[bool]] = []
    budget_verdicts: List[Optional[bool]] = []
    known_statuses = {status.value for status in TargetStatus}
    for row in results:
        if not isinstance(row, dict):
            violations.append("invalid_result")
            continue
        target = row.get("target")
        target_names.append(target)
        if not isinstance(target, str) or target not in TARGET_NAMES:
            violations.append("unknown_target")
        if row.get("synthetic") is not True:
            violations.append(f"row_synthetic_flag_mismatch:{target}")
        status = row.get("status")
        if not isinstance(status, str) or status not in known_statuses:
            violations.append(f"unknown_status:{target}")
        else:
            status_counts[status] += 1
            if status == TargetStatus.MALFORMED_RECORD.value:
                violations.append(f"malformed_record:{target}")

        det = row.get("deterministic") or {}
        if not isinstance(det, dict):
            violations.append(f"missing_checksum_match:{target}")
            det = {}
        if "checksum_match" not in det:
            violations.append(f"missing_checksum_match:{target}")
        checksum_match = det.get("checksum_match")
        checksum_matches.append(checksum_match)
        if (
            checksum_match is not True
            and checksum_match is not False
            and checksum_match is not None
        ):
            violations.append(f"invalid_checksum_match:{target}")
        if status == TargetStatus.OK.value and checksum_match is not True:
            violations.append(f"success_without_checksum:{target}")

        budget = det.get("budget")
        if budget is None:
            budget_verdict = None
        elif isinstance(budget, dict):
            budget_verdict = budget.get("within_budget")
            if not budget_result_is_consistent(budget):
                violations.append(f"budget_checks_mismatch:{target}")
        else:
            violations.append(f"invalid_budget:{target}")
            budget_verdict = None
        if (
            budget_verdict is not True
            and budget_verdict is not False
            and budget_verdict is not None
        ):
            violations.append(f"invalid_budget_verdict:{target}")
        budget_verdicts.append(budget_verdict)
        if status == TargetStatus.OK.value and budget_verdict is not True:
            violations.append(f"success_without_budget:{target}")

        tel = row.get("telemetry")
        if tel is not None and not isinstance(tel, dict):
            violations.append(f"invalid_telemetry:{target}")
        elif tel:
            for side in ("baseline", "candidate"):
                view = tel.get(side) or {}
                if not isinstance(view, dict):
                    violations.append(f"invalid_telemetry:{target}:{side}")
                    continue
                for key in ("rss_after_bytes", "tracemalloc_peak_bytes"):
                    if key in view and view[key] == 0:
                        violations.append(f"zero_metric:{target}:{side}:{key}")
        if row.get("evidence_class") != EVIDENCE_CLASS:
            violations.append(f"row_evidence_class:{target}")

    declared_count = report.get("num_targets")
    if type(declared_count) is not int or declared_count != len(results):
        violations.append("target_count_mismatch")
    summary = report.get("summary")
    if (
        not isinstance(summary, dict)
        or any(type(count) is not int or count < 0 for count in summary.values())
        or dict(status_counts) != summary
    ):
        violations.append("summary_mismatch")

    if "targets" not in config:
        violations.append("missing_target_selection")
    else:
        configured_targets = config.get("targets")
        if not isinstance(configured_targets, list):
            violations.append("invalid_target_selection")
        else:
            if not configured_targets:
                violations.append("empty_target_selection")
            if any(
                not isinstance(target, str) or target not in TARGET_NAMES
                for target in configured_targets
            ):
                violations.append("unknown_target")
            if configured_targets != target_names:
                violations.append("target_selection_mismatch")

    all_equivalent = report.get("all_equivalent")
    if all_equivalent is not True and all_equivalent is not False and all_equivalent is not None:
        violations.append("invalid_equivalence_verdict")
    elif all_equivalent is not _aggregate_complete_boolean(checksum_matches):
        violations.append("equivalence_claim_mismatch")

    all_within_budget = report.get("all_within_budget")
    if (
        all_within_budget is not True
        and all_within_budget is not False
        and all_within_budget is not None
    ):
        violations.append("invalid_budget_verdict")
    elif all_within_budget is not _aggregate_complete_boolean(budget_verdicts):
        violations.append("budget_claim_mismatch")

    blob = json.dumps(report, allow_nan=False, default=str)
    _scan_forbidden(blob, violations, "report")
    _finite(report, "$", violations)
    _scan_remote_hosts(report, violations)
    return {
        "ok": not violations,
        "violations": violations,
        "evidence_class": EVIDENCE_CLASS,
        "schema": SCHEMA_VERSION,
    }


def validate_root(root: str | Path) -> Dict[str, Any]:
    root = Path(root)
    violations: List[str] = []
    for rel in REQUIRED_OUTPUT_FILES:
        if not (root / rel).exists():
            violations.append(f"missing:{rel}")
    report_path = root / "batch2_pipeline_report.json"
    report_result: Dict[str, Any] = {}
    if report_path.exists():
        report = json.loads(report_path.read_text(encoding="utf-8"))
        report_result = validate_report(report)
        violations.extend(report_result.get("violations") or [])
    for path in root.rglob("*"):
        if path.is_file() and path.suffix in {".md", ".json"}:
            _scan_forbidden(path.read_text(encoding="utf-8", errors="replace"), violations, str(path.name))
    return {
        "ok": not violations,
        "violations": violations,
        "root": str(root),
        "evidence_class": EVIDENCE_CLASS,
        "report": report_result,
    }


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate a Batch-2 pipeline artifact pack.")
    parser.add_argument("--root", required=True)
    parser.add_argument("--json-out", default=None)
    args = parser.parse_args(argv)
    result = validate_root(args.root)
    if args.json_out:
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(json.dumps(result, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"ok": result["ok"], "n_violations": len(result["violations"])}))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
