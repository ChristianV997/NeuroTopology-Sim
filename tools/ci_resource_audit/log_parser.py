"""Deterministic, local-only classification of captured CI logs."""
from __future__ import annotations

import re
from typing import Any


FAILURE_CLASSES = (
    "test_failure",
    "import_failure",
    "dependency_resolution_failure",
    "disk_exhaustion",
    "memory_exhaustion",
    "network_resolution_failure",
    "billing_or_runner_blocked",
    "workflow_configuration_failure",
    "unknown_infrastructure_failure",
)

_SIGNATURES: dict[str, tuple[tuple[str, re.Pattern[str]], ...]] = {
    "disk_exhaustion": (
        ("no_space_left", re.compile(r"no space left on device|enospc|disk quota exceeded|not enough space on (?:the )?disk|no usable temporary directory", re.I)),
    ),
    "memory_exhaustion": (
        ("memory_error", re.compile(r"memoryerror|out of memory|oomkilled|cannot allocate memory|cuda out of memory|out-of-memory", re.I)),
        ("oom_exit", re.compile(r"(?:exit|return|status) code\s*137\b", re.I)),
    ),
    "billing_or_runner_blocked": (
        ("billing", re.compile(r"billing|payment method|spending limit|budget exceeded|actions minutes|minutes quota|account .*disabled|account .*not allowed|repository .*disabled.*actions|payment required", re.I)),
    ),
    "network_resolution_failure": (
        ("dns_resolution", re.compile(r"temporary failure in name resolution|could not resolve host|name or service not known|getaddrinfo failed|nodename nor servname provided", re.I)),
        ("network_connection", re.compile(r"failed to establish a new connection|network is unreachable|connection refused|connection reset by peer|proxyerror|max retries exceeded", re.I)),
    ),
    "dependency_resolution_failure": (
        ("pip_resolution", re.compile(r"resolutionimpossible|could not find a version that satisfies the requirement|no matching distribution found|dependency conflict|pip(?:'s)? dependency resolver", re.I)),
        ("package_build", re.compile(r"failed building wheel|subprocess-exited-with-error.*(?:build|install)", re.I)),
    ),
    "import_failure": (
        ("missing_module", re.compile(r"modulenotfounderror|no module named ['\"]|importerror|cannot import name|dll load failed", re.I)),
    ),
    "workflow_configuration_failure": (
        ("invalid_workflow", re.compile(r"invalid workflow file|the workflow is not valid|unexpected value|yaml(?: syntax)? error|workflow validation failed|jobs\.[\w-]+\.[\w-]+ is not allowed", re.I)),
        ("permission_configuration", re.compile(r"resource not accessible by integration|workflow permission denied|github actions is not enabled", re.I)),
    ),
    "test_failure": (
        ("pytest_failed", re.compile(r"^\s*(?:FAILED|ERROR)\s+\S+|=+\s*FAILURES\s*=+|\bassertionerror\b|\btests? failed\b|\bfailed,?\s+\d+", re.I | re.M)),
    ),
    "unknown_infrastructure_failure": (
        ("runner_failure", re.compile(r"runner has received a shutdown signal|runner lost communication|hosted runner|runner.*unavailable|job was canceled|job was cancelled|internal server error", re.I)),
        ("generic_timeout", re.compile(r"timeout|timed out", re.I)),
    ),
}

_START_MARKER = re.compile(
    r"current runner version|set up job|setup job|##\[group\]run|test session starts|collected \d+ items?|pytest|running \d+ tests?",
    re.I,
)
_PASS_MARKER = re.compile(r"(?:^|\s)(\d+) passed(?:\s|$)|passed in \d", re.I | re.M)
_FAILURE_MARKER = re.compile(r"(?:^|\s)(?:\d+ )?(?:failed|error)s?(?:\s|$)|\bfailed\b", re.I | re.M)


def _matched_signatures(text: str) -> dict[str, list[str]]:
    matched: dict[str, list[str]] = {}
    for failure_class, signatures in _SIGNATURES.items():
        names = [name for name, pattern in signatures if pattern.search(text)]
        if names:
            matched[failure_class] = names
    return matched


def parse_ci_log(text: str) -> dict[str, Any]:
    """Classify captured text without filesystem, subprocess, or network access."""
    if not isinstance(text, str):
        return {
            "schema": "NeuroTopology.CIResourceAudit.Log.v1",
            "input_valid": False,
            "classification": "unknown_infrastructure_failure",
            "failure_detected": True,
            "job_started": False,
            "tests_executed": False,
            "tests_passed": False,
            "billing_evidence": False,
            "generic_timeout_only": False,
            "matched_signatures": [],
            "errors": ["log input must be text"],
        }

    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    matched = _matched_signatures(normalized)
    failure_classes = [name for name in FAILURE_CLASSES if name in matched]
    explicit_failure = bool(failure_classes)
    job_started = bool(_START_MARKER.search(normalized))
    tests_executed = bool(re.search(r"pytest|test session starts|collected \d+ items?|(?:^|\s)(?:FAILED|ERROR|PASSED)\s+", normalized, re.I | re.M))
    has_test_failure = "test_failure" in matched
    passed_summary = bool(_PASS_MARKER.search(normalized))
    tests_passed = bool(job_started and tests_executed and passed_summary and not has_test_failure)
    timeout_found = bool(re.search(r"timeout|timed out", normalized, re.I))
    generic_timeout_only = bool(timeout_found and not any(name != "unknown_infrastructure_failure" for name in failure_classes))

    # Priority distinguishes resource blockers from downstream symptoms. A
    # timeout alone never becomes a billing classification.
    priority = (
        "disk_exhaustion",
        "memory_exhaustion",
        "billing_or_runner_blocked",
        "network_resolution_failure",
        "dependency_resolution_failure",
        "import_failure",
        "workflow_configuration_failure",
        "test_failure",
        "unknown_infrastructure_failure",
    )
    classification = next((name for name in priority if name in matched), None)
    if classification is None and normalized.strip():
        classification = "unknown_infrastructure_failure" if explicit_failure or generic_timeout_only else None
    errors: list[str] = []
    if not normalized.strip():
        errors.append("log is empty; no failure evidence was observed")
    return {
        "schema": "NeuroTopology.CIResourceAudit.Log.v1",
        "input_valid": True,
        "classification": classification,
        "failure_detected": classification is not None,
        "job_started": job_started,
        "job_never_started": bool(classification == "billing_or_runner_blocked" and not job_started),
        "tests_executed": tests_executed,
        "tests_passed": tests_passed,
        "pass_status": "passed" if tests_passed else "not_evaluated" if not job_started else "failed_or_not_proven",
        "billing_evidence": "billing_or_runner_blocked" in matched,
        "generic_timeout_only": generic_timeout_only,
        "matched_signatures": [f"{failure_class}:{signature}" for failure_class in sorted(matched) for signature in matched[failure_class]],
        "errors": errors,
    }


def classify_ci_log(text: str) -> dict[str, Any]:
    """Public alias emphasizing that this operation only classifies evidence."""
    return parse_ci_log(text)

