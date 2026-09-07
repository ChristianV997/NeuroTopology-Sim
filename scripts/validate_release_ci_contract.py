"""Validate the release-candidate GitHub Actions contract.

This module intentionally uses only repository metadata and standard JSON/YAML
data.  It does not execute workflows, install dependencies, access the network,
or infer scientific validity from a successful CI job.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path
from typing import Any, Iterable


SCHEMA_VERSION = "release-ci-contract-v1"
DIAGNOSTIC_SCHEMA_VERSION = "release-ci-diagnostic-v1"

# These are the stable checks consumed by the release gate.  A check is
# identified by its displayed GitHub job name, not by an implementation detail
# such as a matrix child name.
REQUIRED_CHECKS = {
    "core-tests": ("required-checks.yml", "core-tests"),
    "awareness-tests": ("required-checks.yml", "awareness-tests"),
    "ontology-claim-language": ("ontology-claim-language.yml", "ontology-claim-language"),
    "Cross-system smoke": ("smoke.yml", "smoke"),
    "DS005620 E2E Mock Run": ("ds005620-e2e.yml", "ds005620-e2e"),
}

HEAVY_DEPENDENCY_TOKENS = (
    "torch",
    "torch-geometric",
    "nvidia",
    "cuda",
    "cupy",
    "tensorflow",
    "gudhi",
    "cripser",
)
CPU_JOB_TOKENS = (
    "core",
    "required",
    "smoke",
    "ontology",
    "ds005620",
    "governance",
)
TEST_STEP_PATTERN = re.compile(
    r"(?:pytest|run_tests_isolated|docker\s+run|make\s+[^\n]*test|eval_runner|main\.py\s+--mode|validate_)",
    re.IGNORECASE,
)
SILENT_SKIP_PATTERN = re.compile(r"\b(?:skip|skipping|continue-on-error)\b", re.IGNORECASE)
EXPLICIT_UNSUPPORTED_PATTERN = re.compile(
    r"(?:not_supported|unsupported|unavailable|inconclusive|capability[-_ ]gate)",
    re.IGNORECASE,
)


def _events(workflow: dict[str, Any]) -> dict[str, Any]:
    """Return GitHub event configuration across YAML 1.1/1.2 parsers."""

    value = workflow.get("on", workflow.get(True, {}))
    if value is None:
        return {}
    if isinstance(value, list):
        return {str(item): {} for item in value}
    if isinstance(value, str):
        return {value: {}}
    return value if isinstance(value, dict) else {}


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - exercised in minimal CI images
        raise RuntimeError("PyYAML is required to validate workflow YAML") from exc
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"workflow is not a mapping: {path}")
    return value


def _job_display_name(job_id: str, job: dict[str, Any]) -> str:
    name = job.get("name")
    return name if isinstance(name, str) and name.strip() else job_id


def _needs(job: dict[str, Any]) -> tuple[list[str], str | None]:
    value = job.get("needs", [])
    if value is None:
        return [], None
    if isinstance(value, str):
        return [value], None
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return list(value), None
    return [], "needs must be a string or a list of strings"


def _run_text(job: dict[str, Any]) -> str:
    chunks: list[str] = []
    for step in job.get("steps", []):
        if isinstance(step, dict):
            chunks.append(str(step.get("run", "")))
            chunks.append(str(step.get("uses", "")))
            chunks.append(str(step.get("if", "")))
    return "\n".join(chunks)


def _automatic(events: dict[str, Any]) -> bool:
    return "pull_request" in events or "push" in events


def _test_like(job: dict[str, Any]) -> bool:
    return bool(TEST_STEP_PATTERN.search(_run_text(job)))


def _has_always_artifact_upload(job: dict[str, Any]) -> bool:
    for step in job.get("steps", []):
        if not isinstance(step, dict):
            continue
        uses = str(step.get("uses", "")).lower()
        condition = str(step.get("if", "")).replace(" ", "").lower()
        if "actions/upload-artifact@" in uses and "always()" in condition:
            return True
    return False


def _issue(
    code: str,
    message: str,
    *,
    workflow: str | None = None,
    job: str | None = None,
    severity: str = "error",
) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "workflow": workflow,
        "job": job,
        "severity": severity,
    }


def audit_workflows(root: Path) -> dict[str, Any]:
    """Return a deterministic, JSON-safe audit report for ``root``."""

    workflow_dir = root / ".github" / "workflows"
    report: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "status": "PASS",
        "workflows": [],
        "required_checks": {},
        "issues": [],
        "diagnostics": [],
    }
    issues: list[dict[str, Any]] = report["issues"]
    loaded: dict[str, dict[str, Any]] = {}

    if not workflow_dir.is_dir():
        issues.append(_issue("missing-workflow-directory", str(workflow_dir)))
    else:
        paths = sorted((*workflow_dir.glob("*.yml"), *workflow_dir.glob("*.yaml")))
        for path in paths:
            relative = path.relative_to(root).as_posix()
            try:
                workflow = _load_yaml(path)
            except Exception as exc:
                issues.append(_issue("invalid-yaml", str(exc), workflow=relative))
                continue
            loaded[path.name] = workflow
            jobs = workflow.get("jobs")
            events = _events(workflow)
            record = {
                "path": relative,
                "name": workflow.get("name", path.stem),
                "events": sorted(events),
                "jobs": sorted(jobs) if isinstance(jobs, dict) else [],
            }
            report["workflows"].append(record)
            if not isinstance(jobs, dict) or not jobs:
                issues.append(_issue("invalid-jobs", "workflow must define a non-empty jobs mapping", workflow=relative))
                continue

            for job_id, job in jobs.items():
                if not isinstance(job_id, str) or not isinstance(job, dict):
                    issues.append(_issue("invalid-job", "job ids and definitions must be mappings", workflow=relative))
                    continue
                display_name = _job_display_name(job_id, job)
                needs, needs_error = _needs(job)
                if needs_error:
                    issues.append(_issue("invalid-needs", needs_error, workflow=relative, job=job_id))
                for dependency in needs:
                    if dependency not in jobs:
                        issues.append(
                            _issue(
                                "undefined-needs",
                                f"job references undefined dependency: {dependency}",
                                workflow=relative,
                                job=job_id,
                            )
                        )
                timeout = job.get("timeout-minutes")
                if not isinstance(timeout, int) or isinstance(timeout, bool) or timeout <= 0:
                    issues.append(
                        _issue(
                            "missing-timeout",
                            "every job needs a positive integer timeout-minutes",
                            workflow=relative,
                            job=job_id,
                        )
                    )
                steps = job.get("steps")
                if not isinstance(steps, list) or not steps:
                    issues.append(_issue("invalid-steps", "job must define a non-empty steps list", workflow=relative, job=job_id))
                else:
                    for step in steps:
                        if not isinstance(step, dict):
                            issues.append(_issue("invalid-step", "workflow steps must be mappings", workflow=relative, job=job_id))
                            continue
                        if "uses" in step:
                            uses = str(step["uses"])
                            if not uses.startswith("./") and "@" not in uses:
                                issues.append(_issue("invalid-uses-reference", f"external action lacks @ ref: {uses}", workflow=relative, job=job_id))

                automatic = _automatic(events)
                text = _run_text(job)
                lower = text.lower()
                job_cpu_like = any(token in f"{job_id} {display_name}".lower() for token in CPU_JOB_TOKENS)
                if automatic and job_cpu_like:
                    if re.search(r"pip\s+install[^\n]*requirements\.txt(?:\s|$)", text, re.IGNORECASE):
                        issues.append(_issue("aggregate-profile-in-cpu-job", "automatic CPU job installs aggregate requirements.txt", workflow=relative, job=job_id))
                    heavy = [token for token in HEAVY_DEPENDENCY_TOKENS if token in lower]
                    if heavy and "requirements-base.txt" not in lower:
                        issues.append(_issue("heavy-dependency-in-cpu-job", f"automatic CPU job references heavy packages: {heavy}", workflow=relative, job=job_id))
                    if job_id in {"core-tests", "isolated-core-suite", "fast-contracts", "ds005620-e2e", "smoke"} and "requirements-base.txt" not in lower:
                        issues.append(_issue("missing-base-profile", "automatic core job must install requirements-base.txt", workflow=relative, job=job_id))

                if automatic and _test_like(job) and not _has_always_artifact_upload(job):
                    issues.append(_issue("missing-failure-artifact", "test-like automatic job lacks an always-run artifact upload", workflow=relative, job=job_id))
                if automatic and SILENT_SKIP_PATTERN.search(text) and not EXPLICIT_UNSUPPORTED_PATTERN.search(text):
                    issues.append(_issue("silent-optional-skip", "optional capability is skipped without an explicit NOT_SUPPORTED/unavailable status", workflow=relative, job=job_id))

    # Check names are a public CI interface.  Missing, duplicated, and manual-only
    # definitions are all contract failures because they make branch protection
    # ambiguous.
    definitions: dict[str, list[tuple[str, str, dict[str, Any]]]] = {}
    for filename, workflow in loaded.items():
        events = _events(workflow)
        jobs = workflow.get("jobs", {})
        if not isinstance(jobs, dict) or not _automatic(events):
            continue
        for job_id, job in jobs.items():
            if isinstance(job, dict):
                definitions.setdefault(_job_display_name(job_id, job), []).append((filename, job_id, job))

    for check_name, (expected_file, expected_job) in REQUIRED_CHECKS.items():
        matches = definitions.get(check_name, [])
        report["required_checks"][check_name] = {
            "expected": {"workflow": expected_file, "job": expected_job},
            "definitions": [{"workflow": item[0], "job": item[1]} for item in matches],
        }
        if not matches:
            issues.append(_issue("missing-required-check", f"required check is not defined automatically: {check_name}"))
        elif len(matches) > 1:
            issues.append(_issue("duplicate-required-check", f"required check has multiple automatic definitions: {check_name}"))
        elif matches[0][0] != expected_file or matches[0][1] != expected_job:
            issues.append(_issue("contradictory-required-check", f"required check moved from {expected_file}:{expected_job}: {check_name}"))
        elif "if" in matches[0][2] and "always" not in str(matches[0][2]["if"]).lower():
            issues.append(_issue("conditional-required-check", f"required check has a conditional job gate: {check_name}"))

    report["issues"] = issues
    report["status"] = "FAIL" if issues else "PASS"
    return report


def classify_failure(message: str = "", *, exit_code: int | None = None, timed_out: bool = False) -> dict[str, Any]:
    """Classify CI evidence without conflating missing logs with test failure."""

    text = str(message or "")
    lower = text.lower()
    if timed_out or "timeout" in lower or "timed out" in lower:
        classification = "timeout"
    elif any(token in lower for token in ("no space left", "enospc", "disk quota", "disk full")):
        classification = "disk_exhaustion"
    elif any(token in lower for token in ("out of memory", "memoryerror", "oom-kill", "oom killer", "killed")):
        classification = "memory_exhaustion"
    elif any(token in lower for token in ("temporary failure in name resolution", "connection refused", "network is unreachable", "proxyerror", "could not resolve host", "pypi.org")):
        classification = "network_failure"
    elif any(token in lower for token in ("resolutionimpossible", "no matching distribution", "could not find a version", "pip install")):
        classification = "dependency_resolution_failure"
    elif any(token in lower for token in ("modulenotfounderror", "importerror", "no module named")):
        classification = "import_failure"
    elif any(token in lower for token in ("assertionerror", "failed", "test session starts", "pytest")):
        classification = "test_failure"
    elif any(token in lower for token in ("unknown needs", "undefined needs", "invalid workflow", "yaml parse", "unrecognized named-value")):
        classification = "workflow_configuration_failure"
    elif any(token in lower for token in ("billing", "no available runners", "queued too long", "runner group")):
        classification = "billing_runner_blockage"
    elif any(token in lower for token in ("blobnotfound", "no steps", "runner lost", "internal server error", "job status: failure", "502", "503", "504")):
        classification = "unknown_infrastructure_failure"
    elif exit_code not in (None, 0):
        classification = "unknown_failure"
    else:
        classification = "none"

    dependency_state = {
        "import_failure": "missing",
        "dependency_resolution_failure": "resolution_failed",
    }.get(classification, "not_applicable")
    infrastructure_blocked = classification in {"billing_runner_blockage", "unknown_infrastructure_failure"}
    actionable = classification not in {"none", "unknown_infrastructure_failure", "billing_runner_blockage"}
    resource_classification = classification if classification in {"disk_exhaustion", "memory_exhaustion", "network_failure"} else "not_resource_related"
    return {
        "failure_classification": classification,
        "resource_classification": resource_classification,
        "dependency_state": dependency_state,
        "actionable": actionable,
        "infrastructure_blocked": infrastructure_blocked,
    }


def make_diagnostic(
    *,
    workflow: str,
    job: str,
    step: str,
    exit_code: int | None = None,
    timeout_state: str = "unknown",
    dependency_state: str | None = None,
    message: str = "",
    artifact_path: str | None = None,
) -> dict[str, Any]:
    result = classify_failure(message, exit_code=exit_code, timed_out=timeout_state == "timed_out")
    if dependency_state is not None:
        result["dependency_state"] = dependency_state
    return {
        "schema_version": DIAGNOSTIC_SCHEMA_VERSION,
        "workflow": str(workflow),
        "job": str(job),
        "step": str(step),
        "exit_code": exit_code if isinstance(exit_code, int) and not isinstance(exit_code, bool) else None,
        "timeout_state": str(timeout_state),
        "dependency_state": result["dependency_state"],
        "failure_classification": result["failure_classification"],
        "resource_classification": result["resource_classification"],
        "artifact_path": str(artifact_path) if artifact_path else None,
        "actionable": bool(result["actionable"]),
        "infrastructure_blocked": bool(result["infrastructure_blocked"]),
        "message": str(message),
    }


def _assert_finite(value: Any, path: str = "$") -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError(f"non-finite JSON number at {path}")
    if isinstance(value, dict):
        for key, item in value.items():
            _assert_finite(item, f"{path}.{key}")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            _assert_finite(item, f"{path}[{index}]")


def write_json(path: Path, value: Any) -> None:
    _assert_finite(value)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path("."))
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--validate-json", type=Path)
    parser.add_argument("--diagnostic", action="store_true")
    parser.add_argument("--workflow", default="unknown")
    parser.add_argument("--job", default="unknown")
    parser.add_argument("--step", default="unknown")
    parser.add_argument("--exit-code", type=int)
    parser.add_argument("--timeout-state", default="unknown")
    parser.add_argument("--dependency-state")
    parser.add_argument("--message", default="")
    parser.add_argument("--artifact-path")
    return parser


def main(argv: Iterable[str] | None = None) -> int:
    args = _parser().parse_args(list(argv) if argv is not None else None)
    if args.validate_json:
        value = json.loads(args.validate_json.read_text(encoding="utf-8"))
        _assert_finite(value)
        print(f"PASS finite JSON: {args.validate_json}")
        return 0
    if args.diagnostic:
        diagnostic = make_diagnostic(
            workflow=args.workflow,
            job=args.job,
            step=args.step,
            exit_code=args.exit_code,
            timeout_state=args.timeout_state,
            dependency_state=args.dependency_state,
            message=args.message,
            artifact_path=args.artifact_path,
        )
        output = args.json_out or Path("outputs/ci_diagnostics/release_ci_diagnostic.json")
        write_json(output, diagnostic)
        print(json.dumps(diagnostic, sort_keys=True))
        return 0

    report = audit_workflows(args.root.resolve())
    output = args.json_out or args.root / "outputs/ci_diagnostics/release_ci_contract.json"
    write_json(output, report)
    print(f"{report['status']} release CI contract: {len(report['issues'])} issue(s)")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
